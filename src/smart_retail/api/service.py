"""Hardware-free FastAPI runtime for containers and local API-only use."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import TypeVar

from fastapi import FastAPI

from smart_retail.api.factory import create_api_app
from smart_retail.application_state import (
    ApplicationNotReadyError,
    ApplicationState,
    CartResetResult,
    SessionHistory,
)
from smart_retail.checkout.cart import CartService
from smart_retail.config import AppConfig, load_config
from smart_retail.domain.events import CartEvent, CartEventType
from smart_retail.domain.models import CartSnapshot, CheckoutSession, Product
from smart_retail.health import (
    HealthComponent,
    HealthService,
    LivenessSnapshot,
    ReadinessSnapshot,
)
from smart_retail.infrastructure.logging_config import configure_logging, log_event
from smart_retail.infrastructure.repository import load_product_catalog
from smart_retail.infrastructure.sqlite_repository import (
    PersistenceError,
    SQLiteCheckoutRepository,
)
from smart_retail.metrics import MetricsService, MetricsSnapshot

PersistenceResult = TypeVar("PersistenceResult")


class HeadlessAPIRuntime:
    """Own API business state without importing camera or vision adapters."""

    def __init__(
        self,
        config: AppConfig,
        logger: logging.Logger,
        products: dict[str, Product],
        repository: SQLiteCheckoutRepository | None = None,
    ) -> None:
        if config.database.enabled and repository is None:
            raise ValueError("Enabled database configuration requires a repository.")
        self.config = config
        self.logger = logger
        self.cart = CartService(products)
        self.health = HealthService(
            database_enabled=config.database.enabled,
            disabled_components=(
                HealthComponent.MODEL,
                HealthComponent.CAMERA,
                HealthComponent.VISION_PIPELINE,
            ),
        )
        self.metrics = MetricsService(config.metrics.rolling_window_size)
        self._products = dict(products)
        self._repository = repository
        self._session_id: int | None = None
        self._state_lock = threading.Lock()
        self._checkout_lock = threading.Lock()
        self._lifecycle_lock = threading.Lock()
        self._lifecycle_condition = threading.Condition(self._lifecycle_lock)
        self._starting = False
        self._stopping = False
        self._started = False
        self._stopped = False

    def start(self) -> None:
        """Initialize SQLite and open one checkout-history session."""
        with self._lifecycle_condition:
            if self._started:
                return
            if self._stopped:
                raise RuntimeError("A stopped headless runtime cannot be restarted.")
            if self._starting:
                raise RuntimeError("The headless runtime is already starting.")
            self._starting = True

        repository = self._repository
        try:
            if repository is not None:
                repository.initialize(self._products)
                session = repository.create_session()
                with self._state_lock:
                    self._session_id = session.session_id
                self.health.mark_ready(HealthComponent.DATABASE)
            self.health.mark_ready(HealthComponent.CORE_SERVICES)
            self.health.set_application_state(ApplicationState.RUNNING)
        except Exception as error:
            self.metrics.record_persistence_error()
            self.health.mark_unavailable(HealthComponent.DATABASE)
            self.health.set_application_state(ApplicationState.ERROR)
            if repository is not None:
                try:
                    repository.close()
                except Exception as cleanup_error:
                    log_event(
                        self.logger,
                        logging.ERROR,
                        "database_close_failed",
                        "SQLite cleanup after startup failure also failed",
                        exc_info=True,
                        error_type=type(cleanup_error).__name__,
                    )
            with self._lifecycle_condition:
                self._starting = False
                self._lifecycle_condition.notify_all()
            log_event(
                self.logger,
                logging.CRITICAL,
                "headless_service_start_failed",
                "Headless API service failed to start",
                exc_info=True,
                error_type=type(error).__name__,
            )
            raise

        with self._lifecycle_condition:
            self._started = True
            self._starting = False
            self._lifecycle_condition.notify_all()

        log_event(
            self.logger,
            logging.INFO,
            "application_started",
            "Headless checkout API started",
            database_enabled=self.config.database.enabled,
        )

    def stop(self) -> None:
        """Close the active session and repository, retaining failed steps."""
        with self._lifecycle_condition:
            while self._starting:
                self._lifecycle_condition.wait()
            while self._stopping:
                self._lifecycle_condition.wait()
            if self._stopped:
                return
            self._stopping = True

        self.health.set_application_state(ApplicationState.STOPPING)
        log_event(
            self.logger,
            logging.INFO,
            "application_stopping",
            "Headless checkout API is stopping",
        )
        with self._state_lock:
            repository = self._repository
            session_id = self._session_id
        final_total = self.cart.get_snapshot().total

        if repository is not None and session_id is not None:
            try:
                repository.close_session(session_id, final_total=final_total)
            except Exception as error:
                self._record_stop_failure(
                    event="session_close_failed",
                    message="Headless checkout session could not be closed",
                    error=error,
                    session_id=session_id,
                )
                raise
            with self._state_lock:
                if self._repository is repository and self._session_id == session_id:
                    self._session_id = None
            log_event(
                self.logger,
                logging.INFO,
                "session_closed",
                "Headless checkout session closed",
                session_id=session_id,
                final_total=final_total,
            )

        if repository is not None:
            try:
                repository.close()
            except Exception as error:
                self._record_stop_failure(
                    event="database_close_failed",
                    message="Headless SQLite repository could not be closed",
                    error=error,
                )
                raise
            with self._state_lock:
                if self._repository is repository:
                    self._repository = None

        with self._lifecycle_condition:
            self._started = False
            self._stopped = True
            self._stopping = False
            self._lifecycle_condition.notify_all()
        self.health.set_application_state(ApplicationState.STOPPED)
        log_event(
            self.logger,
            logging.INFO,
            "application_stopped",
            "Headless checkout API stopped",
        )

    def _record_stop_failure(
        self,
        *,
        event: str,
        message: str,
        error: Exception,
        **fields: object,
    ) -> None:
        self.metrics.record_persistence_error()
        self.health.mark_unavailable(HealthComponent.DATABASE)
        self.health.set_application_state(ApplicationState.ERROR)
        with self._lifecycle_condition:
            self._stopping = False
            self._lifecycle_condition.notify_all()
        log_event(
            self.logger,
            logging.ERROR,
            event,
            message,
            exc_info=True,
            error_type=type(error).__name__,
            **fields,
        )

    def reset_checkout(self, source: str) -> CartResetResult:
        """Reset the same thread-safe CartService exposed by API routes."""
        with self._checkout_lock:
            if (
                self.health.get_readiness().application_state
                is not ApplicationState.RUNNING
            ):
                raise ApplicationNotReadyError(
                    "API reset requires a running checkout application."
                )
            removed_count = self.cart.clear()
            snapshot = self.cart.get_snapshot()
            self.metrics.record_cart_reset(snapshot)

        repository, session_id = self._persistence_snapshot()
        if repository is not None and session_id is not None:
            try:
                repository.record_cart_event(
                    session_id=session_id,
                    event_type=CartEventType.RESET,
                    timestamp=time.time(),
                )
            except PersistenceError:
                self.metrics.record_persistence_error()
                self.health.mark_unavailable(HealthComponent.DATABASE)
                raise

        log_event(
            self.logger,
            logging.INFO,
            "cart_reset",
            "Headless cart reset",
            source=source,
            removed_track_count=removed_count,
            cart_total=snapshot.total,
        )
        return CartResetResult(removed_count, snapshot)

    def get_cart_snapshot(self) -> CartSnapshot:
        return self.cart.get_snapshot()

    def get_liveness_snapshot(self) -> LivenessSnapshot:
        return self.health.get_liveness()

    def get_readiness_snapshot(self) -> ReadinessSnapshot:
        return self.health.get_readiness()

    def get_metrics_snapshot(self) -> MetricsSnapshot:
        return self.metrics.get_snapshot()

    def get_recent_cart_events(self, limit: int) -> list[CartEvent]:
        return self._run_persistence_read(
            lambda repository: repository.get_recent_events(limit)
        )

    def get_recent_checkout_sessions(self, limit: int) -> list[CheckoutSession]:
        return self._run_persistence_read(
            lambda repository: repository.get_recent_sessions(limit)
        )

    def get_checkout_session_history(self, session_id: int) -> SessionHistory | None:
        def load_history(
            repository: SQLiteCheckoutRepository,
        ) -> SessionHistory | None:
            session = repository.get_session(session_id)
            if session is None:
                return None
            return SessionHistory(
                session=session,
                events=tuple(repository.get_session_events(session_id)),
            )

        return self._run_persistence_read(load_history)

    def _run_persistence_read(
        self,
        operation: Callable[[SQLiteCheckoutRepository], PersistenceResult],
    ) -> PersistenceResult:
        repository, _ = self._required_persistence_snapshot()
        try:
            result = operation(repository)
        except PersistenceError:
            self.metrics.record_persistence_error()
            self.health.mark_unavailable(HealthComponent.DATABASE)
            raise
        with self._state_lock:
            repository_is_current = self._repository is repository
        if (
            repository_is_current
            and self.health.get_readiness().application_state
            is ApplicationState.RUNNING
        ):
            self.health.mark_ready(HealthComponent.DATABASE)
        return result

    def _persistence_snapshot(
        self,
    ) -> tuple[SQLiteCheckoutRepository | None, int | None]:
        with self._state_lock:
            return self._repository, self._session_id

    def _required_persistence_snapshot(
        self,
    ) -> tuple[SQLiteCheckoutRepository, int | None]:
        repository, session_id = self._persistence_snapshot()
        if repository is None:
            raise PersistenceError("SQLite checkout history is disabled.")
        return repository, session_id


def create_service_app(
    config: AppConfig | None = None,
    logger: logging.Logger | None = None,
) -> FastAPI:
    """Compose the container-friendly API, persistence, and business services."""
    runtime_config = config or load_config()
    runtime_logger = logger or configure_logging(runtime_config.logging)
    products = load_product_catalog(runtime_config.products_config_path)
    repository = (
        SQLiteCheckoutRepository(
            runtime_config.database.path,
            runtime_config.database.busy_timeout_seconds,
        )
        if runtime_config.database.enabled
        else None
    )
    runtime = HeadlessAPIRuntime(
        config=runtime_config,
        logger=runtime_logger,
        products=products,
        repository=repository,
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        runtime.start()
        try:
            yield
        finally:
            runtime.stop()

    application = create_api_app(runtime, lifespan=lifespan)
    application.state.runtime = runtime
    return application


def main() -> int:
    """Run the headless API server with environment-derived configuration."""
    import uvicorn

    config = load_config()
    logger = configure_logging(config.logging)
    application = create_service_app(config, logger)
    uvicorn.run(
        application,
        host=config.api.host,
        port=config.api.port,
        log_config=None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
