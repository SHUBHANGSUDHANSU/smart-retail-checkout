"""Tests for checkout event lifecycle and persisted-domain invariants."""

import pytest

from smart_retail.checkout.event_engine import CheckoutEventEngine
from smart_retail.domain.events import (
    CartEvent,
    CartEventType,
    CheckoutEventType,
    ZoneState,
)
from smart_retail.domain.models import CheckoutSession, Product


def test_enter_hold_and_exit_emit_one_event_per_transition(
    event_engine: CheckoutEventEngine,
    make_tracked_object,
) -> None:
    outside = make_tracked_object(7, 500)
    inside = make_tracked_object(7, 800)

    assert event_engine.process_frame([outside], 1000, 500, 0).events == ()
    assert event_engine.process_frame([inside], 1000, 500, 1).events == ()
    entered = event_engine.process_frame([inside], 1000, 500, 2).events
    assert [event.event_type for event in entered] == [CheckoutEventType.ENTER]
    assert event_engine.process_frame([inside], 1000, 500, 3).events == ()
    assert event_engine.process_frame([outside], 1000, 500, 4).events == ()
    exited = event_engine.process_frame([outside], 1000, 500, 5).events
    assert [event.event_type for event in exited] == [CheckoutEventType.EXIT]


def test_confirmed_event_includes_product_class_and_clock_timestamp(
    event_engine: CheckoutEventEngine,
    make_tracked_object,
) -> None:
    outside = make_tracked_object(7, 500)
    inside = make_tracked_object(7, 800, class_name="apple")

    event_engine.process_frame([outside], 1000, 500, 0)
    event_engine.process_frame([inside], 1000, 500, 1)
    event = event_engine.process_frame([inside], 1000, 500, 2).events[0]

    assert event.event_type is CheckoutEventType.ENTER
    assert event.product_class == "apple"
    assert event.timestamp == 123.5


def test_tracks_keep_independent_state(
    event_engine: CheckoutEventEngine,
    make_tracked_object,
) -> None:
    event_engine.process_frame([make_tracked_object(7, 800)], 1000, 500, 0)
    event_engine.process_frame(
        [make_tracked_object(12, 500, class_name="cup")], 1000, 500, 0
    )

    assert dict(event_engine.track_states) == {
        7: ZoneState.INSIDE,
        12: ZoneState.OUTSIDE,
    }


def test_first_sighting_establishes_baseline_without_event(
    event_engine: CheckoutEventEngine,
    make_tracked_object,
) -> None:
    update = event_engine.process_frame([make_tracked_object(7, 800)], 1000, 500, 0)

    assert update.events == ()
    assert event_engine.state_for(7) is ZoneState.INSIDE


def test_fragmented_id_inside_does_not_repeat_enter(
    event_engine: CheckoutEventEngine,
    make_tracked_object,
) -> None:
    outside = make_tracked_object(7, 500)
    inside = make_tracked_object(7, 800)

    event_engine.process_frame([outside], 1000, 500, 0)
    event_engine.process_frame([inside], 1000, 500, 1)
    entered = event_engine.process_frame([inside], 1000, 500, 2).events
    fragmented = event_engine.process_frame([make_tracked_object(8, 810)], 1000, 500, 3)

    assert [event.event_type for event in entered] == [CheckoutEventType.ENTER]
    assert fragmented.events == ()


def test_missing_track_is_preserved_during_grace_then_expires(
    event_engine: CheckoutEventEngine,
    make_tracked_object,
) -> None:
    event_engine.process_frame([make_tracked_object(7, 500)], 1000, 500, 0)

    assert event_engine.process_frame([], 1000, 500, 2).expired_track_ids == ()
    assert event_engine.state_for(7) is ZoneState.OUTSIDE
    assert event_engine.process_frame([], 1000, 500, 3).expired_track_ids == (7,)
    assert event_engine.state_for(7) is None


def test_reappearing_track_resets_expiry_clock(
    event_engine: CheckoutEventEngine,
    make_tracked_object,
) -> None:
    event_engine.process_frame([make_tracked_object(7, 500)], 1000, 500, 0)
    assert event_engine.process_frame([], 1000, 500, 2).expired_track_ids == ()
    event_engine.process_frame([make_tracked_object(7, 500)], 1000, 500, 2)

    assert event_engine.process_frame([], 1000, 500, 4).expired_track_ids == ()
    assert event_engine.process_frame([], 1000, 500, 5).expired_track_ids == (7,)


def test_missing_frame_breaks_consecutive_transition_confirmation(
    event_engine: CheckoutEventEngine,
    make_tracked_object,
) -> None:
    outside = make_tracked_object(7, 500)
    inside = make_tracked_object(7, 800)

    event_engine.process_frame([outside], 1000, 500, 0)
    assert event_engine.process_frame([inside], 1000, 500, 1).events == ()
    assert event_engine.process_frame([], 1000, 500, 2).events == ()
    assert event_engine.process_frame([inside], 1000, 500, 3).events == ()
    entered = event_engine.process_frame([inside], 1000, 500, 4).events

    assert [event.event_type for event in entered] == [CheckoutEventType.ENTER]


