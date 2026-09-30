<div align="center">

# 🔥 Fire & Smoke Detection — Deployment

> **Real-time fire and smoke detection from a camera or video source, powered by a custom-trained Ultralytics YOLO model.**

[![YOLO](https://img.shields.io/badge/Ultralytics-YOLO-00FFFF?style=for-the-badge)](https://ultralytics.com/)
[![OpenCV](https://img.shields.io/badge/OpenCV-Video-5C3EE8?style=for-the-badge&logo=opencv)](https://opencv.org/)
[![Docker](https://img.shields.io/badge/Docker-Service-2496ED?style=for-the-badge&logo=docker)](../../../docs/ai-detector-services.md)

</div>

---

## 📌 Overview

This project detects fire and smoke from a camera or video source using a trained Ultralytics YOLO model. It runs in two ways:

- **Service (`headless.py`)** — the Docker container used by SFLMS. No window: it watches the whole frame, sends confirmed alerts to the backend, serves a live MJPEG view, and follows the per-camera model switch from the admin console. How to run it is in [`docs/ai-detector-services.md`](../../../docs/ai-detector-services.md).
- **Local demo (`Main.py`)** — an OpenCV window for testing on a laptop, with an optional hand-drawn ROI.

| Module | Responsibility |
| --- | --- |
| `headless.py` | Service entry point (the container's `CMD`). |
| `sflms_client.py` | Writes the alert snapshot to protected media and posts the event to the SFLMS ingestion API. |
| `camera_settings.py` | Polls the backend every `CONFIG_REFRESH_SECONDS` (30 s) for whether the `fire_smoke` model is switched on for this camera. |
| `stream_server.py` | MJPEG live view: `/stream`, `/snapshot`, `/snapshot/raw` (no overlays), `/info` (the camera it watches). |
| `Main.py` | Local demo entry point — calls `main()` from `local_test.py`. |
| `local_test.py` | Local OpenCV runtime: ROI selection, display, FPS, and orchestration. |
| `detector.py` | YOLO inference, with optional ROI filtering for the local demo. |
| `video_source.py` | Threaded video capture that keeps the latest frame; video files play at their own frame rate. |
| `alert_manager.py` | Temporal confirmation and incident/reminder logic, shared by both runtimes. |
| `verify_alert_logic.py` | Checks the window, incident and evidence rules without a camera or model (`python verify_alert_logic.py`). |
| `notifier.py` | Asynchronous HTTP alert delivery for the local demo. |
| `config.py` | Model, source, threshold, and timing configuration. |

---

## ⚙️ Configuration

Current values, defined in `config.py`:

```python
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
MODEL_PATH = PROJECT_DIR / 'best.pt'
DEVICE = 0
VIDEO_SOURCE = 0
BACKEND_ALERT_URL = None

FRAME_SKIP = 5
CONF_THRESHOLD = 0.378
IMAGE_SIZE = 640
WINDOW_SIZE = 6

ALERT_THRESHOLD = {'Fire': 4, 'Smoke': 3}
WINDOW_MAX_AGE_SECONDS = 10
ALERT_REMINDER_SECONDS = 300
INCIDENT_CLEAR_SECONDS = 30
```

| Parameter | Meaning |
| --- | --- |
| `MODEL_PATH` | Trained YOLO weights, resolved relative to `config.py` so the application does not depend on the current working directory. |
| `DEVICE` | Ultralytics device index. `0` means the first CUDA GPU; use `'cpu'` on a CPU-only system. |
| `VIDEO_SOURCE` | `0` means the default camera. It can also be a video filename, e.g. `Videos/VID_20250610_173239.mp4`. |
| `BACKEND_ALERT_URL` | HTTP endpoint for alerts. `None` disables network notifications. |
| `FRAME_SKIP` | YOLO runs once for every five frames consumed by the processing loop. Displayed frames are not skipped. |
| `CONF_THRESHOLD` | Minimum confidence accepted by YOLO. |
| `IMAGE_SIZE` | YOLO inference input size — affects inference speed and detection detail, not the OpenCV display size. `416`, `640`, `768` are commonly used. |
| `WINDOW_SIZE` | Number of inference checks used by the alert manager. |
| `ALERT_THRESHOLD` | Required positive checks for each class. |
| `WINDOW_MAX_AGE_SECONDS` | Checks older than this leave the window, so it never spans a stream outage. |
| `ALERT_REMINDER_SECONDS` | Interval between reminders while an incident stays open. |
| `INCIDENT_CLEAR_SECONDS` | Time without a detection after which an incident closes. |

> 💡 For the current Quadro M2200, `IMAGE_SIZE = 640` is the current setting. A smaller value such as `416` can improve speed, while `1024` may improve detection of very small objects but is considerably more expensive.

The tuning values can be overridden with environment variables of the same name — `FRAME_SKIP`, `WINDOW_SIZE`, `CONF_THRESHOLD`, `WINDOW_MAX_AGE_SECONDS`, `ALERT_REMINDER_SECONDS`, `INCIDENT_CLEAR_SECONDS` — and `FIRE_ALERT_FRAMES` / `SMOKE_ALERT_FRAMES` for `ALERT_THRESHOLD`. The service takes them from `docker-compose.override.yml`, with the same defaults as above.

---

## 🔄 Runtime Flow

### Service (`headless.py`)

1. Load the model, start the MJPEG server, and read the camera's settings from the backend (then again every 30 s in the background).
2. Read the latest frame; on failure, release the source, wait 2 s and reopen it when `VIDEO_LOOP=1`.
3. Frames between inferences go straight to the live view with the last known boxes.
4. On every `FRAME_SKIP`-th frame: if the `fire_smoke` model is switched off for this camera, publish the frame with a "model disabled" label and raise nothing; otherwise run YOLO over the whole frame and publish the annotated frame.
5. Feed the result to `AlertManager`. For each alert, build the snapshot from the best evidence frame and post it through `sflms_client.py`.

The per-frame flow is drawn in `Diagrams/AI/ModelsPipeline/FireAndSmoke/FireAndSmokePipelineV5.png`.

### Local demo (`Main.py`)

`Main.py` calls `local_test.main()`. The runtime follows this sequence:

1. Load the YOLO model and create the alert manager, notifier, and video source.
2. Read the first frame.
3. Let the user select an optional ROI with `cv2.selectROI`.
4. Start the background GPU usage monitor.
5. Read the latest available camera frame from `VideoSource`.
6. Run YOLO only when `frame_count % FRAME_SKIP == 0`.
7. Draw the latest detections on every displayed frame.
8. Update alert history only after an inference check.
9. Queue new alerts for asynchronous HTTP delivery.
10. Display the frame and exit when the user presses `q`.

---

## 🎥 Video Source

`VideoSource` uses a background daemon thread. The thread continuously reads from `cv2.VideoCapture` and stores the latest frame. The main loop receives the newest available frame instead of waiting for old buffered frames.

On Windows, integer camera sources first use the DirectShow backend and fall back to OpenCV's default backend if necessary. Temporary read failures are retried before the source is marked as stopped.

A video file is read at its own frame rate rather than as fast as it decodes, so a recording behaves like a live camera: the detection windows and incident timers see real-time spacing. Live sources (cameras, RTSP) are read as fast as they deliver.

The display loop and YOLO inference have different rates:

| Rate | Driven by |
| --- | --- |
| Display rate | Every frame received by the main loop |
| Inference rate | Every `FRAME_SKIP`-th consumed frame |
| Camera capture rate | Frames read by the background capture thread |

> The on-screen FPS is a rolling average of the display-loop rate. It is **not** a guaranteed camera FPS or YOLO inference FPS.

---

## 🎯 Detection & ROI

The service always watches the **whole frame**: fire and smoke can start anywhere in view, so it has no ROI. ROIs in the admin console belong to the intrusion model. The ROI below exists only in the local demo.

`Detector.detect()` runs YOLO with the configured confidence, device, and image size. Each result contains:

```python
{
    'class_name': 'Fire',
    'confidence': 0.91,
    'box': (x1, y1, x2, y2),
}
```

When an ROI is selected, a detection is accepted only when the center of its bounding box is inside the ROI:

```python
center_x = (x1 + x2) / 2
center_y = (y1 + y2) / 2
```

This is a **center-point policy** — a box that overlaps the ROI but has its center outside it is ignored.

The ROI and detection boxes use the original camera-frame coordinates. `IMAGE_SIZE` is only an inference setting and does not change the displayed frame coordinates.

---

## 🚨 Alert Decisions

`AlertManager` keeps an independent history for `Fire` and `Smoke`. Each inference check adds a positive or negative result to the corresponding window. An alert is created when:

- ✅ the window contains `WINDOW_SIZE` inference checks, none older than `WINDOW_MAX_AGE_SECONDS`; **and**
- ✅ the positive count reaches the class threshold.

With the current settings, an alert requires **at least 4 positive Fire checks** or **3 positive Smoke checks** within a **6-check window**. Fire needs more because its per-frame precision is lower (~0.73 vs ~0.83), and smoke usually appears first, so it is the earlier warning.

> The window is based on inference checks, not fixed seconds. Its real elapsed time changes when camera FPS, `FRAME_SKIP`, or inference speed changes; `WINDOW_MAX_AGE_SECONDS` only caps it.

**Incidents.** The first confirmation opens an incident and raises one alert. While the class keeps being confirmed, a reminder is raised every `ALERT_REMINDER_SECONDS` (5 minutes). Once the class has gone undetected for `INCIDENT_CLEAR_SECONDS` (30 s), the incident closes, and the next confirmation is a new alert. Fire and Smoke have separate incidents.

**Evidence.** Each positive check stores its frame and boxes in the same window. An alert uses the highest-confidence frame from the checks that confirmed it, draws every box of that class on the snapshot, and reports the strongest box as the event's `bbox`. Evidence older than the window cannot be sent.

---

## 📡 Notifications

**Service.** `sflms_client.py` writes the snapshot JPEG to the protected media volume shared with the backend, then posts a `fire_alert` or `smoke_alert` camera event with its AI key. Fire and smoke events carry no `roi_id`. The backend rejects the event if the `fire_smoke` model is switched off for the camera, so a switched-off model raises nothing even before the detector's next settings refresh.

**Local demo.** When `BACKEND_ALERT_URL` is configured, `AlertNotifier.send(alert)` places the alert in a queue. A background worker performs the HTTP `POST`, so network latency does not block the video-processing loop.

```text
Content-Type: application/json
```

When the URL is `None` or empty, notifications are disabled. HTTP, connection, and timeout failures are reported without stopping the main detection loop.

---

## 🖥️ Display and Controls

The detection window is created as a resizable OpenCV window with preserved aspect ratio and an initial size of `800x450`. The displayed frame includes:

- 🔲 Fire and Smoke bounding boxes
- 🔢 Confidence values
- 🎯 The selected ROI, when enabled
- ⏱️ Rolling display FPS
- 🖥️ GPU utilization and VRAM information when `nvidia-smi` is available

**Press `q` to stop the application.**

> The display size is independent from `IMAGE_SIZE`. A camera frame of `640x480` will not become a `640x640` display image merely because YOLO uses `IMAGE_SIZE = 640`.

---

## 🧹 Cleanup

The main loop uses `finally` to release the video source, close the notifier worker, stop the GPU monitor, and destroy OpenCV windows.

---

## 🚀 Local Setup

The service's dependencies are pinned in `requirements.txt` (a CUDA build of `torch` for the Quadro M2200) and installed by the `Dockerfile`. The local demo needs a desktop OpenCV build, because the service image uses `opencv-python-headless`, which has no windows:

```text
opencv-python
ultralytics
torch
```

The active environment must also have a CUDA-enabled PyTorch installation when `DEVICE = 0` is used. Verify CUDA with:

```powershell
python -c "import torch; print(torch.cuda.is_available())"
```

Run locally with:

```powershell
python Main.py
```

For a video-file test, set:

```python
VIDEO_SOURCE = 'Videos/VID_20250610_173239.mp4'
```

---

## 🛣️ Current Limitations and Future Work

- [ ] `/healthz` on the stream port always reports ok; it does not yet check that frames are still arriving.
- [ ] The MJPEG live view has no authentication, so anyone on the network can watch it.
- [ ] The thresholds come from test-set curves; they have not yet been checked against reviewed alerts from the real room.
- [ ] `torchvision`, `ultralytics` and `opencv-python-headless` are not pinned in `requirements.txt`.
- [ ] The local demo's ROI filter uses the box center; overlap filtering could be added if needed.