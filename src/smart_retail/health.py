"""Thread-safe operational liveness and readiness state."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType

from smart_retail.application_state import ApplicationState


class HealthComponent(str, Enum):
    CORE_SERVICES = "core_services"
    MODEL = "model"
    CAMERA = "camera"
    VISION_PIPELINE = "vision_pipeline"
    DATABASE = "database"


class ComponentStatus(str, Enum):
    INITIALIZING = "initializing"
    READY = "ready"
    UNAVAILABLE = "unavailable"
    DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class LivenessSnapshot:
    """Cheap proof that the local API process can respond."""

    status: str
    uptime_seconds: float


@dataclass(frozen=True, slots=True)
class ReadinessSnapshot:
    """One consistent copy of application and component readiness."""

    application_state: ApplicationState
    components: Mapping[str, str]

    @property
    def ready(self) -> bool:
        acceptable = {ComponentStatus.READY.value, ComponentStatus.DISABLED.value}
        return self.application_state is ApplicationState.RUNNING and all(
            status in acceptable for status in self.components.values()
        )

    @property
    def status(self) -> str:
        return "ready" if self.ready else "not_ready"


class HealthService:
    """Record component transitions without probing adapters from HTTP routes."""

    def __init__(
        self,
        database_enabled: bool,
        clock: Callable[[], float] = time.monotonic,
        disabled_components: Iterable[HealthComponent] = (),
    ) -> None:
        disabled = set(disabled_components)
        allowed_disabled = {
            HealthComponent.MODEL,
            HealthComponent.CAMERA,
            HealthComponent.VISION_PIPELINE,
        }
        if not disabled.issubset(allowed_disabled):
            raise ValueError(
                "Only model, camera, and vision components may be "
                "intentionally disabled."
            )
        self._clock = clock
        self._started_at = clock()
        self._lock = threading.Lock()
        self._application_state = ApplicationState.INITIALIZING
        self._components = {
            component: (
                ComponentStatus.DISABLED
                if component in disabled
                else ComponentStatus.INITIALIZING
            )
            for component in HealthComponent
        }
        if not database_enabled:
            self._components[HealthComponent.DATABASE] = ComponentStatus.DISABLED

    def set_application_state(self, state: ApplicationState) -> None:
        with self._lock:
            self._application_state = state

    def mark_ready(self, component: HealthComponent) -> None:
        self._set_component(component, ComponentStatus.READY)

    def mark_unavailable(self, component: HealthComponent) -> None:
        self._set_component(component, ComponentStatus.UNAVAILABLE)

    def get_liveness(self) -> LivenessSnapshot:
        uptime = max(0.0, self._clock() - self._started_at)
        return LivenessSnapshot(status="ok", uptime_seconds=uptime)

    def get_readiness(self) -> ReadinessSnapshot:
        with self._lock:
            application_state = self._application_state
            components = {
                component.value: status.value
                for component, status in self._components.items()
            }
        return ReadinessSnapshot(
            application_state=application_state,
            components=MappingProxyType(components),
        )

    def _set_component(
        self,
        component: HealthComponent,
        status: ComponentStatus,
    ) -> None:
        if not isinstance(component, HealthComponent):
            raise TypeError("Health component must be a HealthComponent value.")
        with self._lock:
            self._components[component] = status
