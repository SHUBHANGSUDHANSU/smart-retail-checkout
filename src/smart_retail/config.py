"""Typed, immutable runtime configuration with environment overrides."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, cast

PACKAGE_ROOT = Path(__file__).resolve().parent
SOURCE_PROJECT_ROOT = PACKAGE_ROOT.parents[1]
PROJECT_ROOT = (
    SOURCE_PROJECT_ROOT
    if (SOURCE_PROJECT_ROOT / "pyproject.toml").is_file()
    else Path.cwd().resolve()
)
DEFAULT_CONFIG_DIR = PACKAGE_ROOT / "configs"
ENV_PREFIX = "SMART_RETAIL_"
DevicePreference = Literal["auto", "mps", "cpu"]
TrackerType = Literal["bytetrack"]
VALID_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


class ConfigurationError(ValueError):
    """Raised when runtime configuration is malformed or impossible."""


@dataclass(frozen=True, slots=True)
class CameraConfig:
    camera_index: int = 0
    width: int = 1280
    height: int = 720
    read_max_attempts: int = 30
    read_retry_delay_seconds: float = 0.1
    mirror: bool = True

    def __post_init__(self) -> None:
        if self.camera_index < 0:
            raise ConfigurationError("Camera index cannot be negative.")
        if self.width <= 0 or self.height <= 0:
            raise ConfigurationError("Camera width and height must be positive.")
        if self.read_max_attempts < 1:
            raise ConfigurationError("Camera read attempts must be at least 1.")
        if self.read_retry_delay_seconds < 0:
            raise ConfigurationError("Camera retry delay cannot be negative.")


@dataclass(frozen=True, slots=True)
class ModelConfig:
    model_path: str = "yolov8n.pt"
    confidence_threshold: float = 0.45
    iou_threshold: float = 0.70
    device_preference: DevicePreference = "auto"
    image_size: int = 640
    allowed_classes: tuple[str, ...] = (
        "bottle",
        "cup",
        "banana",
        "apple",
        "orange",
    )

    def __post_init__(self) -> None:
        if not self.model_path.strip():
            raise ConfigurationError("Model path cannot be empty.")
        _validate_probability("Model confidence threshold", self.confidence_threshold)
        _validate_probability("Model IoU threshold", self.iou_threshold)
        if self.device_preference not in {"auto", "mps", "cpu"}:
            raise ConfigurationError(
                "Model device preference must be one of: auto, mps, cpu."
            )
        if self.image_size <= 0:
            raise ConfigurationError("Model image size must be positive.")
        if not self.allowed_classes or any(
            not class_name.strip() for class_name in self.allowed_classes
        ):
            raise ConfigurationError("Model allowed classes cannot be empty.")
        if len(set(self.allowed_classes)) != len(self.allowed_classes):
            raise ConfigurationError("Model allowed classes cannot contain duplicates.")

    @property
    def display_name(self) -> str:
        if self.model_path == "yolov8n.pt":
            return "YOLOv8n"
        return Path(self.model_path).stem


@dataclass(frozen=True, slots=True)
class TrackerConfig:
    tracker_type: TrackerType = "bytetrack"
    config_path: Path = DEFAULT_CONFIG_DIR / "bytetrack_retail.yaml"
    tracking_confidence_threshold: float = 0.10
    persist_tracks: bool = True

    def __post_init__(self) -> None:
        if self.tracker_type != "bytetrack":
            raise ConfigurationError("Only the 'bytetrack' tracker is supported.")
        if not self.config_path.is_file():
            raise ConfigurationError(
                f"Tracker configuration does not exist: {self.config_path}"
            )
        _validate_probability(
            "Tracker confidence threshold",
            self.tracking_confidence_threshold,
        )


@dataclass(frozen=True, slots=True)
class CheckoutConfig:
    zone_left: float = 0.70
    zone_top: float = 0.05
    zone_right: float = 0.98
    zone_bottom: float = 0.95
    zone_hysteresis: float = 0.015
    transition_confirmation_frames: int = 3
    track_expiry_grace_frames: int = 90

    def __post_init__(self) -> None:
        coordinates = (
            self.zone_left,
            self.zone_top,
            self.zone_right,
            self.zone_bottom,
        )
        if not all(0.0 <= coordinate <= 1.0 for coordinate in coordinates):
            raise ConfigurationError(
                "Checkout-zone coordinates must be between 0.0 and 1.0."
            )
        if self.zone_left >= self.zone_right or self.zone_top >= self.zone_bottom:
            raise ConfigurationError(
                "Checkout zone must have positive width and height."
            )
        if self.zone_hysteresis < 0.0:
            raise ConfigurationError("Checkout-zone hysteresis cannot be negative.")
        if (
            self.zone_hysteresis * 2 >= self.zone_right - self.zone_left
            or self.zone_hysteresis * 2 >= self.zone_bottom - self.zone_top
        ):
            raise ConfigurationError(
                "Checkout-zone hysteresis is too large for the configured zone."
            )
        if self.transition_confirmation_frames < 1:
            raise ConfigurationError(
                "Checkout transition confirmation frames must be at least 1."
            )
        if self.track_expiry_grace_frames < 1:
            raise ConfigurationError(
                "Checkout track expiry grace frames must be at least 1."
            )


@dataclass(frozen=True, slots=True)
class UIConfig:
    window_name: str = "Smart Retail & Checkout System"
    debug_display: bool = False
    show_fps: bool = True
    notification_duration_seconds: float = 2.0
    debug_log_every_n_frames: int = 15

    def __post_init__(self) -> None:
        if not self.window_name.strip():
            raise ConfigurationError("UI window name cannot be empty.")
        if self.notification_duration_seconds <= 0:
            raise ConfigurationError("UI notification duration must be positive.")
        if self.debug_log_every_n_frames < 1:
            raise ConfigurationError("UI debug log interval must be at least 1.")


@dataclass(frozen=True, slots=True)
class LoggingConfig:
    level: str = "INFO"
    format: str = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    json_enabled: bool = False
    file_path: Path | None = None
    file_max_bytes: int = 5_000_000
    file_backup_count: int = 3

    def __post_init__(self) -> None:
        normalized_level = self.level.upper()
        if normalized_level not in VALID_LOG_LEVELS:
            allowed = ", ".join(sorted(VALID_LOG_LEVELS))
            raise ConfigurationError(f"Log level must be one of: {allowed}.")
        object.__setattr__(self, "level", normalized_level)
        if not self.format.strip():
            raise ConfigurationError("Log format cannot be empty.")
        try:
            formatter = logging.Formatter(self.format)
            formatter.format(
                logging.LogRecord(
                    name="smart_retail.validation",
                    level=logging.INFO,
                    pathname="",
                    lineno=0,
                    msg="configuration validation",
                    args=(),
                    exc_info=None,
                )
            )
        except (TypeError, ValueError) as error:
            raise ConfigurationError(f"Log format is invalid: {error}") from error
        if self.file_max_bytes < 1:
            raise ConfigurationError("Log file maximum bytes must be at least 1.")
        if self.file_backup_count < 0:
            raise ConfigurationError("Log file backup count cannot be negative.")


@dataclass(frozen=True, slots=True)
class APIConfig:
    host: str = "127.0.0.1"
    port: int = 8000
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.host.strip():
            raise ConfigurationError("API host cannot be empty.")
        if not 1 <= self.port <= 65535:
            raise ConfigurationError("API port must be between 1 and 65535.")


@dataclass(frozen=True, slots=True)
class DatabaseConfig:
    enabled: bool = True
    path: Path = PROJECT_ROOT / "data/smart_retail.db"
    busy_timeout_seconds: float = 5.0

    def __post_init__(self) -> None:
        if not str(self.path).strip():
            raise ConfigurationError("Database path cannot be empty.")
        if self.path.exists() and self.path.is_dir():
            raise ConfigurationError("Database path cannot be a directory.")
        if self.busy_timeout_seconds <= 0:
            raise ConfigurationError("Database busy timeout must be positive.")


@dataclass(frozen=True, slots=True)
class MetricsConfig:
    rolling_window_size: int = 60

    def __post_init__(self) -> None:
        if self.rolling_window_size < 1:
            raise ConfigurationError("Metrics rolling window must be at least 1.")


@dataclass(frozen=True, slots=True)
class AppConfig:
    camera: CameraConfig = field(default_factory=CameraConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    tracker: TrackerConfig = field(default_factory=TrackerConfig)
    checkout: CheckoutConfig = field(default_factory=CheckoutConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    api: APIConfig = field(default_factory=APIConfig)
    metrics: MetricsConfig = field(default_factory=MetricsConfig)
    products_config_path: Path = DEFAULT_CONFIG_DIR / "products.json"

    def __post_init__(self) -> None:
        if not self.products_config_path.is_file():
            raise ConfigurationError(
                f"Product configuration does not exist: {self.products_config_path}"
            )
        if self.tracker.tracking_confidence_threshold > self.model.confidence_threshold:
            raise ConfigurationError(
                "Tracker confidence threshold cannot exceed the model confidence "
                "threshold used by checkout logic."
            )

    def safe_summary(self, active_device: str) -> str:
        """Return a concise startup summary containing no secret values."""
        api_status = (
            f"enabled@{self.api.host}:{self.api.port}"
            if self.api.enabled
            else "disabled"
        )
        log_destination = "console+file" if self.logging.file_path else "console"
        log_encoding = "json" if self.logging.json_enabled else "text"
        database_status = (
            f"enabled:{self.database.path.name}"
            if self.database.enabled
            else "disabled"
        )
        return (
            f"camera={self.camera.camera_index} "
            f"{self.camera.width}x{self.camera.height} | "
            f"model={Path(self.model.model_path).name} "
            f"conf={self.model.confidence_threshold:.2f} "
            f"iou={self.model.iou_threshold:.2f} "
            f"device={self.model.device_preference}->{active_device} | "
            f"tracker={self.tracker.tracker_type} | "
            f"zone=({self.checkout.zone_left:.2f},{self.checkout.zone_top:.2f},"
            f"{self.checkout.zone_right:.2f},{self.checkout.zone_bottom:.2f}) "
            f"confirm={self.checkout.transition_confirmation_frames}f "
            f"grace={self.checkout.track_expiry_grace_frames}f | "
            f"debug={self.ui.debug_display} fps={self.ui.show_fps} | "
            f"logging={self.logging.level}/{log_encoding}/{log_destination} | "
            f"database={database_status} | "
            f"api={api_status} | "
            f"metrics_window={self.metrics.rolling_window_size}f"
        )


def load_config(environ: Mapping[str, str] | None = None) -> AppConfig:
    """Load, parse, and validate all supported environment overrides."""
    environment = os.environ if environ is None else environ

    camera = CameraConfig(
        camera_index=_env_int(environment, "CAMERA_INDEX", 0),
        width=_env_int(environment, "CAMERA_WIDTH", 1280),
        height=_env_int(environment, "CAMERA_HEIGHT", 720),
        read_max_attempts=_env_int(environment, "CAMERA_READ_MAX_ATTEMPTS", 30),
        read_retry_delay_seconds=_env_float(
            environment,
            "CAMERA_READ_RETRY_DELAY_SECONDS",
            0.1,
        ),
        mirror=_env_bool(environment, "CAMERA_MIRROR", True),
    )
    model = ModelConfig(
        model_path=_env_string(environment, "MODEL_PATH", "yolov8n.pt"),
        confidence_threshold=_env_float(
            environment,
            "MODEL_CONFIDENCE_THRESHOLD",
            0.45,
        ),
        iou_threshold=_env_float(environment, "MODEL_IOU_THRESHOLD", 0.70),
        device_preference=cast(
            DevicePreference,
            _env_string(environment, "MODEL_DEVICE", "auto").lower(),
        ),
        image_size=_env_int(environment, "MODEL_IMAGE_SIZE", 640),
        allowed_classes=_env_csv(
            environment,
            "MODEL_ALLOWED_CLASSES",
            ("bottle", "cup", "banana", "apple", "orange"),
        ),
    )
    tracker = TrackerConfig(
        tracker_type=cast(
            TrackerType,
            _env_string(environment, "TRACKER_TYPE", "bytetrack").lower(),
        ),
        config_path=_env_path(
            environment,
            "TRACKER_CONFIG_PATH",
            DEFAULT_CONFIG_DIR / "bytetrack_retail.yaml",
        ),
        tracking_confidence_threshold=_env_float(
            environment,
            "TRACKER_CONFIDENCE_THRESHOLD",
            0.10,
        ),
        persist_tracks=_env_bool(environment, "TRACKER_PERSIST_TRACKS", True),
    )
    checkout = CheckoutConfig(
        zone_left=_env_float(environment, "CHECKOUT_ZONE_LEFT", 0.70),
        zone_top=_env_float(environment, "CHECKOUT_ZONE_TOP", 0.05),
        zone_right=_env_float(environment, "CHECKOUT_ZONE_RIGHT", 0.98),
        zone_bottom=_env_float(environment, "CHECKOUT_ZONE_BOTTOM", 0.95),
        zone_hysteresis=_env_float(
            environment,
            "CHECKOUT_ZONE_HYSTERESIS",
            0.015,
        ),
        transition_confirmation_frames=_env_int(
            environment,
            "CHECKOUT_TRANSITION_CONFIRMATION_FRAMES",
            3,
        ),
        track_expiry_grace_frames=_env_int(
            environment,
            "CHECKOUT_TRACK_EXPIRY_GRACE_FRAMES",
            90,
        ),
    )
    ui = UIConfig(
        window_name=_env_string(
            environment,
            "UI_WINDOW_NAME",
            "Smart Retail & Checkout System",
        ),
        debug_display=_env_bool(environment, "UI_DEBUG_DISPLAY", False),
        show_fps=_env_bool(environment, "UI_SHOW_FPS", True),
        notification_duration_seconds=_env_float(
            environment,
            "UI_NOTIFICATION_DURATION_SECONDS",
            2.0,
        ),
        debug_log_every_n_frames=_env_int(
            environment,
            "UI_DEBUG_LOG_EVERY_N_FRAMES",
            15,
        ),
    )
    logging_config = LoggingConfig(
        level=_env_string(environment, "LOG_LEVEL", "INFO"),
        format=_env_string(
            environment,
            "LOG_FORMAT",
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        ),
        json_enabled=_env_bool(environment, "LOG_JSON", False),
        file_path=_env_optional_path(environment, "LOG_FILE_PATH"),
        file_max_bytes=_env_int(environment, "LOG_FILE_MAX_BYTES", 5_000_000),
        file_backup_count=_env_int(environment, "LOG_FILE_BACKUP_COUNT", 3),
    )
    database = DatabaseConfig(
        enabled=_env_bool(environment, "DATABASE_ENABLED", True),
        path=_env_path(
            environment,
            "DATABASE_PATH",
            PROJECT_ROOT / "data/smart_retail.db",
        ),
        busy_timeout_seconds=_env_float(
            environment,
            "DATABASE_BUSY_TIMEOUT_SECONDS",
            5.0,
        ),
    )
    api = APIConfig(
        host=_env_string(environment, "API_HOST", "127.0.0.1"),
        port=_env_int(environment, "API_PORT", 8000),
        enabled=_env_bool(environment, "API_ENABLED", True),
    )
    metrics = MetricsConfig(
        rolling_window_size=_env_int(
            environment,
            "METRICS_ROLLING_WINDOW_SIZE",
            60,
        ),
    )
    return AppConfig(
        camera=camera,
        model=model,
        tracker=tracker,
        checkout=checkout,
        ui=ui,
        logging=logging_config,
        database=database,
        api=api,
        metrics=metrics,
        products_config_path=_env_path(
            environment,
            "PRODUCTS_CONFIG_PATH",
            DEFAULT_CONFIG_DIR / "products.json",
        ),
    )


def _environment_name(name: str) -> str:
    return f"{ENV_PREFIX}{name}"


def _raw_value(
    environment: Mapping[str, str],
    name: str,
) -> str | None:
    value = environment.get(_environment_name(name))
    return value.strip() if value is not None else None


def _env_string(
    environment: Mapping[str, str],
    name: str,
    default: str,
) -> str:
    value = _raw_value(environment, name)
    return default if value is None else value


def _env_int(
    environment: Mapping[str, str],
    name: str,
    default: int,
) -> int:
    value = _raw_value(environment, name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as error:
        raise ConfigurationError(
            f"{_environment_name(name)} must be an integer, got '{value}'."
        ) from error


def _env_float(
    environment: Mapping[str, str],
    name: str,
    default: float,
) -> float:
    value = _raw_value(environment, name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError as error:
        raise ConfigurationError(
            f"{_environment_name(name)} must be a number, got '{value}'."
        ) from error


def _env_bool(
    environment: Mapping[str, str],
    name: str,
    default: bool,
) -> bool:
    value = _raw_value(environment, name)
    if value is None:
        return default
    normalized = value.lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(
        f"{_environment_name(name)} must be a boolean "
        "(true/false, yes/no, on/off, or 1/0)."
    )


def _env_csv(
    environment: Mapping[str, str],
    name: str,
    default: tuple[str, ...],
) -> tuple[str, ...]:
    value = _raw_value(environment, name)
    if value is None:
        return default
    return tuple(part.strip() for part in value.split(","))


def _env_path(
    environment: Mapping[str, str],
    name: str,
    default: Path,
) -> Path:
    value = _raw_value(environment, name)
    if value is None:
        return default
    path = Path(value).expanduser()
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def _env_optional_path(
    environment: Mapping[str, str],
    name: str,
) -> Path | None:
    value = _raw_value(environment, name)
    if not value:
        return None
    path = Path(value).expanduser()
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def _validate_probability(label: str, value: float) -> None:
    if not 0.0 <= value <= 1.0:
        raise ConfigurationError(f"{label} must be between 0.0 and 1.0.")
