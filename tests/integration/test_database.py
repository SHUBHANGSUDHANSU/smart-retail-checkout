"""SQLite integration tests using isolated temporary database files."""

import logging
import sqlite3

import pytest

from smart_retail.domain.events import CartEventType
from smart_retail.domain.models import Product
from smart_retail.infrastructure.sqlite_repository import (
    PersistenceError,
    SQLiteCheckoutRepository,
)


class TestSQLiteCheckoutRepository:
    def test_session_and_cart_event_history_round_trip(
        self, sqlite_repository: SQLiteCheckoutRepository
    ) -> None:
        session = sqlite_repository.create_session(started_at=100.0)
        add = sqlite_repository.record_cart_event(
            session.session_id,
            CartEventType.ADD,
            timestamp=101.0,
            track_id=14,
            product_id="bottle",
            unit_price=40,
        )
        sqlite_repository.record_cart_event(
            session.session_id,
            CartEventType.REMOVE,
            timestamp=102.0,
            track_id=14,
            product_id="bottle",
            unit_price=40,
        )
        sqlite_repository.record_cart_event(
            session.session_id,
            CartEventType.RESET,
            timestamp=103.0,
        )
        closed = sqlite_repository.close_session(
            session.session_id,
            final_total=45,
            ended_at=104.0,
        )

        assert add.event_id == 1
        assert closed.final_total == 45
        assert sqlite_repository.get_session(session.session_id) == closed
        events = sqlite_repository.get_session_events(session.session_id)
        assert [event.event_type for event in events] == [
            CartEventType.ADD,
            CartEventType.REMOVE,
            CartEventType.RESET,
        ]
        assert events[0].unit_price == 40
        assert events[2].product_id is None

    def test_recent_sessions_are_bounded_and_newest_first(
        self, sqlite_repository: SQLiteCheckoutRepository
    ) -> None:
        older = sqlite_repository.create_session(started_at=100.0)
        sqlite_repository.close_session(older.session_id, 0, ended_at=101.0)
        newer = sqlite_repository.create_session(started_at=200.0)

        recent = sqlite_repository.get_recent_sessions(limit=1)

        assert [session.session_id for session in recent] == [newer.session_id]
        with pytest.raises(ValueError, match="between 1 and 1000"):
            sqlite_repository.get_recent_sessions(limit=0)

    def test_recent_events_are_bounded_and_newest_first(
        self, sqlite_repository: SQLiteCheckoutRepository
    ) -> None:
        session = sqlite_repository.create_session(started_at=100.0)
        for track_id, timestamp in ((7, 101.0), (8, 102.0)):
            sqlite_repository.record_cart_event(
                session.session_id,
                CartEventType.ADD,
                timestamp=timestamp,
                track_id=track_id,
                product_id="bottle",
                unit_price=40,
            )

        recent = sqlite_repository.get_recent_events(limit=1)

        assert [event.track_id for event in recent] == [8]
        with pytest.raises(ValueError, match="between 1 and 200"):
            sqlite_repository.get_recent_events(limit=201)

    def test_database_readiness_checks_the_initialized_schema(
        self, sqlite_repository: SQLiteCheckoutRepository
    ) -> None:
        assert sqlite_repository.is_ready()

        sqlite_repository.database_path.unlink()

        assert not sqlite_repository.is_ready()

    def test_close_is_idempotent_and_rejects_later_operations(
        self,
        sqlite_repository: SQLiteCheckoutRepository,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        with caplog.at_level(
            logging.INFO,
            logger="smart_retail.infrastructure.sqlite_repository",
        ):
            sqlite_repository.close()
            sqlite_repository.close()

        assert not sqlite_repository.is_ready()
        with pytest.raises(PersistenceError, match="not been initialized"):
            sqlite_repository.get_recent_sessions(limit=1)
        closed_events = [
            record
            for record in caplog.records
            if getattr(record, "event", None) == "database_closed"
        ]
        assert len(closed_events) == 1

    def test_failed_event_write_rolls_back_and_repository_recovers(
        self, sqlite_repository: SQLiteCheckoutRepository
    ) -> None:
        session = sqlite_repository.create_session(started_at=100.0)

        with pytest.raises(PersistenceError, match="FOREIGN KEY"):
            sqlite_repository.record_cart_event(
                session.session_id,
                CartEventType.ADD,
                timestamp=101.0,
                track_id=7,
                product_id="not-a-product",
                unit_price=10,
            )

        assert sqlite_repository.get_session_events(session.session_id) == []
        recorded = sqlite_repository.record_cart_event(
            session.session_id,
            CartEventType.ADD,
            timestamp=102.0,
            track_id=7,
            product_id="bottle",
            unit_price=40,
        )
        assert recorded.track_id == 7

    def test_parameterized_values_cannot_modify_schema(
        self, sqlite_repository: SQLiteCheckoutRepository
    ) -> None:
        hostile_id = "sku'); DROP TABLE checkout_sessions; --"
        hostile_class = "bottle'); DROP TABLE products; --"
        repository = SQLiteCheckoutRepository(
            sqlite_repository.database_path.with_name("hostile.sqlite3")
        )
        repository.initialize(
            {hostile_class: Product(hostile_id, "Quoted ' Product", 75)}
        )
        session = repository.create_session(started_at=100.0)
        repository.record_cart_event(
            session.session_id,
            CartEventType.ADD,
            timestamp=101.0,
            track_id=1,
            product_id=hostile_id,
            unit_price=75,
        )

        assert (
            repository.get_session_events(session.session_id)[0].product_id
            == hostile_id
        )
        with sqlite3.connect(repository.database_path) as connection:
            table_count = connection.execute(
                """
                SELECT COUNT(*) FROM sqlite_master
                WHERE type = ? AND name IN (?, ?, ?)
                """,
                ("table", "products", "checkout_sessions", "cart_events"),
            ).fetchone()[0]
        assert table_count == 3
        repository.close()

    def test_catalog_sync_marks_removed_products_inactive(
        self, sqlite_repository: SQLiteCheckoutRepository
    ) -> None:
        updated_products = {
            "bottle": Product("bottle", "Large Water Bottle", 55),
        }

        sqlite_repository.initialize(updated_products)

        with sqlite3.connect(sqlite_repository.database_path) as connection:
            rows = connection.execute(
                "SELECT id, display_name, price, active FROM products ORDER BY id"
            ).fetchall()
        assert rows == [
            ("apple", "Apple", 45, 0),
            ("bottle", "Large Water Bottle", 55, 1),
        ]
