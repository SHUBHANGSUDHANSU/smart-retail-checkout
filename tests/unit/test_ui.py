"""Rendering smoke tests for the OpenCV presentation component."""

import unittest
from unittest.mock import patch

import numpy as np

from smart_retail.checkout.cart import CartService
from smart_retail.checkout.event_engine import CheckoutEventEngine
from smart_retail.checkout.zone import CheckoutZone
from smart_retail.config import load_config
from smart_retail.domain.models import Product, TrackedObject
from smart_retail.infrastructure.repository import load_product_catalog
from smart_retail.presentation.opencv_ui import OpenCVUI


class OpenCVUITests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = 100.0
        self.ui = OpenCVUI(
            window_name="Test",
            notification_duration=2.0,
            clock=lambda: self.now,
        )
        config = load_config({})
        self.cart = CartService(load_product_catalog(config.products_config_path))
        self.cart.add_item(7, "bottle")
        self.cart.add_item(12, "apple")
        self.cart.add_item(19, "apple")
        self.event_engine = CheckoutEventEngine(
            CheckoutZone(0.70, 0.05, 0.98, 0.95),
            confirmation_frames=1,
            expiry_grace_frames=90,
        )
        self.tracked_objects = [
            TrackedObject(
                track_id=7,
                class_name="bottle",
                confidence=0.91,
                bbox=(740, 180, 900, 460),
            )
        ]
        self.event_engine.process_frame(self.tracked_objects, 1280, 720, frame_number=0)

    def test_full_overlay_renders_on_normal_webcam_frame(self) -> None:
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)

        self.ui.render(
            frame,
            self.tracked_objects,
            self.event_engine.get_snapshot(),
            self.cart.get_snapshot(),
            fps=14.2,
            device="mps",
            inference_time_ms=58.4,
            debug=True,
        )

        self.assertGreater(np.count_nonzero(frame), 0)

    def test_notification_expires_automatically(self) -> None:
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        self.ui.show_notification("- Water Bottle added", "add")

        self.ui.render(
            frame,
            [],
            self.event_engine.get_snapshot(),
            self.cart.get_snapshot(),
            10.0,
            "cpu",
            90.0,
            False,
        )
        self.assertTrue(self.ui.notification_active)

        self.now += 2.1
        self.ui.render(
            frame,
            [],
            self.event_engine.get_snapshot(),
            self.cart.get_snapshot(),
            10.0,
            "cpu",
            90.0,
            False,
        )
        self.assertFalse(self.ui.notification_active)

    def test_long_product_name_renders_on_small_frame(self) -> None:
        cart = CartService(
            {
                "bottle": Product(
                    product_id="bottle",
                    name="Extra Long Limited Edition Sparkling Water Bottle",
                    unit_price=40,
                )
            }
        )
        cart.add_item(7, "bottle")
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        self.ui.render(
            frame,
            [],
            self.event_engine.get_snapshot(),
            cart.get_snapshot(),
            8.0,
            "cpu",
            110.0,
            False,
        )

        self.assertGreater(np.count_nonzero(frame), 0)

    def test_fps_can_be_hidden_by_configuration(self) -> None:
        ui = OpenCVUI(window_name="Test", show_fps=False)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        with patch("smart_retail.presentation.opencv_ui.cv2.putText") as put_text:
            ui.render(
                frame,
                [],
                self.event_engine.get_snapshot(),
                self.cart.get_snapshot(),
                10.0,
                "cpu",
                90.0,
                False,
            )

        rendered_text = [call.args[1] for call in put_text.call_args_list]
        self.assertFalse(any(text.startswith("FPS ") for text in rendered_text))
        self.assertTrue(any(text.startswith("Device CPU") for text in rendered_text))


if __name__ == "__main__":
    unittest.main()
