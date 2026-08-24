"""Tests for typed environment configuration and startup validation."""

import dataclasses
import unittest

from smart_retail.config import PROJECT_ROOT, ConfigurationError, load_config


class ApplicationConfigurationTests(unittest.TestCase):
    def test_sensible_defaults_are_typed_and_immutable(self) -> None:
        config = load_config({})

        self.assertEqual(config.camera.camera_index, 0)
        self.assertEqual((config.camera.width, config.camera.height), (1280, 720))
        self.assertEqual(config.model.model_path, "yolov8n.pt")
        self.assertEqual(config.model.iou_threshold, 0.70)
        self.assertEqual(config.model.device_preference, "auto")
        self.assertEqual(config.tracker.tracker_type, "bytetrack")
        self.assertTrue(config.ui.show_fps)
        self.assertTrue(config.database.enabled)
        self.assertEqual(
            config.database.path,
            PROJECT_ROOT / "data/smart_retail.db",
        )
        self.assertTrue(config.api.enabled)
        self.assertEqual(
            config.api.cors_allowed_origins,
            ("http://localhost:5173", "http://127.0.0.1:5173"),
        )
        self.assertEqual(config.metrics.rolling_window_size, 60)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            config.camera.camera_index = 1

    def test_environment_overrides_every_configuration_area(self) -> None:
        config = load_config(
            {
                "SMART_RETAIL_CAMERA_INDEX": "1",
                "SMART_RETAIL_CAMERA_WIDTH": "1920",
                "SMART_RETAIL_CAMERA_HEIGHT": "1080",
                "SMART_RETAIL_MODEL_PATH": "models/best.pt",
                "SMART_RETAIL_MODEL_CONFIDENCE_THRESHOLD": "0.60",
                "SMART_RETAIL_MODEL_IOU_THRESHOLD": "0.55",
                "SMART_RETAIL_MODEL_DEVICE": "cpu",
                "SMART_RETAIL_MODEL_ALLOWED_CLASSES": "bottle, apple",
                "SMART_RETAIL_TRACKER_TYPE": "bytetrack",
                "SMART_RETAIL_TRACKER_CONFIDENCE_THRESHOLD": "0.20",
                "SMART_RETAIL_TRACKER_PERSIST_TRACKS": "false",
                "SMART_RETAIL_CHECKOUT_ZONE_LEFT": "0.65",
                "SMART_RETAIL_CHECKOUT_TRANSITION_CONFIRMATION_FRAMES": "4",
                "SMART_RETAIL_CHECKOUT_TRACK_EXPIRY_GRACE_FRAMES": "120",
                "SMART_RETAIL_UI_DEBUG_DISPLAY": "true",
                "SMART_RETAIL_UI_SHOW_FPS": "false",
                "SMART_RETAIL_UI_NOTIFICATION_DURATION_SECONDS": "3.5",
                "SMART_RETAIL_LOG_LEVEL": "debug",
                "SMART_RETAIL_LOG_JSON": "true",
                "SMART_RETAIL_LOG_FILE_PATH": "logs/application.log",
                "SMART_RETAIL_LOG_FILE_MAX_BYTES": "1000000",
                "SMART_RETAIL_LOG_FILE_BACKUP_COUNT": "5",
                "SMART_RETAIL_DATABASE_ENABLED": "false",
                "SMART_RETAIL_DATABASE_PATH": "runtime/history.sqlite3",
                "SMART_RETAIL_DATABASE_BUSY_TIMEOUT_SECONDS": "2.5",
                "SMART_RETAIL_API_HOST": "0.0.0.0",
                "SMART_RETAIL_API_PORT": "9000",
                "SMART_RETAIL_API_ENABLED": "yes",
                "SMART_RETAIL_API_CORS_ALLOWED_ORIGINS": (
                    "https://dashboard.example.test,http://localhost:4173"
                ),
                "SMART_RETAIL_METRICS_ROLLING_WINDOW_SIZE": "120",
            }
        )

        self.assertEqual(config.camera.camera_index, 1)
        self.assertEqual((config.camera.width, config.camera.height), (1920, 1080))
        self.assertEqual(config.model.model_path, "models/best.pt")
        self.assertEqual(config.model.confidence_threshold, 0.60)
        self.assertEqual(config.model.iou_threshold, 0.55)
        self.assertEqual(config.model.device_preference, "cpu")
        self.assertEqual(config.model.allowed_classes, ("bottle", "apple"))
        self.assertFalse(config.tracker.persist_tracks)
        self.assertEqual(config.checkout.zone_left, 0.65)
        self.assertEqual(config.checkout.transition_confirmation_frames, 4)
        self.assertEqual(config.checkout.track_expiry_grace_frames, 120)
        self.assertTrue(config.ui.debug_display)
        self.assertFalse(config.ui.show_fps)
        self.assertEqual(config.logging.level, "DEBUG")
        self.assertTrue(config.logging.json_enabled)
        self.assertEqual(
            config.logging.file_path,
            PROJECT_ROOT / "logs/application.log",
        )
        self.assertEqual(config.logging.file_max_bytes, 1_000_000)
        self.assertEqual(config.logging.file_backup_count, 5)
        self.assertFalse(config.database.enabled)
        self.assertEqual(
            config.database.path,
            PROJECT_ROOT / "runtime/history.sqlite3",
        )
        self.assertEqual(config.database.busy_timeout_seconds, 2.5)
        self.assertTrue(config.api.enabled)
        self.assertEqual((config.api.host, config.api.port), ("0.0.0.0", 9000))
        self.assertEqual(
            config.api.cors_allowed_origins,
            ("https://dashboard.example.test", "http://localhost:4173"),
        )
        self.assertEqual(config.metrics.rolling_window_size, 120)

    def test_invalid_numeric_types_fail_with_environment_name(self) -> None:
        invalid_values = (
            ({"SMART_RETAIL_CAMERA_INDEX": "first"}, "CAMERA_INDEX"),
            ({"SMART_RETAIL_MODEL_IOU_THRESHOLD": "wide"}, "IOU_THRESHOLD"),
            ({"SMART_RETAIL_API_PORT": "http"}, "API_PORT"),
        )
        for environment, expected_name in invalid_values:
            with self.subTest(environment=environment):
                with self.assertRaisesRegex(ConfigurationError, expected_name):
                    load_config(environment)

    def test_impossible_ranges_and_values_are_rejected(self) -> None:
        invalid_values = (
            ({"SMART_RETAIL_CAMERA_INDEX": "-1"}, "cannot be negative"),
            ({"SMART_RETAIL_CAMERA_WIDTH": "0"}, "must be positive"),
            ({"SMART_RETAIL_MODEL_CONFIDENCE_THRESHOLD": "1.1"}, "between"),
            ({"SMART_RETAIL_MODEL_IOU_THRESHOLD": "-0.1"}, "between"),
            ({"SMART_RETAIL_MODEL_DEVICE": "cuda"}, "auto, mps, cpu"),
            ({"SMART_RETAIL_TRACKER_TYPE": "deepsort"}, "bytetrack"),
            (
                {"SMART_RETAIL_TRACKER_CONFIDENCE_THRESHOLD": "0.8"},
                "cannot exceed",
            ),
            ({"SMART_RETAIL_CHECKOUT_ZONE_LEFT": "1.2"}, "between"),
            (
                {
                    "SMART_RETAIL_CHECKOUT_ZONE_LEFT": "0.8",
                    "SMART_RETAIL_CHECKOUT_ZONE_RIGHT": "0.7",
                },
                "positive width",
            ),
            (
                {"SMART_RETAIL_CHECKOUT_TRANSITION_CONFIRMATION_FRAMES": "0"},
                "at least 1",
            ),
            (
                {"SMART_RETAIL_CHECKOUT_TRACK_EXPIRY_GRACE_FRAMES": "0"},
                "at least 1",
            ),
            (
                {"SMART_RETAIL_UI_NOTIFICATION_DURATION_SECONDS": "0"},
                "must be positive",
            ),
            ({"SMART_RETAIL_LOG_LEVEL": "verbose"}, "Log level"),
            ({"SMART_RETAIL_LOG_FORMAT": "%(missing)s"}, "format is invalid"),
            ({"SMART_RETAIL_LOG_FILE_MAX_BYTES": "0"}, "at least 1"),
            ({"SMART_RETAIL_LOG_FILE_BACKUP_COUNT": "-1"}, "cannot be negative"),
            (
                {"SMART_RETAIL_DATABASE_BUSY_TIMEOUT_SECONDS": "0"},
                "timeout must be positive",
            ),
            ({"SMART_RETAIL_DATABASE_PATH": "."}, "cannot be a directory"),
            ({"SMART_RETAIL_API_PORT": "70000"}, "between 1 and 65535"),
            ({"SMART_RETAIL_API_HOST": ""}, "host cannot be empty"),
            ({"SMART_RETAIL_API_CORS_ALLOWED_ORIGINS": "*"}, "CORS origin"),
            (
                {"SMART_RETAIL_API_CORS_ALLOWED_ORIGINS": "ftp://localhost:5173"},
                "http or https",
            ),
            (
                {
                    "SMART_RETAIL_API_CORS_ALLOWED_ORIGINS": (
                        "http://user:password@localhost:5173"
                    )
                },
                "credentials",
            ),
            (
                {
                    "SMART_RETAIL_API_CORS_ALLOWED_ORIGINS": (
                        "http://localhost:5173/path"
                    )
                },
                "origin without a path",
            ),
            (
                {"SMART_RETAIL_METRICS_ROLLING_WINDOW_SIZE": "0"},
                "at least 1",
            ),
        )
        for environment, expected_message in invalid_values:
            with self.subTest(environment=environment):
                with self.assertRaisesRegex(ConfigurationError, expected_message):
                    load_config(environment)

    def test_invalid_boolean_is_rejected_instead_of_guessed(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "must be a boolean"):
            load_config({"SMART_RETAIL_API_ENABLED": "sometimes"})

    def test_missing_local_configuration_files_are_rejected(self) -> None:
        invalid_paths = (
            "SMART_RETAIL_TRACKER_CONFIG_PATH",
            "SMART_RETAIL_PRODUCTS_CONFIG_PATH",
        )
        for variable in invalid_paths:
            with self.subTest(variable=variable):
                with self.assertRaisesRegex(ConfigurationError, "does not exist"):
                    load_config({variable: "configs/not-present.yaml"})

    def test_safe_summary_does_not_reveal_full_local_paths(self) -> None:
        config = load_config(
            {
                "SMART_RETAIL_MODEL_PATH": "/private/project/models/best.pt",
                "SMART_RETAIL_LOG_FILE_PATH": "/private/logs/application.log",
                "SMART_RETAIL_DATABASE_PATH": "/private/data/history.db",
            }
        )

        summary = config.safe_summary(active_device="cpu")

        self.assertIn("model=best.pt", summary)
        self.assertIn("logging=INFO/text/console+file", summary)
        self.assertIn("database=enabled:history.db", summary)
        self.assertNotIn("/private", summary)


if __name__ == "__main__":
    unittest.main()
