<div align="center">

# 🚗 License Plate Recognition (ALPR) — Deployment

> **Real-time Syrian license plate detection, tracking, OCR, vehicle typing, and IN/OUT crossing detection from a video source, powered by a custom-trained Ultralytics YOLO model.**

[![YOLO](https://img.shields.io/badge/Ultralytics-YOLO-00FFFF?style=for-the-badge)](https://ultralytics.com/)
[![OpenCV](https://img.shields.io/badge/OpenCV-Video-5C3EE8?style=for-the-badge&logo=opencv)](https://opencv.org/)
[![EasyOCR](https://img.shields.io/badge/EasyOCR-Digits-yellow?style=for-the-badge)](https://github.com/JaidedAI/EasyOCR)
[![Status](https://img.shields.io/badge/Docker%20%2F%20Django-Postponed-lightgrey?style=for-the-badge)]()

</div>

---

## 📌 Overview

This pipeline detects and tracks license plates from a video source, reads their digits with EasyOCR, classifies the vehicle type (car vs. truck, via a COCO-pretrained YOLO model), and logs IN/OUT crossings across a configurable virtual line. The implementation is split into focused modules:

| Module | Responsibility |
| --- | --- |
| `Main.py` | Application entry point — imports and calls `main()` from `local_test.py`. |
| `local_test.py` | Current local OpenCV runtime: video loop, drawing, and orchestration. Kept for local testing until a headless Docker production entry point is created. |
| `models.py` | Loads the EasyOCR reader, the custom plate-detector YOLO model, and the COCO vehicle-classifier YOLO model. |
| `tracking.py` | `TrackState` (per-track history/state) and the `tracks` registry, plus stale-track cleanup. |
| `direction.py` | Line-crossing geometry and the debounced IN/OUT direction decision. |
| `vehicle.py` | Matches a plate box to the smallest overlapping vehicle box and simplifies COCO classes into `CAR`/`Truck`. |
| `ocr.py` | Plate cropping, digit OCR, rectangle/vertical plate-format extraction, and confidence-weighted voting across frames. |
| `debug_utils.py` | Saves cropped plate images per OCR attempt, capped at `MAX_DEBUG_IMAGES`. |
| `config.py` | Model, video, threshold, and timing configuration. |

> 🐳 **Docker and Django integration are intentionally postponed.** The current runtime uses an interactive OpenCV window and reads from a local video file, so both will require a separate decision about GUI/headless operation, request-scoped state, and GPU access.

---

## ⚙️ Configuration

Key values, defined in `config.py`:

| Parameter | Meaning |
| --- | --- |
| `MODEL_PATH` | Custom-trained plate-detector weights, resolved relative to `config.py` (`PROJECT_DIR / "best.pt"`). **Not committed** — place your own `best.pt` next to `config.py` before running. |
| `VEHICLE_MODEL_PATH` | COCO-pretrained vehicle classifier (`yolo26n.pt`); Ultralytics downloads it automatically if not found locally. |
| `VIDEO_PATH` / `OUTPUT_PATH` | Input video and annotated output path. **Not committed** — point `VIDEO_PATH` at your own local test video. |
| `DETECT_EVERY` / `OCR_EVERY` | Run plate detection+tracking / OCR once every N frames. |
| `VEHICLE_DETECT_EVERY` | Run the vehicle-type model once every N frames (vehicle type changes slowly, so this runs less often than plate tracking). |
| `YOLO_CONF` / `VEHICLE_CONF` | Minimum confidence for the plate detector / vehicle classifier. |
| `HISTORY_SIZE` / `MIN_VOTES` | Rolling OCR history length per track, and the minimum number of matching reads before a plate text is considered "stable". |
| `TRACK_TIMEOUT_FRAMES` | Frames a track can go unseen before it's dropped. |
| `LINE_P1_RATIO` / `LINE_P2_RATIO` | Virtual crossing line endpoints, as fractions of frame width/height. |
| `CROSSING_CONFIRM_FRAMES` | Consecutive detections required on the new side before a crossing is confirmed (debounce). |

---

## 🔄 Runtime Flow

`Main.py` calls `local_test.main()`. The runtime follows this sequence per frame:

1. Every `DETECT_EVERY` frames: run YOLO + ByteTrack on the plate model, update each track's box, and check for a confirmed line crossing.
2. Every `VEHICLE_DETECT_EVERY` frames: run the COCO vehicle model, match each plate track to the smallest overlapping vehicle box, and update a majority-vote vehicle type.
3. Drop tracks unseen for more than `TRACK_TIMEOUT_FRAMES`.
4. Every `OCR_EVERY` frames: crop each active track's plate region, run digit OCR, append to that track's rolling history, and recompute the confidence-weighted "stable" plate text.
5. Draw the crossing line, track boxes/labels, and an on-screen summary; write the frame to `OUTPUT_PATH` and show it in a window.
6. Exit on end-of-video or `q`, then print a summary of all logged crossing events.

---

## 🚀 Local Setup

```text
opencv-python
numpy
easyocr
ultralytics
```

1. `pip install -r requirements.txt`
2. Place your trained `best.pt` next to `config.py`.
3. Point `VIDEO_PATH` in `config.py` at a local test video (e.g. `PROJECT_DIR / "my_test.mp4"`).
4. Run:

```powershell
python Main.py
```

**Press `q`** to stop early; otherwise it runs to the end of the video and prints a crossing-event summary.

---

## 🛣️ Current Limitations and Future Work

- [ ] OCR and vehicle-type matching still run against tracks that haven't been detected recently — they should skip stale tracks the same way the drawing loop already does, to avoid wasted inference and stale-box contamination.
- [ ] `USE_GPU` only controls the EasyOCR reader; the YOLO models pick their device automatically regardless of this flag.
- [ ] `pick_best_window`'s confidence penalty favors substrings earlier in the OCR text with no evidence that's actually more reliable.
- [ ] The left/right and top/bottom region crops in `ocr.py` use fixed percentages of the plate box — sensitive to imprecise or tilted detections.
- [ ] Once a track's plate text is "stable," later OCR noise can still flip it — there's no lock-in once confidence is reached.
- [ ] Motorcycles are currently bucketed into the same `CAR` category as cars in `simplify_vehicle_type`.
- [ ] `tracks`, `debug_counter`, and the OCR reader are module-level global state — fine for a single local run, but will need to become request/session-scoped before this is called from concurrent Django requests.
- [ ] A separate production entry point (headless, no `cv2.imshow`) will be needed for Docker/Django integration.

> These changes are intentionally left for the Docker/Django integration stage.
