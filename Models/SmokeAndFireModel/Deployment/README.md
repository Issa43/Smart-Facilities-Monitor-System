<div align="center">

# 🔥 Fire & Smoke Detection — Deployment

> **Real-time fire and smoke detection from a camera or video source, powered by a custom-trained Ultralytics YOLO model.**

[![YOLO](https://img.shields.io/badge/Ultralytics-YOLO-00FFFF?style=for-the-badge)](https://ultralytics.com/)
[![OpenCV](https://img.shields.io/badge/OpenCV-Video-5C3EE8?style=for-the-badge&logo=opencv)](https://opencv.org/)
[![Status](https://img.shields.io/badge/Docker-Postponed-lightgrey?style=for-the-badge)]()

</div>

---

## 📌 Overview

This project detects fire and smoke from a camera or video source using a trained Ultralytics YOLO model. The current implementation is split into focused modules:

| Module | Responsibility |
| --- | --- |
| `Main.py` | Application entry point — imports and calls `main()` from `local_test.py`. |
| `local_test.py` | Current local OpenCV runtime: ROI selection, display, FPS, and orchestration. Kept for local testing until the Docker production entry point is created. |
| `detector.py` | YOLO inference and ROI filtering. |
| `video_source.py` | Threaded video capture that keeps the latest frame. |
| `alert_manager.py` | Temporal confirmation and cooldown logic. |
| `notifier.py` | Asynchronous HTTP alert delivery. |
| `config.py` | Model, source, threshold, and timing configuration. |

> 🐳 **Docker deployment is intentionally postponed.** The current runtime uses an interactive OpenCV window and a local camera, so Docker will require a separate decision about GUI, camera-device access, and GPU access.

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

ALERT_THRESHOLD = {'Fire': 3, 'Smoke': 4}
COOLDOWN_SECONDS = 15
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
| `COOLDOWN_SECONDS` | Minimum time between alerts for the same class. |

> 💡 For the current Quadro M2200, `IMAGE_SIZE = 640` is the current setting. A smaller value such as `416` can improve speed, while `1024` may improve detection of very small objects but is considerably more expensive.

---

## 🔄 Runtime Flow

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

The display loop and YOLO inference have different rates:

| Rate | Driven by |
| --- | --- |
| Display rate | Every frame received by the main loop |
| Inference rate | Every `FRAME_SKIP`-th consumed frame |
| Camera capture rate | Frames read by the background capture thread |

> The on-screen FPS is a rolling average of the display-loop rate. It is **not** a guaranteed camera FPS or YOLO inference FPS.

---

## 🎯 Detection & ROI

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

- ✅ the window contains `WINDOW_SIZE` inference checks;
- ✅ the positive count reaches the class threshold; **and**
- ✅ the class cooldown has expired.

With the current settings, an alert requires **at least 3 positive Fire checks** or **4 positive Smoke checks** within a **6-check window**.

> The window is based on inference checks, not fixed seconds. Its real elapsed time changes when camera FPS, `FRAME_SKIP`, or inference speed changes.

---

## 📡 Notifications

When `BACKEND_ALERT_URL` is configured, `AlertNotifier.send(alert)` places the alert in a queue. A background worker performs the HTTP `POST`, so network latency does not block the video-processing loop.

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

The current code expects Python packages including:

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

- [ ] `Main.py` currently starts the local GUI implementation in `local_test.py`; a separate production `app.py` can be introduced during Dockerization.
- [ ] The interactive ROI and OpenCV display require a graphical environment.
- [ ] A Docker container will need explicit camera and NVIDIA GPU configuration.
- [ ] A headless Docker deployment will need a replacement for `cv2.selectROI` and `cv2.imshow`.
- [ ] The repository should later include dependency metadata such as `requirements.txt` and a proper `.gitignore`.
- [ ] Alert timing may be changed from inference-check windows to a time-based policy if required.
- [ ] ROI filtering may be changed from center-point filtering to intersection or overlap filtering if the application requires it.

> These deployment changes are intentionally left for the Dockerization stage.
