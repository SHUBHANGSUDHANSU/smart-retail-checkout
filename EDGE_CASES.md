# Edge-case behavior

Phase 7 hardens the existing V1 pipeline without adding appearance-based
re-identification or synthetic tracking IDs.

| Scenario | Expected behavior | Current behavior / solution |
|---|---|---|
| Repeated counting | One physical track is counted once while it remains in the cart. | `CartService` is keyed by track ID. Duplicate `add_item` calls are ignored. |
| Tracker ID changes | Do not pretend a replacement ID is the original object. Avoid duplicate cart entries. | A newly observed ID establishes a zone baseline and emits no event. The missing original ID keeps its state during the grace period, then expires. No fake ID or cross-ID transfer is created. |
| Temporary hand occlusion | Brief loss must not immediately add or remove an item. | ByteTrack keeps lost tracks for 60 frames. Application state has a longer 90-frame expiry grace period; recovery with the same ID refreshes it. |
| Missing YOLO detection | A missing frame must not generate a crossing. | No zone event is produced. Any pending transition is cancelled because confirmation requires consecutive visible frames. |
| Object disappears while inside | Do not instantly corrupt the cart, but do not retain stale state forever. | The exact cart track remains during the 90-frame grace period. If the same ID does not return, the track expires and that exact cart entry is removed. |
| Multiple objects of the same class | Count each physical tracked object and aggregate the visible quantity. | Each ID has its own cart entry; `get_items()` aggregates class quantities and integer totals. |
| Object hovers around boundary | Avoid repeated `ENTER`/`EXIT` events from centroid jitter. | The zone uses a 1.5% normalized hysteresis margin and requires three consecutive frames before confirming a transition. |
| Low-confidence detections | Weak detections may help tracking but must not create noisy cart events. | ByteTrack receives detections down to 0.10. UI and zone logic only receive results at or above 0.45. |
| Unsupported YOLO classes | Unsupported objects must not enter the cart. | YOLO inference is filtered to configured class IDs. `CartService` independently rejects unsupported classes. |
| Webcam read failure | Recover from brief startup/read failures, then fail clearly and release resources. | Camera reads retry up to 30 times with a short delay. Persistent failure returns an error; `finally` releases the camera and closes OpenCV windows. |
| Empty result tensors | Continue rendering without exceptions. | Empty or missing box collections normalize to an empty tracked-object list. |
| `boxes.id` is `None` | Continue displaying a pending object without inventing an ID. | The normalized track ID is `None`; app logic skips zone/cart state for that observation. |
| Reset while tracks remain active | Cart stays empty instead of being immediately repopulated by a pending transition. | `R` clears cart and all zone stable/pending/lifecycle state. Active objects establish a fresh baseline on their next observation. |
| Quit application | Camera and windows close cleanly. | `Q`/`q` returns through a `finally` cleanup. Ctrl+C is caught and uses the same cleanup without a traceback. |
| MPS incompatibility | Use MPS when it works and CPU otherwise. | Startup checks MPS build/availability. A runtime MPS exception moves the same model to CPU and retries once. Genuine CPU errors still surface. |
| Variable webcam resolution | Zone and UI remain usable without fixed pixel coordinates. | Zone geometry is normalized; header, zone, cart panel, footer, truncation, and notifications derive dimensions from each frame. Tests cover 1280×720 and 640×480. |
| Accidental event oscillation | One stable crossing produces one event. | Hysteresis, three-frame confirmation, pending cancellation on missing frames, and per-ID stable state suppress oscillation. |

## Intentional V1 limitations

- ByteTrack is motion-based, not appearance-based re-identification. If an ID
  changes during a long occlusion, the system does not guess that two IDs are
  the same physical item.
- A replacement ID first seen inside does not emit `ENTER`; the item must be
  observed outside and then cross in. This prevents false duplicate adds.
- Expiry is frame-based. Ninety frames lasts longer at low FPS than at high FPS.
- If an item remains physically inside but cannot be detected beyond the full
  grace period, its stale cart entry is removed rather than retained forever.
