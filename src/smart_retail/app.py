"""Application composition and thin real-time orchestration."""

from __future__ import annotations

import logging
import threading
import time
from contextlib import AbstractContextManager
from dataclasses import dataclass, field

from smart_retail.api.factory import create_api_app
from smart_retail.api.server import APIServerError, BackgroundAPIServer
from smart_retail.application_state import (
    ApplicationNotReadyError,
    ApplicationState,
    CartResetResult,
    CheckoutFrameSnapshot,
    SessionHistory,
)
from smart_retail.checkout.cart import CartService
from smart_retail.checkout.event_engine import CheckoutEventEngine, CheckoutUpdate
from smart_retail.checkout.zone import CheckoutZone
from smart_retail.config import AppConfig, ConfigurationError, load_config
from smart_retail.domain.events import (
    CartEvent,
    CartEventType,
    CheckoutEvent,
    CheckoutEventType,
)
from smart_retail.domain.models import (
    CartSnapshot,
    CheckoutSession,
    Product,
    TrackedObject,
)
from smart_retail.health import (
    HealthComponent,
    HealthService,
    LivenessSnapshot,
    ReadinessSnapshot,
)
from smart_retail.infrastructure.camera import CameraError, OpenCVCamera
from smart_retail.infrastructure.logging_config import (
    configure_bootstrap_logging,
    configure_logging,
    log_event,
)
from smart_retail.infrastructure.repository import load_product_catalog
from smart_retail.infrastructure.sqlite_repository import (
    PersistenceError,
    SQLiteCheckoutRepository,
)
from smart_retail.metrics import MetricsService, MetricsSnapshot
from smart_retail.presentation.opencv_ui import OpenCVUI
from smart_retail.vision.detector import YOLODetector
from smart_retail.vision.pipeline import VisionPipeline
from smart_retail.vision.tracker import ByteTracker

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class SmartRetailApplication:
    """Coordinate components while delegating all specialized behavior."""

    config: AppConfig
    logger: logging.Logger
    camera: OpenCVCamera
    vision: VisionPipeline
    event_engine: CheckoutEventEngine
    cart: CartService
    ui: OpenCVUI
    health: HealthService
    metrics: MetricsService = field(default_factory=MetricsService)
    persistence: SQLiteCheckoutRepository | None = None
    persistence_session_id: int | None = None
    api_server: BackgroundAPIServer | None = None
    _state_lock: AbstractContextManager[None] = field(
        default_factory=threading.Lock,
        init=False,
        repr=False,
    )
    _checkout_command_lock: AbstractContextManager[None] = field(
        default_factory=threading.Lock,
        init=False,
        repr=False,
    )
    _lifecycle_lock: AbstractContextManager[None] = field(
        default_factory=threading.Lock,
        init=False,
        repr=False,
    )
    _shutdown_complete: bool = field(default=False, init=False, repr=False)
    _shutdown_success: bool = field(default=True, init=False, repr=False)
    _shutdown_started: bool = field(default=False, init=False, repr=False)
    _shutdown_reason: str | None = field(default=None, init=False, repr=False)
    _completed_cleanup_steps: set[str] = field(
        default_factory=set,
        init=False,
        repr=False,
    )
    _stop_requested: threading.Event = field(
        default_factory=threading.Event,
        init=False,
        repr=False,
    )
    _run_finished: threading.Event = field(
        default_factory=threading.Event,
        init=False,
        repr=False,
    )
    _run_thread_id: int | None = field(default=None, init=False, repr=False)

    def run(self) -> int:
        """Own one realtime loop and make external shutdown wait for it."""
        with self._lifecycle_lock:
            if self._shutdown_started or self._stop_requested.is_set():
                return 0 if self._shutdown_success else 1
            if self._run_thread_id is not None:
                raise RuntimeError("The realtime frame loop is already running.")
            self._run_thread_id = threading.get_ident()
            self._run_finished.clear()
        try:
            return self._run_loop()
        finally:
            with self._lifecycle_lock:
                self._run_thread_id = None
                self._run_finished.set()

    def _run_loop(self) -> int:
        """Run until quit, interruption, or an unrecoverable component error."""
        self._log_starting()
        frame_number = 0
        debug_enabled = self.config.ui.debug_display
        previous_frame_time = time.perf_counter()
        shutdown_reason = "normal"
        exit_code = 0
        vision_pipeline_ready = False

        try:
            self._start_api_server()
            self._start_persistence_session()
            self.camera.open()
            self.health.mark_ready(HealthComponent.CAMERA)
            self.health.set_application_state(ApplicationState.RUNNING)
            self._log_started()
            while not self._stop_requested.is_set():
                frame = self.camera.read()
                frame_processing_started = time.perf_counter()
                try:
                    vision_result = self.vision.process(frame)
                except Exception as error:
                    self.health.mark_unavailable(HealthComponent.VISION_PIPELINE)
                    log_event(
                        self.logger,
                        logging.ERROR,
                        "vision_pipeline_failed",
                        "YOLO/ByteTrack processing failed",
                        exc_info=True,
                        error_type=type(error).__name__,
                    )
                    shutdown_reason = "vision_pipeline_error"
                    self._set_application_state(ApplicationState.ERROR)
                    exit_code = 1
                    break

                if not vision_pipeline_ready:
                    self.health.mark_ready(HealthComponent.VISION_PIPELINE)
                    vision_pipeline_ready = True

                frame_height, frame_width = frame.shape[:2]
                checkout_frame = self.process_checkout_frame(
                    vision_result.tracked_objects,
                    frame_width=frame_width,
                    frame_height=frame_height,
                    frame_number=frame_number,
                )
                current_frame_time = time.perf_counter()
                elapsed = current_frame_time - previous_frame_time
                fps = 1.0 / elapsed if elapsed > 0 else 0.0
                previous_frame_time = current_frame_time

                if (
                    debug_enabled
                    and frame_number % self.config.ui.debug_log_every_n_frames == 0
                ):
                    self._log_tracks(vision_result.tracked_objects)
                frame_number += 1
                active_tracks = len(
                    {
                        tracked_object.track_id
                        for tracked_object in vision_result.tracked_objects
                        if tracked_object.track_id is not None
                    }
                )
                self.metrics.record_frame(
                    detection_count=len(vision_result.tracked_objects),
                    active_tracks=active_tracks,
                    inference_latency_ms=vision_result.inference_time_ms,
                    frame_processing_latency_ms=(
                        current_frame_time - frame_processing_started
                    )
                    * 1000.0,
                    current_fps=fps,
                )

                self.ui.render(
                    frame,
                    tracked_objects=vision_result.tracked_objects,
                    checkout=checkout_frame.checkout,
                    cart=checkout_frame.cart,
                    fps=fps,
                    device=self.vision.device,
                    inference_time_ms=vision_result.inference_time_ms,
                    debug=debug_enabled,
                )
                self.ui.present(frame)

                key = self.ui.poll_key()
                if key in (ord("q"), ord("Q")):
                    log_event(
                        self.logger,
                        logging.INFO,
                        "shutdown_requested",
                        "Quit requested from the OpenCV UI",
                        source="keyboard",
                    )
                    shutdown_reason = "user_quit"
                    break
                if key in (ord("r"), ord("R")):
                    self.reset_checkout(source="opencv")
                if key in (ord("d"), ord("D")):
                    debug_enabled = not debug_enabled
                    state = "enabled" if debug_enabled else "disabled"
                    log_event(
                        self.logger,
                        logging.INFO,
                        "debug_mode_changed",
                        f"Debug mode {state}",
                        enabled=debug_enabled,
                    )
                    self.ui.show_notification(f"- Debug {state}", "info")
        except CameraError as error:
            self.metrics.record_camera_error()
            self.health.mark_unavailable(HealthComponent.CAMERA)
            log_event(
                self.logger,
                logging.ERROR,
                "camera_error",
                str(error),
                camera_index=self.config.camera.camera_index,
            )
            shutdown_reason = "camera_error"
            self._set_application_state(ApplicationState.ERROR)
            exit_code = 1
        except KeyboardInterrupt:
            log_event(
                self.logger,
                logging.INFO,
                "shutdown_requested",
                "Keyboard interrupt received",
                source="keyboard_interrupt",
            )
            shutdown_reason = "keyboard_interrupt"
        except Exception as error:
            log_event(
                self.logger,
                logging.CRITICAL,
                "application_runtime_failed",
                "Unexpected application failure",
                exc_info=True,
                error_type=type(error).__name__,
            )
            shutdown_reason = "unexpected_error"
            self._set_application_state(ApplicationState.ERROR)
            exit_code = 1
        finally:
            cleanup_success = self.shutdown(shutdown_reason, frame_number)
        return 1 if exit_code == 0 and not cleanup_success else exit_code

    def shutdown(self, reason: str, frames_processed: int = 0) -> bool:
        """Stop owned resources once, continuing after individual failures."""
        self._stop_requested.set()
        current_thread_id = threading.get_ident()
        with self._lifecycle_lock:
            if self._shutdown_reason is None:
                self._shutdown_reason = reason
            run_thread_id = self._run_thread_id
        if run_thread_id is not None and run_thread_id != current_thread_id:
            self._run_finished.wait()
            with self._lifecycle_lock:
                return self._shutdown_success

        with self._lifecycle_lock:
            if self._shutdown_complete:
                return self._shutdown_success
            shutdown_reason = self._shutdown_reason or reason

            self._set_application_state(ApplicationState.STOPPING)
            if not self._shutdown_started:
                self._shutdown_started = True
                log_event(
                    self.logger,
                    logging.INFO,
                    "application_stopping",
                    "Smart Retail Checkout is stopping",
                    reason=shutdown_reason,
                    frames_processed=frames_processed,
                )
            failed_steps: list[str] = []
            cleanup_steps = (
                ("api_server", self._stop_api_server),
                ("checkout_session", self._close_persistence_session),
                ("camera", self.camera.release),
                ("opencv_ui", self.ui.close),
                ("database", self._close_database),
            )
            for step_name, cleanup in cleanup_steps:
                if step_name in self._completed_cleanup_steps:
                    continue
                # A live API can still access every downstream shared service.
                if (
                    step_name != "api_server"
                    and "api_server" not in self._completed_cleanup_steps
                ):
                    break
                # Keep repository ownership until its active session is final.
                if (
                    step_name == "database"
                    and "checkout_session" not in self._completed_cleanup_steps
                ):
                    continue
                try:
                    cleanup()
                except Exception as error:
                    failed_steps.append(step_name)
                    log_event(
                        self.logger,
                        logging.ERROR,
                        "resource_cleanup_failed",
                        "Application resource cleanup failed",
                        exc_info=True,
                        cleanup_step=step_name,
                        error_type=type(error).__name__,
                    )
                else:
                    self._completed_cleanup_steps.add(step_name)

            self.health.mark_unavailable(HealthComponent.CAMERA)
            self._shutdown_success = not failed_steps
            if self._shutdown_success:
                self._set_application_state(ApplicationState.STOPPED)
                self._shutdown_complete = True
                log_event(
                    self.logger,
                    logging.INFO,
                    "application_stopped",
                    "Smart Retail Checkout stopped",
                    reason=shutdown_reason,
                    frames_processed=frames_processed,
                    cleanup_success=True,
                    failed_cleanup_steps=[],
                )
            else:
                log_event(
                    self.logger,
                    logging.ERROR,
                    "application_stop_incomplete",
                    "Smart Retail Checkout cleanup is incomplete",
                    reason=shutdown_reason,
                    frames_processed=frames_processed,
                    cleanup_success=False,
                    failed_cleanup_steps=failed_steps,
                )
            return self._shutdown_success

    def _apply_checkout_update(self, update: CheckoutUpdate) -> None:
        for event in update.events:
            self._apply_checkout_event(event)
        for track_id in update.expired_track_ids:
            self._remove_expired_track(track_id)

    def process_checkout_frame(
        self,
        tracked_objects: tuple[TrackedObject, ...],
        frame_width: int,
        frame_height: int,
        frame_number: int,
    ) -> CheckoutFrameSnapshot:
        """Serialize one vision checkout update against API cart resets."""
        with self._checkout_command_lock:
            update = self.event_engine.process_frame(
                tracked_objects,
                frame_width=frame_width,
                frame_height=frame_height,
                frame_number=frame_number,
            )
            self._apply_checkout_update(update)
            return CheckoutFrameSnapshot(
                update=update,
                checkout=self.event_engine.get_snapshot(),
                cart=self.cart.get_snapshot(),
            )

    def _apply_checkout_event(self, event: CheckoutEvent) -> None:
        self.metrics.record_checkout_event(event.event_type)
        log_event(
            self.logger,
            logging.INFO,
            f"checkout_{event.event_type.value.lower()}",
            f"Checkout {event.event_type.value}",
            track_id=event.track_id,
            product_class=event.product_class,
            checkout_timestamp=event.timestamp,
        )
        if event.event_type is CheckoutEventType.ENTER:
            product = self.cart.product_for_class(event.product_class)
            changed = self.cart.add_item(event.track_id, event.product_class)
            action = "added"
            notification_kind = "add"
        else:
            product = self.cart.product_for_track(event.track_id)
            changed = self.cart.remove_item(event.track_id)
            action = "removed"
            notification_kind = "remove"

        if not changed:
            unsupported = (
                event.event_type is CheckoutEventType.ENTER and product is None
            )
            ignored_reason = (
                "unsupported_product_class" if unsupported else "no_state_change"
            )
            log_event(
                self.logger,
                logging.WARNING if unsupported else logging.DEBUG,
                "cart_update_ignored",
                "Cart update did not change state",
                track_id=event.track_id,
                product_class=event.product_class,
                checkout_event=event.event_type.value,
                reason=ignored_reason,
            )
            return

        if product is not None:
            cart_snapshot = self.cart.get_snapshot()
            if event.event_type is CheckoutEventType.ENTER:
                self.metrics.record_cart_addition(cart_snapshot)
            else:
                self.metrics.record_cart_removal(cart_snapshot)
            log_event(
                self.logger,
                logging.INFO,
                f"cart_item_{action}",
                f"Cart item {action}",
                track_id=event.track_id,
                product_class=event.product_class,
                product=product.name,
                quantity=self._quantity_for(product.product_id),
                cart_total=cart_snapshot.total,
                reason="zone_transition",
            )
            persisted_event_type = (
                CartEventType.ADD
                if event.event_type is CheckoutEventType.ENTER
                else CartEventType.REMOVE
            )
            self._record_cart_event(
                event_type=persisted_event_type,
                timestamp=event.timestamp,
                track_id=event.track_id,
                product=product,
            )
            self.ui.show_notification(
                f"- {product.name} {action}",
                notification_kind,
            )

    def _remove_expired_track(self, track_id: int) -> None:
        product = self.cart.product_for_track(track_id)
        if product is None or not self.cart.remove_item(track_id):
            log_event(
                self.logger,
                logging.DEBUG,
                "track_expired",
                "Expired track had no cart entry",
                track_id=track_id,
                cart_item_removed=False,
            )
            return
        log_event(
            self.logger,
            logging.INFO,
            "track_expired",
            "Tracked object expired after its grace period",
            track_id=track_id,
            product=product.name,
            cart_item_removed=True,
        )
        log_event(
            self.logger,
            logging.INFO,
            "cart_item_removed",
            "Cart item removed after tracking loss",
            track_id=track_id,
            product_class=product.product_id,
            product=product.name,
            quantity=self._quantity_for(product.product_id),
            cart_total=self.cart.get_total(),
            reason="tracking_expired",
        )
        self.metrics.record_cart_removal(self.cart.get_snapshot())
        self._record_cart_event(
            event_type=CartEventType.REMOVE,
            timestamp=time.time(),
            track_id=track_id,
            product=product,
        )
        self.ui.show_notification(
            f"- {product.name} removed (tracking lost)",
            "remove",
        )

    def reset_checkout(self, source: str) -> CartResetResult:
        """Reset the one shared cart/event engine from OpenCV or the API."""
        with self._checkout_command_lock:
            application_state = self.health.get_readiness().application_state
            if source == "api" and application_state is not ApplicationState.RUNNING:
                raise ApplicationNotReadyError(
                    "API reset requires a running checkout application."
                )
            self.event_engine.reset()
            removed_count = self.cart.clear()
            snapshot = self.cart.get_snapshot()
            self.metrics.record_cart_reset(snapshot)
            log_event(
                self.logger,
                logging.INFO,
                "cart_reset",
                "Cart and checkout lifecycle state reset",
                source=source,
                removed_track_count=removed_count,
                cart_total=snapshot.total,
            )
            self._record_cart_event(
                event_type=CartEventType.RESET,
                timestamp=time.time(),
            )
            self.ui.show_notification("- Cart reset", "info")
            return CartResetResult(removed_count, snapshot)

    def _reset_checkout(self) -> None:
        """Preserve the existing internal reset entry point for tests/callers."""
        self.reset_checkout(source="opencv")

    def get_cart_snapshot(self) -> CartSnapshot:
        return self.cart.get_snapshot()

    def get_liveness_snapshot(self) -> LivenessSnapshot:
        return self.health.get_liveness()

    def get_readiness_snapshot(self) -> ReadinessSnapshot:
        return self.health.get_readiness()

    def get_metrics_snapshot(self) -> MetricsSnapshot:
        return self.metrics.get_snapshot()

    def get_recent_cart_events(self, limit: int) -> list[CartEvent]:
        repository = self._available_persistence()
        try:
            events = repository.get_recent_events(limit)
        except PersistenceError:
            self.metrics.record_persistence_error()
            self.health.mark_unavailable(HealthComponent.DATABASE)
            raise
        self._mark_database_ready_if_current(repository)
        return events

    def get_recent_checkout_sessions(self, limit: int) -> list[CheckoutSession]:
        repository = self._available_persistence()
        try:
            sessions = repository.get_recent_sessions(limit)
        except PersistenceError:
            self.metrics.record_persistence_error()
            self.health.mark_unavailable(HealthComponent.DATABASE)
            raise
        self._mark_database_ready_if_current(repository)
        return sessions

    def get_checkout_session_history(
        self,
        session_id: int,
    ) -> SessionHistory | None:
        repository = self._available_persistence()
        try:
            session = repository.get_session(session_id)
            events = (
                tuple(repository.get_session_events(session_id))
                if session is not None
                else ()
            )
        except PersistenceError:
            self.metrics.record_persistence_error()
            self.health.mark_unavailable(HealthComponent.DATABASE)
            raise
        self._mark_database_ready_if_current(repository)
        if session is None:
            return None
        return SessionHistory(
            session=session,
            events=events,
        )

    def _available_persistence(self) -> SQLiteCheckoutRepository:
        with self._state_lock:
            repository = self.persistence
        if repository is None:
            if self.config.database.enabled:
                self.health.mark_unavailable(HealthComponent.DATABASE)
            raise PersistenceError("SQLite checkout history is unavailable.")
        return repository

    def _mark_database_ready_if_current(
        self,
        repository: SQLiteCheckoutRepository,
    ) -> None:
        """Publish success only if a newer failure has not disabled this adapter."""
        with self._state_lock:
            if self.persistence is repository:
                # State -> health is the sole nested lock order used here.
                self.health.mark_ready(HealthComponent.DATABASE)

    def _set_application_state(self, state: ApplicationState) -> None:
        self.health.set_application_state(state)

    def _start_api_server(self) -> None:
        if self.api_server is None:
            return
        try:
            self.api_server.start()
        except APIServerError as error:
            log_event(
                self.logger,
                logging.ERROR,
                "api_server_start_failed",
                "FastAPI server is unavailable; continuing webcam checkout",
                exc_info=True,
                host=self.config.api.host,
                port=self.config.api.port,
                error_type=type(error).__name__,
            )

    def _stop_api_server(self) -> None:
        if self.api_server is not None:
            self.api_server.stop()

    def _start_persistence_session(self) -> None:
        with self._state_lock:
            repository = self.persistence
        if repository is None:
            return
        try:
            session = repository.create_session()
        except PersistenceError as error:
            self._disable_persistence("create_session", error)
            return
        with self._state_lock:
            if self.persistence is repository:
                self.persistence_session_id = session.session_id
        self._mark_database_ready_if_current(repository)

    def _close_persistence_session(self) -> None:
        with self._state_lock:
            repository = self.persistence
            session_id = self.persistence_session_id
        if repository is None or session_id is None:
            return
        final_total = self.cart.get_snapshot().total
        try:
            repository.close_session(
                session_id,
                final_total=final_total,
            )
        except PersistenceError as error:
            self.metrics.record_persistence_error()
            self.health.mark_unavailable(HealthComponent.DATABASE)
            log_event(
                self.logger,
                logging.ERROR,
                "persistence_session_close_failed",
                "Could not close checkout history session",
                exc_info=True,
                operation="close_session",
                session_id=session_id,
                error_type=type(error).__name__,
            )
            raise
        with self._state_lock:
            if self.persistence_session_id == session_id:
                self.persistence_session_id = None
        log_event(
            self.logger,
            logging.INFO,
            "session_closed",
            "Active checkout session finalized",
            session_id=session_id,
            final_total=final_total,
        )

    def _close_database(self) -> None:
        with self._state_lock:
            repository = self.persistence
        if repository is None:
            return
        try:
            repository.close()
        except PersistenceError:
            self.metrics.record_persistence_error()
            raise
        with self._state_lock:
            if self.persistence is repository:
                self.persistence = None
        self.health.mark_unavailable(HealthComponent.DATABASE)

    def _record_cart_event(
        self,
        event_type: CartEventType,
        timestamp: float,
        track_id: int | None = None,
        product: Product | None = None,
    ) -> None:
        with self._state_lock:
            repository = self.persistence
            session_id = self.persistence_session_id
        if repository is None or session_id is None:
            return
        try:
            persisted_event = repository.record_cart_event(
                session_id=session_id,
                event_type=event_type,
                timestamp=timestamp,
                track_id=track_id,
                product_id=product.product_id if product is not None else None,
                unit_price=product.unit_price if product is not None else None,
            )
        except PersistenceError as error:
            self._disable_persistence("record_cart_event", error)
            return
        log_event(
            self.logger,
            logging.DEBUG,
            "cart_event_persisted",
            "Cart history event persisted",
            event_id=persisted_event.event_id,
            session_id=persisted_event.session_id,
            cart_event_type=persisted_event.event_type.value,
        )
        self._mark_database_ready_if_current(repository)

    def _disable_persistence(self, operation: str, error: PersistenceError) -> None:
        self.metrics.record_persistence_error()
        with self._state_lock:
            session_id = self.persistence_session_id
            # Publish not-ready before removing the adapter so readers never
            # observe a missing repository paired with stale ready status.
            self.health.mark_unavailable(HealthComponent.DATABASE)
            self.persistence = None
            self.persistence_session_id = None
        log_event(
            self.logger,
            logging.ERROR,
            "persistence_write_failed",
            "SQLite history write failed; persistence disabled for this run",
            exc_info=True,
            operation=operation,
            session_id=session_id,
            error_type=type(error).__name__,
        )

    def _quantity_for(self, product_id: str) -> int:
        return next(
            (
                item.quantity
                for item in self.cart.get_items()
                if item.product_id == product_id
            ),
            0,
        )

    def _log_tracks(self, tracked_objects: tuple[TrackedObject, ...]) -> None:
        for tracked_object in tracked_objects:
            track_id = (
                str(tracked_object.track_id)
                if tracked_object.track_id is not None
                else "pending"
            )
            center_x, center_y = tracked_object.centroid
            log_event(
                self.logger,
                logging.DEBUG,
                "tracked_object_observed",
                "Tracked object observed",
                track_id=track_id,
                product_class=tracked_object.class_name,
                confidence=round(tracked_object.confidence, 4),
                center_x=round(center_x),
                center_y=round(center_y),
            )

    def _log_starting(self) -> None:
        log_event(
            self.logger,
            logging.INFO,
            "application_starting",
            "Smart Retail Checkout is starting",
            configuration=self.config.safe_summary(active_device=self.vision.device),
        )

    def _log_started(self) -> None:
        log_event(
            self.logger,
            logging.INFO,
            "application_started",
            "Smart Retail Checkout started",
            configuration=self.config.safe_summary(active_device=self.vision.device),
            controls="q=quit,r=reset,d=debug",
        )


