"""Reusable OpenCV presentation for the checkout application."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import cv2
import numpy as np

from smart_retail.checkout.event_engine import CheckoutStateSnapshot
from smart_retail.domain.events import ZoneState
from smart_retail.domain.models import CartSnapshot, TrackedObject

Color = tuple[int, int, int]
NotificationKind = Literal["add", "remove", "info"]

WHITE: Color = (245, 245, 245)
MUTED: Color = (185, 195, 205)
DARK: Color = (18, 24, 31)
GREEN: Color = (70, 210, 110)
RED: Color = (70, 90, 235)
YELLOW: Color = (40, 210, 255)
BLUE: Color = (235, 150, 70)


@dataclass(frozen=True, slots=True)
class Notification:
    message: str
    color: Color
    expires_at: float


class OpenCVUI:
    """Render the existing overlay and own OpenCV window operations."""

    def __init__(
        self,
        window_name: str,
        notification_duration: float = 2.0,
        show_fps: bool = True,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.window_name = window_name
        self.notification_duration = notification_duration
        self.show_fps = show_fps
        self._clock = clock
        self._notification: Notification | None = None
        self._notification_lock = threading.Lock()

    @property
    def notification_active(self) -> bool:
        with self._notification_lock:
            return (
                self._notification is not None
                and self._clock() < self._notification.expires_at
            )

    def show_notification(self, message: str, kind: NotificationKind = "info") -> None:
        colors = {"add": GREEN, "remove": RED, "info": BLUE}
        notification = Notification(
            message=message,
            color=colors[kind],
            expires_at=self._clock() + self.notification_duration,
        )
        with self._notification_lock:
            self._notification = notification

    def render(
        self,
        frame: np.ndarray,
        tracked_objects: tuple[TrackedObject, ...] | list[TrackedObject],
        checkout: CheckoutStateSnapshot,
        cart: CartSnapshot,
        fps: float,
        device: str,
        inference_time_ms: float,
        debug: bool,
    ) -> None:
        """Render one complete application frame in place."""
        self._draw_checkout_zone(frame, checkout)
        self._draw_tracked_objects(frame, tracked_objects, checkout, debug)
        self._draw_cart_panel(frame, cart)
        self._draw_header(
            frame,
            fps=fps,
            device=device,
            tracked_count=len(tracked_objects),
            inference_time_ms=inference_time_ms,
            debug=debug,
        )
        self._draw_footer(frame, debug)
        self._draw_notification(frame)

    def present(self, frame: np.ndarray) -> None:
        """Display a rendered frame in the configured window."""
        cv2.imshow(self.window_name, frame)

    @staticmethod
    def poll_key(delay_ms: int = 1) -> int:
        """Return a normalized OpenCV key code."""
        return cv2.waitKey(delay_ms) & 0xFF

    @staticmethod
    def close() -> None:
        """Close all OpenCV windows owned by this process."""
        cv2.destroyAllWindows()

    def _draw_header(
        self,
        frame: np.ndarray,
        fps: float,
        device: str,
        tracked_count: int,
        inference_time_ms: float,
        debug: bool,
    ) -> None:
        frame_width = frame.shape[1]
        header_height = 76
        _draw_translucent_rect(frame, (0, 0), (frame_width, header_height), DARK, 0.86)
        cv2.putText(
            frame,
            "Smart Retail Checkout",
            (18, 31),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.86,
            WHITE,
            2,
            cv2.LINE_AA,
        )

        stats_parts = []
        if self.show_fps:
            stats_parts.append(f"FPS {fps:.1f}")
        stats_parts.extend((f"Device {device.upper()}", f"Tracks {tracked_count}"))
        stats = "  |  ".join(stats_parts)
        if debug:
            stats += f"  |  Inference {inference_time_ms:.1f} ms"
        stats = _fit_text(frame, stats, frame_width - 36, 0.55, 1)
        cv2.putText(
            frame,
            stats,
            (19, 59),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            MUTED,
            1,
            cv2.LINE_AA,
        )

    def _draw_checkout_zone(
        self,
        frame: np.ndarray,
        checkout: CheckoutStateSnapshot,
    ) -> None:
        frame_height, frame_width = frame.shape[:2]
        x1, y1, x2, y2 = checkout.zone.pixel_bounds(frame_width, frame_height)
        _draw_translucent_rect(frame, (x1, y1), (x2, y2), GREEN, 0.12)
        cv2.rectangle(frame, (x1, y1), (x2, y2), GREEN, 3, cv2.LINE_AA)

        label = "CHECKOUT ZONE"
        base_scale = 0.68
        available_width = max(1, x2 - x1 - 28)
        base_width = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, base_scale, 2)[0][
            0
        ]
        label_scale = base_scale * min(1.0, available_width / base_width)
        label_thickness = 2 if label_scale >= 0.55 else 1
        (text_width, text_height), _ = cv2.getTextSize(
            label, cv2.FONT_HERSHEY_SIMPLEX, label_scale, label_thickness
        )
        label_top = max(y1 + 8, 80)
        _draw_translucent_rect(
            frame,
            (x1 + 8, label_top),
            (x1 + text_width + 22, label_top + text_height + 16),
            DARK,
            0.82,
        )
        cv2.putText(
            frame,
            label,
            (x1 + 15, label_top + text_height + 7),
            cv2.FONT_HERSHEY_SIMPLEX,
            label_scale,
            GREEN,
            label_thickness,
            cv2.LINE_AA,
        )

    def _draw_tracked_objects(
        self,
        frame: np.ndarray,
        tracked_objects: tuple[TrackedObject, ...] | list[TrackedObject],
        checkout: CheckoutStateSnapshot,
        debug: bool,
    ) -> None:
        frame_height, frame_width = frame.shape[:2]
        for tracked_object in tracked_objects:
            x1, y1, x2, y2 = tracked_object.bbox
            id_label = (
                str(tracked_object.track_id)
                if tracked_object.track_id is not None
                else "pending"
            )
            label = (
                f"{tracked_object.class_name.title()}  |  ID {id_label}  |  "
                f"{tracked_object.confidence:.2f}"
            )
            label = _fit_text(frame, label, max(120, frame_width - x1 - 10), 0.58, 2)

            cv2.rectangle(frame, (x1, y1), (x2, y2), YELLOW, 2, cv2.LINE_AA)
            self._draw_box_label(frame, label, x1, y1)

            center_x, center_y = (round(value) for value in tracked_object.centroid)
            cv2.circle(frame, (center_x, center_y), 5, RED, -1, cv2.LINE_AA)

            if debug:
                state = self._zone_state(
                    tracked_object,
                    checkout,
                    frame_width,
                    frame_height,
                )
                status_color = GREEN if state is ZoneState.INSIDE else WHITE
                cv2.putText(
                    frame,
                    state.value.upper(),
                    (center_x + 9, center_y - 8),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.52,
                    status_color,
                    2,
                    cv2.LINE_AA,
                )

    def _draw_box_label(
        self,
        frame: np.ndarray,
        label: str,
        x: int,
        y: int,
    ) -> None:
        (text_width, text_height), baseline = cv2.getTextSize(
            label, cv2.FONT_HERSHEY_SIMPLEX, 0.58, 2
        )
        text_y = y - 9
        if text_y - text_height < 78:
            text_y = y + text_height + 9

        left = max(0, x)
        top = max(76, text_y - text_height - 6)
        right = min(frame.shape[1] - 1, left + text_width + 12)
        bottom = min(frame.shape[0] - 1, text_y + baseline + 5)
        _draw_translucent_rect(frame, (left, top), (right, bottom), DARK, 0.86)
        cv2.putText(
            frame,
            label,
            (left + 6, min(text_y, frame.shape[0] - 5)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.58,
            WHITE,
            2,
            cv2.LINE_AA,
        )

    def _draw_cart_panel(self, frame: np.ndarray, cart: CartSnapshot) -> None:
        frame_height, frame_width = frame.shape[:2]
        panel_x = 16
        panel_y = 88
        panel_width = min(480, max(280, round(frame_width * 0.34)))
        panel_width = min(panel_width, frame_width - 32)
        items = cart.items
        visible_rows = max(1, len(items))
        panel_height = 150 + visible_rows * 31
        panel_height = min(panel_height, frame_height - panel_y - 58)

        x2 = panel_x + panel_width
        y2 = panel_y + panel_height
        _draw_translucent_rect(frame, (panel_x, panel_y), (x2, y2), DARK, 0.82)
        cv2.rectangle(
            frame, (panel_x, panel_y), (x2, y2), (75, 88, 102), 1, cv2.LINE_AA
        )

        cv2.putText(
            frame,
            "Shopping Cart",
            (panel_x + 16, panel_y + 31),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.72,
            WHITE,
            2,
            cv2.LINE_AA,
        )

        product_x = panel_x + 16
        quantity_x = x2 - 114
        amount_right = x2 - 16
        header_y = panel_y + 63
        cv2.putText(
            frame,
            "Product",
            (product_x, header_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            MUTED,
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            "Qty",
            (quantity_x, header_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            MUTED,
            1,
            cv2.LINE_AA,
        )
        _put_right_aligned_text(frame, "Amount", amount_right, header_y, 0.48, MUTED, 1)
        cv2.line(
            frame,
            (product_x, header_y + 10),
            (amount_right, header_y + 10),
            (85, 98, 112),
            1,
            cv2.LINE_AA,
        )

        row_y = header_y + 38
        if not items:
            cv2.putText(
                frame,
                "Cart is empty",
                (product_x, row_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                MUTED,
                1,
                cv2.LINE_AA,
            )
        else:
            product_width = max(80, quantity_x - product_x - 16)
            for item in items:
                product_name = _fit_text(
                    frame, item.product_name, product_width, 0.54, 1
                )
                cv2.putText(
                    frame,
                    product_name,
                    (product_x, row_y),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.54,
                    WHITE,
                    1,
                    cv2.LINE_AA,
                )
                cv2.putText(
                    frame,
                    str(item.quantity),
                    (quantity_x + 10, row_y),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.54,
                    WHITE,
                    1,
                    cv2.LINE_AA,
                )
                _draw_money(frame, item.subtotal, amount_right, row_y, WHITE)
                row_y += 31

        divider_y = min(row_y + 13, y2 - 48)
        cv2.line(
            frame,
            (product_x, divider_y),
            (amount_right, divider_y),
            (130, 142, 154),
            1,
            cv2.LINE_AA,
        )
        total_y = min(divider_y + 32, y2 - 14)
        cv2.putText(
            frame,
            "TOTAL",
            (product_x, total_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.62,
            WHITE,
            2,
            cv2.LINE_AA,
        )
        _draw_money(frame, cart.total, amount_right, total_y, GREEN, 0.62, 2)

    def _draw_footer(self, frame: np.ndarray, debug: bool) -> None:
        frame_height, frame_width = frame.shape[:2]
        footer_height = 46
        _draw_translucent_rect(
            frame,
            (0, frame_height - footer_height),
            (frame_width, frame_height),
            DARK,
            0.88,
        )
        debug_state = "ON" if debug else "OFF"
        controls = f"Q: Quit     R: Reset Cart     D: Debug ({debug_state})"
        controls = _fit_text(frame, controls, frame_width - 36, 0.58, 1)
        cv2.putText(
            frame,
            controls,
            (18, frame_height - 16),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.58,
            WHITE,
            1,
            cv2.LINE_AA,
        )

    def _draw_notification(self, frame: np.ndarray) -> None:
        notification = self._current_notification()
        if notification is None:
            return

        frame_height, frame_width = frame.shape[:2]
        message = _fit_text(frame, notification.message, frame_width - 80, 0.68, 2)
        (text_width, text_height), _ = cv2.getTextSize(
            message, cv2.FONT_HERSHEY_SIMPLEX, 0.68, 2
        )
        box_width = text_width + 34
        x1 = max(20, (frame_width - box_width) // 2)
        y2 = frame_height - 64
        y1 = y2 - text_height - 26
        _draw_translucent_rect(frame, (x1, y1), (x1 + box_width, y2), DARK, 0.92)
        cv2.rectangle(
            frame,
            (x1, y1),
            (x1 + box_width, y2),
            notification.color,
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            message,
            (x1 + 17, y2 - 13),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.68,
            notification.color,
            2,
            cv2.LINE_AA,
        )

    @staticmethod
    def _zone_state(
        tracked_object: TrackedObject,
        checkout: CheckoutStateSnapshot,
        frame_width: int,
        frame_height: int,
    ) -> ZoneState:
        if tracked_object.track_id is not None:
            state = checkout.state_for(tracked_object.track_id)
            if state is not None:
                return state
        return checkout.zone.classify(
            tracked_object.centroid,
            frame_width,
            frame_height,
        )

    def _current_notification(self) -> Notification | None:
        with self._notification_lock:
            notification = self._notification
            if notification is not None and self._clock() >= notification.expires_at:
                self._notification = None
                return None
            return notification


def _draw_translucent_rect(
    frame: np.ndarray,
    top_left: tuple[int, int],
    bottom_right: tuple[int, int],
    color: Color,
    alpha: float,
) -> None:
    frame_height, frame_width = frame.shape[:2]
    x1 = max(0, min(frame_width, top_left[0]))
    y1 = max(0, min(frame_height, top_left[1]))
    x2 = max(0, min(frame_width, bottom_right[0]))
    y2 = max(0, min(frame_height, bottom_right[1]))
    if x2 <= x1 or y2 <= y1:
        return

    region = frame[y1:y2, x1:x2]
    overlay = region.copy()
    overlay[:] = color
    cv2.addWeighted(overlay, alpha, region, 1.0 - alpha, 0.0, region)


def _fit_text(
    frame: np.ndarray,
    text: str,
    max_width: int,
    font_scale: float,
    thickness: int,
) -> str:
    if max_width <= 0:
        return ""
    full_width = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)[
        0
    ][0]
    if full_width <= max_width:
        return text

    candidate = text
    while candidate:
        fitted_text = candidate.rstrip() + "..."
        width = cv2.getTextSize(
            fitted_text,
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            thickness,
        )[0][0]
        if width <= max_width:
            return fitted_text
        candidate = candidate[:-1]
    return ""


def _put_right_aligned_text(
    frame: np.ndarray,
    text: str,
    right_x: int,
    baseline_y: int,
    font_scale: float,
    color: Color,
    thickness: int,
) -> None:
    text_width = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)[
        0
    ][0]
    cv2.putText(
        frame,
        text,
        (right_x - text_width, baseline_y),
        cv2.FONT_HERSHEY_SIMPLEX,
        font_scale,
        color,
        thickness,
        cv2.LINE_AA,
    )


def _draw_money(
    frame: np.ndarray,
    amount: int,
    right_x: int,
    baseline_y: int,
    color: Color,
    font_scale: float = 0.54,
    thickness: int = 1,
) -> None:
    number = str(amount)
    (number_width, text_height), _ = cv2.getTextSize(
        number, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness
    )
    symbol_width = max(9, round(text_height * 0.70))
    gap = 4
    start_x = right_x - number_width - symbol_width - gap
    _draw_rupee_symbol(
        frame,
        x=start_x,
        baseline_y=baseline_y,
        height=text_height,
        width=symbol_width,
        color=color,
        thickness=max(1, thickness),
    )
    cv2.putText(
        frame,
        number,
        (start_x + symbol_width + gap, baseline_y),
        cv2.FONT_HERSHEY_SIMPLEX,
        font_scale,
        color,
        thickness,
        cv2.LINE_AA,
    )


def _draw_rupee_symbol(
    frame: np.ndarray,
    x: int,
    baseline_y: int,
    height: int,
    width: int,
    color: Color,
    thickness: int,
) -> None:
    top = baseline_y - height
    middle = top + height // 2
    cv2.line(frame, (x, top), (x + width, top), color, thickness, cv2.LINE_AA)
    cv2.line(
        frame,
        (x, top + max(2, height // 4)),
        (x + width, top + max(2, height // 4)),
        color,
        thickness,
        cv2.LINE_AA,
    )
    cv2.line(frame, (x, top), (x, middle), color, thickness, cv2.LINE_AA)
    cv2.line(
        frame,
        (x + width, top),
        (x + 1, middle),
        color,
        thickness,
        cv2.LINE_AA,
    )
    cv2.line(
        frame,
        (x + 1, middle),
        (x + width, baseline_y),
        color,
        thickness,
        cv2.LINE_AA,
    )
