"""SQLite checkout-history persistence using explicit parameterized SQL."""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from collections.abc import Callable, Mapping
from contextlib import closing
from pathlib import Path

from smart_retail.domain.events import CartEvent, CartEventType
from smart_retail.domain.models import CheckoutSession, Product
from smart_retail.infrastructure.logging_config import log_event

LOGGER = logging.getLogger(__name__)
SCHEMA_VERSION = 1
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS products (
    id TEXT PRIMARY KEY,
    detector_class TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    price INTEGER NOT NULL CHECK (price >= 0),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);

CREATE TABLE IF NOT EXISTS checkout_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at REAL NOT NULL,
    ended_at REAL,
    final_total INTEGER CHECK (final_total >= 0),
    CHECK (
        (ended_at IS NULL AND final_total IS NULL)
        OR (ended_at IS NOT NULL AND final_total IS NOT NULL AND ended_at >= started_at)
    )
);

CREATE TABLE IF NOT EXISTS cart_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    timestamp REAL NOT NULL,
    track_id INTEGER,
    product_id TEXT,
    event_type TEXT NOT NULL CHECK (event_type IN ('ADD', 'REMOVE', 'RESET')),
    unit_price INTEGER CHECK (unit_price >= 0),
    FOREIGN KEY (session_id) REFERENCES checkout_sessions(id),
    FOREIGN KEY (product_id) REFERENCES products(id),
    CHECK (
        (event_type = 'RESET' AND track_id IS NULL
            AND product_id IS NULL AND unit_price IS NULL)
        OR
        (event_type IN ('ADD', 'REMOVE') AND track_id IS NOT NULL
            AND product_id IS NOT NULL AND unit_price IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_cart_events_session_timestamp
ON cart_events(session_id, timestamp, id);

CREATE INDEX IF NOT EXISTS idx_checkout_sessions_started_at
ON checkout_sessions(started_at DESC, id DESC);
"""


class PersistenceError(RuntimeError):
    """Raised when checkout history cannot be safely read or written."""


class SQLiteCheckoutRepository:
    """Persist products, checkout sessions, and meaningful cart events."""

    def __init__(
        self,
        database_path: str | Path,
        busy_timeout_seconds: float = 5.0,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if busy_timeout_seconds <= 0:
            raise ValueError("SQLite busy timeout must be positive.")
        self.database_path = Path(database_path)
        self.busy_timeout_seconds = busy_timeout_seconds
        self._clock = clock
        self._initialized = False
        self._lifecycle_lock = threading.Lock()

    def initialize(self, products: Mapping[str, Product]) -> None:
        """Create/validate the schema and synchronize the active catalog."""
        if not products:
            raise PersistenceError("Cannot initialize SQLite with an empty catalog.")
        try:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            with closing(self._connect()) as connection, connection:
                schema_version = connection.execute("PRAGMA user_version").fetchone()[0]
                if schema_version not in (0, SCHEMA_VERSION):
                    raise PersistenceError(
                        f"Unsupported database schema version: {schema_version}."
                    )
                connection.executescript(SCHEMA_SQL)
                connection.execute("UPDATE products SET active = 0")
                connection.executemany(
                    """
                    INSERT INTO products (
                        id, detector_class, display_name, price, active
                    ) VALUES (?, ?, ?, ?, 1)
                    ON CONFLICT(id) DO UPDATE SET
                        detector_class = excluded.detector_class,
                        display_name = excluded.display_name,
                        price = excluded.price,
                        active = 1
                    """,
                    (
                        (
                            product.product_id,
                            detector_class,
                            product.name,
                            product.unit_price,
                        )
                        for detector_class, product in products.items()
                    ),
                )
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        except PersistenceError:
            raise
        except (OSError, sqlite3.Error) as error:
            raise PersistenceError(f"Could not initialize SQLite: {error}") from error

        with self._lifecycle_lock:
            self._initialized = True
        log_event(
            LOGGER,
            logging.INFO,
            "database_initialized",
            "SQLite checkout history initialized",
            database=self.database_path.name,
            schema_version=SCHEMA_VERSION,
            product_count=len(products),
        )

    def create_session(self, started_at: float | None = None) -> CheckoutSession:
        """Create one open checkout session."""
        self._require_initialized()
        timestamp = self._clock() if started_at is None else started_at
        try:
            with closing(self._connect()) as connection, connection:
                cursor = connection.execute(
                    "INSERT INTO checkout_sessions (started_at) VALUES (?)",
                    (timestamp,),
                )
                session_id = int(cursor.lastrowid)
        except sqlite3.Error as error:
            raise PersistenceError(
                f"Could not create checkout session: {error}"
            ) from error

        session = CheckoutSession(session_id, timestamp, None, None)
        log_event(
            LOGGER,
            logging.INFO,
            "checkout_session_created",
            "Checkout history session created",
            session_id=session.session_id,
        )
        return session

    def close_session(
        self,
        session_id: int,
        final_total: int,
        ended_at: float | None = None,
    ) -> CheckoutSession:
        """Atomically close one open session with its final in-memory total."""
        self._require_initialized()
        timestamp = self._clock() if ended_at is None else ended_at
        if final_total < 0:
            raise ValueError("Final cart total cannot be negative.")
        try:
            with closing(self._connect()) as connection, connection:
                cursor = connection.execute(
                    """
                    UPDATE checkout_sessions
                    SET ended_at = ?, final_total = ?
                    WHERE id = ? AND ended_at IS NULL
                    """,
                    (timestamp, final_total, session_id),
                )
                if cursor.rowcount != 1:
                    raise PersistenceError(
                        f"Open checkout session {session_id} does not exist."
                    )
                row = connection.execute(
                    """
                    SELECT id, started_at, ended_at, final_total
                    FROM checkout_sessions WHERE id = ?
                    """,
                    (session_id,),
                ).fetchone()
                if row is None:
                    raise PersistenceError(
                        f"Checkout session {session_id} disappeared during close."
                    )
        except PersistenceError:
            raise
        except sqlite3.Error as error:
            raise PersistenceError(
                f"Could not close checkout session: {error}"
            ) from error

        session = self._session_from_row(row)
        log_event(
            LOGGER,
            logging.INFO,
            "checkout_session_closed",
            "Checkout history session closed",
            session_id=session.session_id,
            final_total=session.final_total,
        )
        return session

    def record_cart_event(
        self,
        session_id: int,
        event_type: CartEventType,
        timestamp: float,
        track_id: int | None = None,
        product_id: str | None = None,
        unit_price: int | None = None,
    ) -> CartEvent:
        """Persist one successful ADD/REMOVE or one explicit RESET action."""
        self._require_initialized()
        self._validate_event_fields(event_type, track_id, product_id, unit_price)
        try:
            with closing(self._connect()) as connection, connection:
                cursor = connection.execute(
                    """
                    INSERT INTO cart_events (
                        session_id, timestamp, track_id, product_id,
                        event_type, unit_price
                    )
                    SELECT id, ?, ?, ?, ?, ?
                    FROM checkout_sessions
                    WHERE id = ? AND ended_at IS NULL
                    """,
                    (
                        timestamp,
                        track_id,
                        product_id,
                        event_type.value,
                        unit_price,
                        session_id,
                    ),
                )
                if cursor.rowcount != 1:
                    raise PersistenceError(
                        f"Open checkout session {session_id} does not exist."
                    )
                event_id = int(cursor.lastrowid)
        except PersistenceError:
            raise
        except sqlite3.Error as error:
            raise PersistenceError(f"Could not record cart event: {error}") from error

        return CartEvent(
            event_id=event_id,
            session_id=session_id,
            timestamp=timestamp,
            track_id=track_id,
            product_id=product_id,
            event_type=event_type,
            unit_price=unit_price,
        )

    def get_session(self, session_id: int) -> CheckoutSession | None:
        """Return one checkout session, or None when it does not exist."""
        self._require_initialized()
        try:
            with closing(self._connect()) as connection:
                row = connection.execute(
                    """
                    SELECT id, started_at, ended_at, final_total
                    FROM checkout_sessions WHERE id = ?
                    """,
                    (session_id,),
                ).fetchone()
        except sqlite3.Error as error:
            raise PersistenceError(
                f"Could not read checkout session: {error}"
            ) from error
        return self._session_from_row(row) if row is not None else None

    def get_recent_sessions(self, limit: int = 10) -> list[CheckoutSession]:
        """Return newest sessions first, including incomplete runs."""
        self._require_initialized()
        if not 1 <= limit <= 1000:
            raise ValueError("Recent-session limit must be between 1 and 1000.")
        try:
            with closing(self._connect()) as connection:
                rows = connection.execute(
                    """
                    SELECT id, started_at, ended_at, final_total
                    FROM checkout_sessions
                    ORDER BY started_at DESC, id DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        except sqlite3.Error as error:
            raise PersistenceError(
                f"Could not read recent sessions: {error}"
            ) from error
        return [self._session_from_row(row) for row in rows]

    def get_recent_events(self, limit: int = 50) -> list[CartEvent]:
        """Return newest cart events first across all checkout sessions."""
        self._require_initialized()
        if not 1 <= limit <= 200:
            raise ValueError("Recent-event limit must be between 1 and 200.")
        try:
            with closing(self._connect()) as connection:
                rows = connection.execute(
                    """
                    SELECT id, session_id, timestamp, track_id, product_id,
                           event_type, unit_price
                    FROM cart_events
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        except sqlite3.Error as error:
            raise PersistenceError(f"Could not read recent events: {error}") from error
        return [self._event_from_row(row) for row in rows]

    def is_ready(self) -> bool:
        """Return whether the configured database and application schema respond."""
        with self._lifecycle_lock:
            if not self._initialized:
                return False
        try:
            with closing(self._connect()) as connection:
                row = connection.execute(
                    """
                    SELECT 1
                    FROM sqlite_master
                    WHERE type = 'table' AND name = 'checkout_sessions'
                    """
                ).fetchone()
        except (OSError, sqlite3.Error):
            return False
        return row is not None

    def close(self) -> None:
        """Close repository ownership; per-operation connections are already closed."""
        with self._lifecycle_lock:
            if not self._initialized:
                return
            self._initialized = False
        log_event(
            LOGGER,
            logging.INFO,
            "database_closed",
            "SQLite checkout history closed",
            database=self.database_path.name,
        )

    def get_session_events(self, session_id: int) -> list[CartEvent]:
        """Return one session's event history in deterministic insertion order."""
        self._require_initialized()
        try:
            with closing(self._connect()) as connection:
                rows = connection.execute(
                    """
                    SELECT id, session_id, timestamp, track_id, product_id,
                           event_type, unit_price
                    FROM cart_events
                    WHERE session_id = ?
                    ORDER BY id
                    """,
                    (session_id,),
                ).fetchall()
        except sqlite3.Error as error:
            raise PersistenceError(f"Could not read cart events: {error}") from error
        return [self._event_from_row(row) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path,
            timeout=self.busy_timeout_seconds,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _require_initialized(self) -> None:
        with self._lifecycle_lock:
            if not self._initialized:
                raise PersistenceError("SQLite repository has not been initialized.")

    @staticmethod
    def _validate_event_fields(
        event_type: CartEventType,
        track_id: int | None,
        product_id: str | None,
        unit_price: int | None,
    ) -> None:
        if not isinstance(event_type, CartEventType):
            raise ValueError("Cart event type must be a CartEventType value.")
        if event_type is CartEventType.RESET:
            if any(value is not None for value in (track_id, product_id, unit_price)):
                raise ValueError("RESET events cannot reference a product or track.")
            return
        if track_id is None or product_id is None or unit_price is None:
            raise ValueError("ADD and REMOVE events require product and track data.")
        if unit_price < 0:
            raise ValueError("Cart-event unit price cannot be negative.")

    @staticmethod
    def _session_from_row(row: sqlite3.Row) -> CheckoutSession:
        return CheckoutSession(
            session_id=int(row["id"]),
            started_at=float(row["started_at"]),
            ended_at=(float(row["ended_at"]) if row["ended_at"] is not None else None),
            final_total=(
                int(row["final_total"]) if row["final_total"] is not None else None
            ),
        )

    @staticmethod
    def _event_from_row(row: sqlite3.Row) -> CartEvent:
        return CartEvent(
            event_id=int(row["id"]),
            session_id=int(row["session_id"]),
            timestamp=float(row["timestamp"]),
            track_id=int(row["track_id"]) if row["track_id"] is not None else None,
            product_id=row["product_id"],
            event_type=CartEventType(row["event_type"]),
            unit_price=(
                int(row["unit_price"]) if row["unit_price"] is not None else None
            ),
        )