def build_application(
    config: AppConfig,
    logger: logging.Logger,
) -> SmartRetailApplication:
    """Compose concrete adapters and pure services in one visible location."""
    products = load_product_catalog(config.products_config_path)
    health = HealthService(database_enabled=config.database.enabled)
    metrics = MetricsService(
        rolling_window_size=config.metrics.rolling_window_size,
    )
    persistence: SQLiteCheckoutRepository | None = None
    if config.database.enabled:
        candidate_repository = SQLiteCheckoutRepository(
            database_path=config.database.path,
            busy_timeout_seconds=config.database.busy_timeout_seconds,
        )
        try:
            candidate_repository.initialize(products)
        except PersistenceError as error:
            metrics.record_persistence_error()
            health.mark_unavailable(HealthComponent.DATABASE)
            log_event(
                logger,
                logging.ERROR,
                "persistence_initialization_failed",
                "SQLite history is unavailable; continuing with in-memory cart",
                exc_info=True,
                database=config.database.path.name,
                error_type=type(error).__name__,
            )
        else:
            persistence = candidate_repository
            health.mark_ready(HealthComponent.DATABASE)
    try:
        detector = YOLODetector(
            model_path=config.model.model_path,
            allowed_classes=config.model.allowed_classes,
            device_preference=config.model.device_preference,
        )
        health.mark_ready(HealthComponent.MODEL)
        tracker = ByteTracker(
            detector=detector,
            confidence_threshold=config.model.confidence_threshold,
            tracking_confidence_threshold=config.tracker.tracking_confidence_threshold,
            iou_threshold=config.model.iou_threshold,
            image_size=config.model.image_size,
            tracker_config_path=config.tracker.config_path,
            persist_tracks=config.tracker.persist_tracks,
        )
        event_engine = CheckoutEventEngine(
            zone=CheckoutZone(
                left=config.checkout.zone_left,
                top=config.checkout.zone_top,
                right=config.checkout.zone_right,
                bottom=config.checkout.zone_bottom,
                hysteresis=config.checkout.zone_hysteresis,
            ),
            confirmation_frames=config.checkout.transition_confirmation_frames,
            expiry_grace_frames=config.checkout.track_expiry_grace_frames,
        )
        application = SmartRetailApplication(
            config=config,
            logger=logger,
            camera=OpenCVCamera(
                config.camera,
                on_dropped_frame=metrics.record_dropped_frame,
            ),
            vision=VisionPipeline(tracker),
            event_engine=event_engine,
            cart=CartService(products),
            ui=OpenCVUI(
                window_name=config.ui.window_name,
                notification_duration=config.ui.notification_duration_seconds,
                show_fps=config.ui.show_fps,
            ),
            health=health,
            metrics=metrics,
            persistence=persistence,
        )
        if config.api.enabled:
            application.api_server = BackgroundAPIServer(
                create_api_app(application),
                host=config.api.host,
                port=config.api.port,
            )
        health.mark_ready(HealthComponent.CORE_SERVICES)
        return application
    except BaseException:
        health.mark_unavailable(HealthComponent.MODEL)
        if persistence is not None:
            try:
                persistence.close()
            except Exception as cleanup_error:
                log_event(
                    logger,
                    logging.ERROR,
                    "initialization_cleanup_failed",
                    "Repository cleanup after initialization failure failed",
                    exc_info=True,
                    cleanup_step="database",
                    error_type=type(cleanup_error).__name__,
                )
        raise