def test_reset_clears_stable_pending_and_expiry_state(
    event_engine: CheckoutEventEngine,
    make_tracked_object,
) -> None:
    event_engine.process_frame([make_tracked_object(7, 800)], 1000, 500, 0)
    event_engine.process_frame([make_tracked_object(7, 500)], 1000, 500, 1)
    event_engine.process_frame([make_tracked_object(8, 500)], 1000, 500, 0)
    event_engine.process_frame([make_tracked_object(8, 800)], 1000, 500, 1)

    event_engine.reset()
    assert dict(event_engine.track_states) == {}
    assert event_engine._pending_states == {}
    assert event_engine._pending_counts == {}
    assert event_engine._last_seen_frames == {}

    after_expiry = event_engine.process_frame([], 1000, 500, 4)
    assert after_expiry.expired_track_ids == ()
    assert dict(event_engine.track_states) == {}

    outside = [make_tracked_object(track_id, 500) for track_id in (7, 8)]
    inside = [make_tracked_object(track_id, 800) for track_id in (7, 8)]
    baseline = event_engine.process_frame(outside, 1000, 500, 5)
    assert baseline.events == ()
    assert dict(event_engine.track_states) == {
        7: ZoneState.OUTSIDE,
        8: ZoneState.OUTSIDE,
    }

    first_inside = event_engine.process_frame(inside, 1000, 500, 6)
    assert first_inside.events == ()
    confirmed = event_engine.process_frame(inside, 1000, 500, 7)
    assert [event.track_id for event in confirmed.events] == [7, 8]
    assert all(
        event.event_type is CheckoutEventType.ENTER for event in confirmed.events
    )


def test_observation_without_id_does_not_create_state(
    event_engine: CheckoutEventEngine,
    make_tracked_object,
) -> None:
    update = event_engine.process_frame([make_tracked_object(None, 800)], 1000, 500, 0)

    assert update.events == ()
    assert dict(event_engine.track_states) == {}


def test_checkout_snapshot_is_immutable_and_detached_from_future_frames(
    event_engine: CheckoutEventEngine,
    make_tracked_object,
) -> None:
    outside = make_tracked_object(7, 500)
    inside = make_tracked_object(7, 800)

    event_engine.process_frame([outside], 1000, 500, 0)
    snapshot = event_engine.get_snapshot()
    event_engine.process_frame([inside], 1000, 500, 1)
    event_engine.process_frame([inside], 1000, 500, 2)

    assert snapshot.state_for(7) is ZoneState.OUTSIDE
    assert event_engine.state_for(7) is ZoneState.INSIDE
    with pytest.raises(TypeError):
        snapshot.track_states[7] = ZoneState.INSIDE


@pytest.mark.parametrize(
    "kwargs",
    [
        {"confirmation_frames": 0},
        {"expiry_grace_frames": 0},
    ],
)
def test_event_engine_rejects_nonpositive_lifecycle_configuration(
    checkout_zone,
    kwargs: dict[str, int],
) -> None:
    values = {"confirmation_frames": 1, "expiry_grace_frames": 3}
    values.update(kwargs)

    with pytest.raises(ValueError, match="positive integer"):
        CheckoutEventEngine(checkout_zone, **values)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"event_id": 0}, "IDs must be positive"),
        ({"event_type": CartEventType.RESET, "track_id": 7}, "cannot reference"),
        ({"event_type": CartEventType.ADD, "unit_price": None}, "require product"),
        ({"event_type": CartEventType.ADD, "unit_price": -1}, "cannot be negative"),
    ],
)
def test_cart_event_rejects_invalid_history(
    kwargs: dict[str, object], message: str
) -> None:
    values = {
        "event_id": 1,
        "session_id": 1,
        "timestamp": 100.0,
        "track_id": 7,
        "product_id": "bottle",
        "event_type": CartEventType.ADD,
        "unit_price": 40,
    }
    values.update(kwargs)

    with pytest.raises(ValueError, match=message):
        CartEvent(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"product_id": ""}, "Product ID cannot be empty"),
        ({"name": "   "}, "Product name cannot be empty"),
        ({"unit_price": 40.0}, "nonnegative integer"),
        ({"unit_price": -1}, "nonnegative integer"),
    ],
)
def test_product_rejects_invalid_catalog_values(
    kwargs: dict[str, object], message: str
) -> None:
    values = {"product_id": "bottle", "name": "Water Bottle", "unit_price": 40}
    values.update(kwargs)

    with pytest.raises(ValueError, match=message):
        Product(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"session_id": 0}, "ID must be positive"),
        ({"ended_at": 99.0}, "cannot end before it starts"),
        ({"final_total": -1}, "cannot be negative"),
        ({"ended_at": 110.0, "final_total": None}, "must be set together"),
        ({"ended_at": None, "final_total": 40}, "must be set together"),
    ],
)
def test_checkout_session_rejects_invalid_persisted_values(
    kwargs: dict[str, object], message: str
) -> None:
    values = {
        "session_id": 1,
        "started_at": 100.0,
        "ended_at": 110.0,
        "final_total": 40,
    }
    values.update(kwargs)

    with pytest.raises(ValueError, match=message):
        CheckoutSession(**values)  # type: ignore[arg-type]
