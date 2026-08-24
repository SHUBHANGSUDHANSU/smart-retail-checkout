"""Stateful conversion of tracked observations into checkout events."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from smart_retail.checkout.zone import CheckoutZone
from smart_retail.domain.events import CheckoutEvent, CheckoutEventType, ZoneState
from smart_retail.domain.models import TrackedObject


@dataclass(frozen=True, slots=True)
class CheckoutUpdate:
    """Events and expirations produced while processing one frame."""

    events: tuple[CheckoutEvent, ...]
    expired_track_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class CheckoutStateSnapshot:
    """Immutable zone state used after releasing the checkout command lock."""

    zone: CheckoutZone
    track_states: Mapping[int, ZoneState]

    def state_for(self, track_id: int) -> ZoneState | None:
        return self.track_states.get(track_id)


class CheckoutEventEngine:
    """Confirm per-track zone transitions and manage missing-track expiry."""

    def __init__(
        self,
        zone: CheckoutZone,
        confirmation_frames: int,
        expiry_grace_frames: int,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not isinstance(confirmation_frames, int) or confirmation_frames < 1:
            raise ValueError("Zone confirmation frames must be a positive integer.")
        if not isinstance(expiry_grace_frames, int) or expiry_grace_frames < 1:
            raise ValueError("Track expiry grace frames must be a positive integer.")

        self.zone = zone
        self.confirmation_frames = confirmation_frames
        self.expiry_grace_frames = expiry_grace_frames
        self._clock = clock
        self._track_states: dict[int, ZoneState] = {}
        self._pending_states: dict[int, ZoneState] = {}
        self._pending_counts: dict[int, int] = {}
        self._last_seen_frames: dict[int, int] = {}

    @property
    def track_states(self) -> Mapping[int, ZoneState]:
        """Expose a read-only view for diagnostics and presentation."""
        return MappingProxyType(self._track_states)

    def state_for(self, track_id: int) -> ZoneState | None:
        """Return the stable state currently associated with a track."""
        return self._track_states.get(track_id)

    def process_frame(
        self,
        tracked_objects: Iterable[TrackedObject],
        frame_width: int,
        frame_height: int,
        frame_number: int,
    ) -> CheckoutUpdate:
        """Process all tracked observations and expire stale lifecycle state."""
        if frame_number < 0:
            raise ValueError("Frame number cannot be negative.")

        events: list[CheckoutEvent] = []
        active_track_ids: set[int] = set()
        for tracked_object in tracked_objects:
            if tracked_object.track_id is None:
                continue
            active_track_ids.add(tracked_object.track_id)
            event = self.process_track(
                tracked_object,
                frame_width=frame_width,
                frame_height=frame_height,
                frame_number=frame_number,
            )
            if event is not None:
                events.append(event)

        expired = self.expire_missing_tracks(active_track_ids, frame_number)
        return CheckoutUpdate(tuple(events), tuple(expired))

    def process_track(
        self,
        tracked_object: TrackedObject,
        frame_width: int,
        frame_height: int,
        frame_number: int,
    ) -> CheckoutEvent | None:
        """Update one identified track and return one confirmed event at most."""
        track_id = tracked_object.track_id
        if track_id is None:
            return None
        if frame_number < 0:
            raise ValueError("Frame number cannot be negative.")

        self._last_seen_frames[track_id] = frame_number
        previous_state = self._track_states.get(track_id)
        current_state = self.zone.classify_for_previous_state(
            tracked_object.centroid,
            frame_width,
            frame_height,
            previous_state,
        )

        # An unknown ID needs observations on both sides before it can cross.
        if previous_state is None:
            self._track_states[track_id] = current_state
            return None

        if current_state is previous_state:
            self._clear_pending(track_id)
            return None

        if self._pending_states.get(track_id) is current_state:
            self._pending_counts[track_id] += 1
        else:
            self._pending_states[track_id] = current_state
            self._pending_counts[track_id] = 1

        if self._pending_counts[track_id] < self.confirmation_frames:
            return None

        self._track_states[track_id] = current_state
        self._clear_pending(track_id)
        event_type = (
            CheckoutEventType.ENTER
            if current_state is ZoneState.INSIDE
            else CheckoutEventType.EXIT
        )
        return CheckoutEvent(
            event_type=event_type,
            track_id=track_id,
            product_class=tracked_object.class_name,
            timestamp=self._clock(),
        )

    def expire_missing_tracks(
        self,
        active_track_ids: set[int],
        current_frame: int,
    ) -> list[int]:
        """Discard tracks absent for the configured grace period."""
        if current_frame < 0:
            raise ValueError("Current frame cannot be negative.")

        for track_id in set(self._pending_states) - active_track_ids:
            self._clear_pending(track_id)

        expired_track_ids = sorted(
            track_id
            for track_id, last_seen_frame in self._last_seen_frames.items()
            if track_id not in active_track_ids
            and current_frame - last_seen_frame >= self.expiry_grace_frames
        )
        for track_id in expired_track_ids:
            self._track_states.pop(track_id, None)
            self._last_seen_frames.pop(track_id, None)
            self._clear_pending(track_id)
        return expired_track_ids

    def reset(self) -> None:
        """Clear stable, pending, and missing-track lifecycle state."""
        self._track_states.clear()
        self._pending_states.clear()
        self._pending_counts.clear()
        self._last_seen_frames.clear()

    def get_snapshot(self) -> CheckoutStateSnapshot:
        """Copy stable track state for lock-free presentation reads."""
        return CheckoutStateSnapshot(
            zone=self.zone,
            track_states=MappingProxyType(dict(self._track_states)),
        )

    def _clear_pending(self, track_id: int) -> None:
        self._pending_states.pop(track_id, None)
        self._pending_counts.pop(track_id, None)
