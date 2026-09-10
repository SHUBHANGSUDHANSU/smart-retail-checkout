# Demo runbook

## Choose the right mode

| Mode | Command | Camera/YOLO | Purpose |
|---|---|---|---|
| Vision | `smart-retail` | Active | Prove detection, tracking, zone transitions, and OpenCV UI |
| API only | `smart-retail-api` | Disabled | Backend/API development and container use |
| Demo | `./scripts/run-demo.sh` | Disabled | Present real backend/frontend behavior with clearly synthetic commands |

The OpenCV window is the vision surface. React is the operations surface. Raw
video is intentionally not sent to the browser.

## Hardware-free portfolio demo

Install Python and frontend dependencies as described in the root README, then:

```bash
./scripts/run-demo.sh
```

Open `http://localhost:5173`. Confirm that the navigation displays **DEMO
MODE** and the Dashboard says computer vision is inactive.

Run this deterministic scenario:

1. Add one Water Bottle from Demo controls.
2. Confirm Current Cart changes immediately through SSE.
3. Add one Apple and a second Water Bottle.
4. Confirm Water Bottle is aggregated to quantity two.
5. Remove one Water Bottle and observe a `REMOVE` event.
6. Open System and show readiness plus business metrics. Camera/model/vision
   should say `Disabled`, not `Ready`.
7. Return to Dashboard and reset the cart through the normal confirmation flow.
8. Stop the helper with `Ctrl+C`; graceful shutdown closes the active session.
9. Restart the helper and open Sessions to show the completed persisted session.

The helper defaults to `data/smart_retail_demo.db`, isolating the walkthrough
from the normal `data/smart_retail.db`. Delete or move that ignored local file
before recording if a fresh history is desired.

## Vision demo

1. Grant Camera permission to Terminal or the IDE in macOS Privacy & Security.
2. Run `smart-retail`, then run `npm run dev` inside `frontend/`.
3. Put one supported object outside the checkout zone.
4. Show its bounding box, confidence, and stable ByteTrack ID.
5. Move its centroid into the checkout zone and wait for the confirmed crossing.
6. Show one OpenCV notification and the immediate React cart/event update.
7. Add a second physical object, then move the first back outside.
8. Toggle debug with `D`, reset with `R`, and exit cleanly with `Q`.

Do not describe a demo-mode result as a webcam test. The two modes prove
different boundaries.

## 30–60 second recording outline

1. **0–8 s:** show the OpenCV frame, product labels, confidence, IDs, and zone.
2. **8–20 s:** cross one product into checkout; cut to the React cart updating.
3. **20–30 s:** add a second item, remove the first, and show Recent Events.
4. **30–40 s:** open Sessions and one Session Detail page.
5. **40–50 s:** open System to show readiness, metrics, and SSE `Live` status.
6. **50–60 s:** finish on the README architecture diagram and limitations.

Keep the camera and dashboard visible enough that the relationship is clear.
Avoid personal information, unrelated windows, secrets, and raw terminal paths
in the recording.

## Screenshot checklist

Capture real application states at a readable desktop viewport:

1. Dashboard with a populated cart and visible realtime status.
2. Recent Events containing `ADD`, `REMOVE`, and `RESET` where practical.
3. Sessions history with active and completed states.
4. Session Detail with summary and event history.
5. System page with readiness components and operational metrics.
6. Native OpenCV window with supported detections, track IDs, and checkout zone.

Use the filenames and placement guidance in [images/README.md](images/README.md).
When using synthetic data, keep the **DEMO MODE** badge visible in the image.

## Troubleshooting

- **Camera does not open:** verify macOS Camera permission and camera index.
- **Frontend says unavailable:** verify `GET http://localhost:8000/health` and
  `VITE_API_BASE_URL`.
- **Demo badge is absent:** confirm `SMART_RETAIL_DEMO_MODE=true` in the API
  process, not only the frontend shell.
- **SSE is reconnecting:** inspect `/api/v1/stream`, backend logs, and the
  configured CORS origin.
- **First model start is slow:** Ultralytics may download `yolov8n.pt` once.