def main() -> int:
    """Load process configuration, compose the application, and run it."""
    try:
        config = load_config()
    except ConfigurationError as error:
        logger = configure_bootstrap_logging()
        log_event(
            logger,
            logging.CRITICAL,
            "configuration_invalid",
            "Application configuration is invalid",
            reason=str(error),
        )
        return 2

    try:
        logger = configure_logging(config.logging)
    except OSError as error:
        logger = configure_bootstrap_logging()
        log_event(
            logger,
            logging.CRITICAL,
            "logging_configuration_failed",
            "Logging could not be configured",
            exc_info=True,
            error_type=type(error).__name__,
        )
        return 2
    log_event(
        logger,
        logging.INFO,
        "logging_configured",
        "Application logging configured",
        configured_level=config.logging.level,
        format="json" if config.logging.json_enabled else "text",
        console=True,
        rotating_file=config.logging.file_path is not None,
    )
    try:
        application = build_application(config, logger)
    except KeyboardInterrupt:
        log_event(
            logger,
            logging.INFO,
            "shutdown_requested",
            "Keyboard interrupt received during application startup",
            source="keyboard_interrupt",
        )
        return 0
    except Exception as error:
        log_event(
            logger,
            logging.CRITICAL,
            "application_initialization_failed",
            "Could not initialize the application",
            exc_info=True,
            error_type=type(error).__name__,
        )
        return 1
    return application.run()
