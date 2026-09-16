<div align="center">

# 🚗 License Plate Recognition (ALPR) — Deployment

> **Detection, tracking, and recognition of Syrian licence plates in video, with vehicle-type classification and IN/OUT access logging.**

[![YOLO](https://img.shields.io/badge/Ultralytics-YOLO26-00FFFF?style=for-the-badge)](https://ultralytics.com/)
[![OpenCV](https://img.shields.io/badge/OpenCV-Video-5C3EE8?style=for-the-badge&logo=opencv)](https://opencv.org/)
[![PaddleOCR](https://img.shields.io/badge/PaddleOCR-PP--OCRv6-2932E1?style=for-the-badge)](https://github.com/PaddlePaddle/PaddleOCR)
[![Status](https://img.shields.io/badge/Docker%20%2F%20Backend-Integration%20pending-lightgrey?style=for-the-badge)]()

</div>

---

## 📄 Abstract

This module implements the automatic licence plate recognition (ALPR) component of the Smart Facility Monitoring System. A YOLO26-Nano detector, fine-tuned on Syrian plates, localises plates in each frame; ByteTrack associates the detections over time; and a layout-aware reading stage built on the PaddleOCR PP-OCRv6 text-line recognizer converts each plate crop into a validated number in one of the two Syrian plate formats (2 + 5 or 3 + 4 digits). Readings are accumulated per track by confidence-weighted voting, and each confirmed vehicle is assigned a type and an IN/OUT direction when it crosses a virtual line.

On an evaluation set of 83 plate photographs (47 distinct plates), the recognition stage reads **96.4 %** of plates exactly (95 % CI 89.9–98.8 %) with **no incorrect readings**, compared with 39.8 % correct and 47.0 % incorrect readings for the previous EasyOCR-based implementation. A runtime analysis showed that the dominant source of latency was not model inference but the GPU leaving its high-performance state during CPU-bound OCR pauses; rescheduling OCR, together with display and I/O changes, raised throughput on a 1080 × 1920 test video from **8.1 to 18.4 frames per second**.

---

## 1. System Overview

```text
 video / photo
      │
      ▼
 YOLO26n plate detector ──► ByteTrack ──► per-track state
 (every 2nd frame, 1024 px)                    │
                                               ├──► padded crop ──► layout-aware OCR ──► format validation ──► voting / lock ──► vehicle ID
                                               ├──► COCO YOLO26n vehicle model (every 4th frame) ──► CAR / Truck
                                               └──► virtual line crossing ──► IN / OUT event
```

| Module | Responsibility |
| --- | --- |
| `Main.py` | Entry point — calls `main()` in `local_test.py`. |
| `local_test.py` | Runtime loop: input discovery (video, photo, or folder), detection and tracking, OCR scheduling, drawing, preview window, and output writing. |
| `paths.py` | **All file locations** — the only file that differs between the local test copy and this deployment copy (§5.1). |
| `config.py` | Model, OCR, tracking, display, vehicle, and direction parameters. |
| `models.py` | Loads the OCR engine selected by `OCR_ENGINE`, the plate detector, and the COCO vehicle model. |
| `ocr_paddle.py` | **Current OCR engine** — PP-OCRv6 recognition with row handling, deskewing, scoring, and rejection. |
| `ocr.py` | Previous EasyOCR engine; also holds the engine-independent plate-format rules, cropping, and voting. |
| `tracking.py` | Per-track state, stale-track cleanup, and plate-based vehicle numbering. |
| `direction.py` | Line-side geometry and the debounced IN/OUT decision. |
| `vehicle.py` | Plate-to-vehicle association and COCO class simplification. |
| `image_io.py` | Unicode-safe image reading and writing (OpenCV cannot open non-ASCII paths on Windows). |
| `debug_utils.py` | Saves plate crops with their readings, capped at `MAX_DEBUG_IMAGES`. |
| `test_format_logic.py`, `test_ocr_paddle_logic.py` | Unit tests for plate assembly, parsing, confidence rules, and deskewing — no model weights required. |

---

## 2. Methodology

### 2.1 Plate Detection and Tracking

Plates are detected by a YOLO26-Nano model obtained by transfer learning: a plate detector trained on 10,050 generic plate images was fine-tuned on 393 manually annotated Syrian plate images. Its best checkpoint reaches **99.4 % mAP@50**, 81.2 % mAP@50-95, 99.3 % precision, and 97.6 % recall (see the [repository README](../../../README.md#-model-performance-metrics)).

At run time the detector processes every second frame at an input size of 1024 px (confidence ≥ 0.20, NMS IoU 0.45), and the Ultralytics ByteTrack implementation links detections into tracks. Each detection box is enlarged by 6 % on every side before cropping, so that characters touching the box edge are not cut.

### 2.2 Plate Reading

Syrian plates carry seven digits in one of two formats, which the pipeline must distinguish because they denote different registration states:

| Format | Example | Category | Layout |
| --- | --- | --- | --- |
| 2 + 5 | `65-12377` | Permanent registration | Predominantly one row, digits on either side of the emblem |
| 3 + 4 | `551-7467` | Temporary (customs) | Two rows: three digits beside the flag, four below |

Recognition uses **PP-OCRv6_small_rec**, a text-line recognizer that transcribes exactly one line of text. Presented with a whole two-row plate, it returns only the dominant bottom row (for example `7467` for `551-7467`). The reading stage therefore evaluates two layout hypotheses and keeps the best-scoring valid result (`ocr_paddle.read_plate`):

1. **Skew correction.** The plate angle is estimated as the length-weighted median orientation of long straight edges (Canny edges followed by a probabilistic Hough transform, keeping lines at least 35 % of the crop width). For tilts of 3° or more, a rotated and re-cropped copy of the plate is also read; above 8°, that copy is read first.
2. **One-row hypothesis.** The whole crop is read as one line and must yield exactly seven digits. The emblem, usually transcribed as `=` or `-`, marks the split between the two groups. A reading with confidence ≥ 0.90 is accepted immediately.
3. **Two-row hypothesis.** The crop is split at 42 % of its height. The bottom row is read on its own, and its digit count selects the format (five digits → 2 + 5, four → 3 + 4); the first group is then taken from the digits at the left of the top row, away from the flag and the `SYR` lettering.
4. **Scoring.** A candidate's confidence is the recognizer score (for two-row reads, the lower of the two rows' scores), reduced when the evidence is weaker: ×0.85 when the top row contained extra digits that had to be trimmed; ×0.75 when the two rows imply different formats; ×0.85 for a 3 + 4 plate whose first group does not begin with 5 (the temporary plates observed so far all do, but a permanent plate may also begin with 5, so this is applied as a prior rather than a rule); and ×0.80 when a different plate number scores within 0.10 of the best one.
5. **Rejection.** The best candidate is returned only if its confidence is at least **0.85**; otherwise the plate is reported as unread.

The rejection step reflects the cost asymmetry of the application. In an access log, an incorrect plate number attributes an entry or exit to the wrong vehicle, whereas an unread plate leaves the event unattributed and is usually recovered from later frames of the same track.

The previous EasyOCR-based engine remains available as `OCR_ENGINE = "easyocr"` and serves as the baseline in §3.

### 2.3 Temporal Aggregation and Vehicle Identity

Each track keeps its 20 most recent accepted readings. The plate number with the highest summed confidence becomes the track's **confirmed** plate once it has at least three supporting readings (`MIN_VOTES`) and is **locked** once it has five (`LOCK_VOTES`), after which the track is no longer passed to OCR. OCR is also restricted to boxes found in the most recent detection pass: a track that has been lost retains its last box, and reading that region returns only background.

Tracker identifiers are not suitable as vehicle numbers. ByteTrack assigns an identifier to every new unmatched detection, including one-frame false detections that never become tracks, and a single vehicle can be split into several tracks when its plate is briefly lost; in the test video, the only vehicle present was assigned tracks 2, 5, and 6. Vehicles are therefore numbered **1, 2, 3, … in the order in which their plates are confirmed**, and tracks with the same confirmed plate share one number.

### 2.4 Vehicle Type and Direction

Every fourth frame, a COCO-pretrained YOLO26-Nano model detects vehicles (confidence ≥ 0.35). Each plate is associated with the smallest vehicle box containing its centre (with a 10 % margin), and a majority vote over the last ten associations yields `CAR` (car, motorcycle) or `Truck` (truck, bus).

Direction is determined relative to a virtual line across the frame at 55 % of its height. A change in the side of the line on which the plate centre lies is confirmed after three consecutive detections and produces a single `IN` or `OUT` event.

---

## 3. Experimental Evaluation

### 3.1 Evaluation Data

| Set | Content | Samples | Distinct plates | Median plate width | Stages exercised |
| --- | --- | :---: | :---: | :---: | --- |
| **Photo set** | Photographs of vehicles taken with phones or collected from social media, at varied angles and distances | 83 | 47 | 196 px | Detection → crop → OCR |
| **Crop set** | Plate regions cut manually from annotated images, mostly small and distant plates | 53 | 33 | 62 px | OCR only |

Fourteen plates appear in both sets. Every sample carries a manually labelled seven-digit ground truth; the plate format is additionally labelled for 26 photographs and for all 53 crops, and 8 crops are marked as blurry.

The photographs are drawn from the Syrian Plates detection dataset (56 from its training split, 15 from validation, and 12 from test), so detection rates measured on the photo set describe the pipeline on known imagery rather than the detector's generalisation, which is characterised by the held-out metrics in §2.1. The crop set is drawn from the validation (16) and test (37) splits and involves no detection.

### 3.2 Protocol and Metrics

For each photograph, the highest-confidence plate detection is cropped and read once, exactly as the live pipeline reads a single frame; for each crop, the reading function is applied directly. No multi-frame voting is involved, so the figures describe single-frame recognition — the pipeline's weakest operating point. Both OCR engines ran on the CPU (Intel Core i7-6820HQ), and the detector ran on the GPU (NVIDIA Quadro M2200).

Each sample receives one outcome: **correct** (all seven digits match), **wrong** (a plate number is returned but differs from the ground truth), or **no read** (the engine rejects the plate or cannot parse it). The reported metrics are:

| Metric | Definition |
| --- | --- |
| Accuracy | correct / all samples |
| False-read rate | wrong / all samples |
| Precision | correct / (correct + wrong) — the probability that a returned plate number is right |
| Character error rate (CER) | digit-level Levenshtein distance / ground-truth digits; an unread plate counts as seven errors |
| 95 % CI | Wilson score interval |

### 3.3 Results — Photo Set (detection + OCR, single frame)

The detector located a plate in all 83 photographs. Recognition outcomes:

| Engine | Correct | Wrong | No read | Accuracy (95 % CI) | False-read rate (95 % CI) | Precision | CER |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| EasyOCR (previous) | 33 | 39 | 11 | 39.8 % (29.9–50.5) | 47.0 % (36.6–57.6) | 45.8 % | 25.8 % |
| **PaddleOCR PP-OCRv6 (current)** | **80** | **0** | **3** | **96.4 % (89.9–98.8)** | **0.0 % (0.0–4.4)** | **100 %** | **3.6 %** |

At the plate level, PaddleOCR read 45 of the 47 distinct plates correctly in at least one photograph and 44 in every photograph, against 25 and 13 for EasyOCR. Wherever the format is labelled, it was correct for every plate number either engine returned, so EasyOCR's errors are digit-recognition errors rather than layout errors. In each of the three photographs PaddleOCR left unread, its best candidate was incorrect (confidence 0.51–0.80) and was rejected.

**Accuracy by plate width.**

| Crop width | Photos | PaddleOCR correct / wrong | EasyOCR correct / wrong |
| --- | :---: | :---: | :---: |
| < 60 px | 2 | 2 / 0 | 0 / 2 |
| 60–99 px | 8 | 7 / 0 | 2 / 4 |
| 100–159 px | 24 | 22 / 0 | 6 / 12 |
| ≥ 160 px | 49 | 49 / 0 | 25 / 21 |

**Accuracy by detector split of the photograph.** Recognition quality does not depend on whether the detector saw the photograph during training:

| Detector split | Photos | PaddleOCR correct / wrong | EasyOCR correct / wrong |
| --- | :---: | :---: | :---: |
| Train | 56 | 54 / 0 | 21 / 28 |
| Validation | 15 | 14 / 0 | 5 / 8 |
| Test | 12 | 12 / 0 | 7 / 3 |

**Effect of the acceptance threshold.** Each row discards readings below the threshold:

| Threshold | PaddleOCR correct / wrong | PaddleOCR precision | EasyOCR correct / wrong | EasyOCR precision |
| :---: | :---: | :---: | :---: | :---: |
| 0.00 | 80 / 3 | 96.4 % | 33 / 39 | 45.8 % |
| 0.45 (EasyOCR setting) | 80 / 3 | 96.4 % | 33 / 39 | 45.8 % |
| 0.80 | 80 / 0 | 100 % | 26 / 19 | 57.8 % |
| **0.85 (PaddleOCR setting)** | **80 / 0** | **100 %** | 22 / 15 | 59.5 % |
| 0.90 | 77 / 0 | 100 % | 20 / 13 | 60.6 % |
| 0.95 | 68 / 0 | 100 % | 19 / 10 | 65.5 % |

EasyOCR's confidence does not separate correct from incorrect readings: even at 0.95, a third of the plate numbers it returns are wrong, so no threshold makes it usable for access logging. PaddleOCR's incorrect candidates all score below 0.80, which allows a rejection threshold to remove them without losing a correct reading.

### 3.4 Results — Crop Set (OCR only)

The crop set isolates recognition under difficult conditions: its median plate width is 62 px, roughly a third of the photo set's.

| Engine | Correct | Wrong | No read | Accuracy (95 % CI) | False-read rate (95 % CI) | Precision | CER |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| EasyOCR (previous) | 9 | 18 | 26 | 17.0 % (9.2–29.2) | 34.0 % (22.7–47.4) | 33.3 % | 58.5 % |
| **PaddleOCR PP-OCRv6 (current)** | **37** | **0** | **16** | **69.8 % (56.5–80.5)** | **0.0 % (0.0–6.8)** | **100 %** | **30.2 %** |

| Condition | Crops | PaddleOCR correct / wrong | EasyOCR correct / wrong |
| --- | :---: | :---: | :---: |
| Width < 60 px | 26 | 13 / 0 | 3 / 5 |
| Width 60–99 px | 20 | 17 / 0 | 3 / 11 |
| Width 100–159 px | 7 | 7 / 0 | 3 / 2 |
| One-row plate | 31 | 25 / 0 | 3 / 13 |
| Two-row plate | 22 | 12 / 0 | 6 / 5 |
| Clear | 45 | 36 / 0 | 9 / 18 |
| Blurry | 8 | 1 / 0 | 0 / 0 |

PaddleOCR read 23 of the 33 distinct plates correctly in at least one crop, against 6 for EasyOCR. Its accuracy is governed mainly by resolution — rising from 50 % below 60 px to 100 % from 100 px — and by layout: a two-row plate divides the available height between two rows, so small two-row plates are the hardest case. As on the photo set, every failure takes the form of a rejection rather than an incorrect plate number.

### 3.5 Recognition Latency

Per-plate reading time on the CPU:

| Engine | Photo set — median / 95th percentile | Crop set — median / 95th percentile |
| --- | :---: | :---: |
| EasyOCR (previous) | 8,938 ms / 29,398 ms | 4,039 ms / 10,344 ms |
| **PaddleOCR PP-OCRv6 (current)** | **75 ms / 390 ms** | **164 ms / 223 ms** |

A clear one-row plate needs a single recognizer call. Plates that fall through to the two-row hypothesis or to the deskewed copy need several, which produces the longer tail. The EasyOCR engine makes several reading attempts per plate (the whole plate, then row- and group-level crops), each a full text-detection and recognition pass, which accounts for its latency on the CPU.

### 3.6 Video Case Study

The complete pipeline was run on a 14.9 s phone video (1080 × 1920, 30 fps, 446 frames) in which one car approaches the camera and crosses the virtual line.

| Aspect | Result |
| --- | --- |
| Plate number | `17-42414` — confirmed and correct (verified against the saved plate crops) |
| Vehicle numbering | A single vehicle, `ID1`, although the tracker produced three tracks for it |
| Vehicle type | `CAR` |
| Direction | One `IN` event at frame 246 |
| OCR calls | 22, of which 10 returned a plate number (all correct) and 12 were rejected; **0 incorrect** |

---

## 4. Runtime Performance Analysis

### 4.1 Profiling

Initial profiling of the video above showed a throughput of 8.1 fps. Per-stage timing revealed that the plate detector took a median of **116 ms** per call inside the pipeline but **25.6 ms** when benchmarked on its own on frames from the same video, so the model itself was not the bottleneck.

### 4.2 Effect of GPU Idle Time

To isolate the cause, detector latency was measured while inserting controlled work between consecutive detector calls:

| Work between detector calls | Detector inference (median) |
| --- | :---: |
| None | 17.4 ms |
| 20 ms idle | 17.5 ms |
| 50 ms idle | 26.7 ms |
| 110 ms idle | 111.8 ms |
| 110 ms of CPU-bound work | 113.0 ms |
| Two PaddleOCR recognitions | 108.5 ms |

Idle time and CPU-bound work of the same duration had the same effect, and changing PaddleOCR's thread settings made no difference. The slowdown is therefore caused by the laptop GPU dropping to a low-power performance state after roughly 100 ms without work, not by contention for the CPU. OCR on the CPU created exactly such pauses on most detection frames.

### 4.3 Optimisations and Results

| Change | Rationale |
| --- | --- |
| Run OCR only on boxes detected in the current pass | Reading a lost track's stale box returns background, and failed reads try every hypothesis, making them the slowest (median 179 ms against 57 ms for successful reads). |
| Lock a plate after five agreeing readings | Further readings of a confirmed plate cannot change it but still pause the GPU. |
| Encode the output video on a worker thread | Encoding a 1080 × 1920 frame took about 15 ms; OpenCV releases the Python GIL while encoding. |
| Use `cv2.pollKey()` instead of `cv2.waitKey(1)` | `waitKey(1)` waits for the next Windows timer tick, about 10 ms per frame. |
| Downscale the preview in two steps | Area interpolation directly to a fractional size took up to 12 ms per frame; an integer-factor area step followed by bilinear resizing takes about 0.7 ms. |

| Configuration | Total time | Throughput | Detector (median) | OCR calls |
| --- | :---: | :---: | :---: | :---: |
| Initial pipeline, no preview window | 55.1 s | 8.1 fps | 116 ms | 154 |
| + OCR scheduling (first two changes), no preview window | 28.5 s | 15.6 fps | 29 ms | 22 |
| + all changes, **preview window on** | **24.2 s** | **18.4 fps** | — | 22 |

All totals include a one-time GPU warm-up of about 4 s on the first frame. The recognised plate, vehicle type, and crossing event were identical in every configuration.

---

## 5. Deployment Configuration

### 5.1 Local and Deployment Copies

The pipeline is maintained in two copies with identical code: a local copy used for experiments and this deployment copy, which is intended for integration with the backend and Docker. **All file locations live in `paths.py`, the only file that differs between the two**, so any other file can be copied between them unchanged.

In this copy, every path is read from an environment variable and falls back to a location inside this folder:

| Variable | Purpose | Default |
| --- | --- | --- |
| `ALPR_MODEL_PATH` | Fine-tuned plate-detector weights | `./best.pt` |
| `ALPR_VEHICLE_MODEL_PATH` | COCO vehicle model | `yolo26n.pt` (downloaded on first use) |
| `ALPR_INPUT_PATH` | A video, a photo, or a folder containing both | `./VID_sample.mp4` |
| `ALPR_OUTPUT_PATH` | Annotated video when the input is a single video | `./output_fast.mp4` |
| `ALPR_OUTPUT_DIR` | Annotated files for photo and folder inputs | `./outputs` |
| `ALPR_DEBUG_DIR` | Saved plate crops | `./debug_plates` |

PaddleOCR downloads its recognition model on first use and caches it under `~/.paddlex`; set `PADDLE_PDX_CACHE_HOME` to place that cache on a mounted volume.

### 5.2 Principal Parameters (`config.py`)

| Parameter | Value | Meaning |
| --- | :---: | --- |
| `OCR_ENGINE` | `"paddle"` | `"paddle"` (`ocr_paddle.py`) or `"easyocr"` (`ocr.py`) |
| `PADDLE_REC_MODEL` | `PP-OCRv6_small_rec` | PaddleOCR recognition model |
| `DETECT_EVERY` / `OCR_EVERY` | 2 / 2 | Run detection and tracking / OCR every N frames |
| `YOLO_IMGSZ` / `YOLO_CONF` | 1024 / 0.20 | Detector input size and confidence threshold |
| `HISTORY_SIZE` | 20 | Readings kept per track |
| `MIN_VOTES` / `LOCK_VOTES` | 3 / 5 | Agreeing readings needed to confirm / lock a plate |
| `TRACK_TIMEOUT_FRAMES` | 30 | Frames a track may go unseen before removal |
| `VEHICLE_DETECT_EVERY` / `VEHICLE_CONF` | 4 / 0.35 | Vehicle-model schedule and confidence threshold |
| `LINE_P1_RATIO` / `LINE_P2_RATIO` | (0, 0.55) / (1, 0.55) | Virtual line endpoints as fractions of the frame size |
| `CROSSING_CONFIRM_FRAMES` | 3 | Consecutive detections confirming a side change |
| `SHOW_WINDOW` / `WINDOW_SCREEN_FRACTION` | `True` / 0.95 | Preview window, scaled to fit the screen |
| `SAVE_DEBUG` / `MAX_DEBUG_IMAGES` | `True` / 60 | Save plate crops for inspection |

The acceptance threshold (0.85) and the scoring factors of §2.2 are defined in `ocr_paddle.py`.

### 5.3 Setup and Execution

```powershell
pip install -r requirements.txt
python Main.py
```

1. Place the fine-tuned detector weights at `./best.pt`, or set `ALPR_MODEL_PATH`. Weights and videos are not committed.
2. Place a test video at `./VID_sample.mp4`, or set `ALPR_INPUT_PATH` to a video, a photo, or a folder.
3. Press **`q`** in the preview window to stop. For photos, any other key advances to the next image.

The unit tests need no weights:

```powershell
python test_format_logic.py
python test_ocr_paddle_logic.py
```

### 5.4 Test Environment

| Component | Version |
| --- | --- |
| Hardware | Intel Core i7-6820HQ, NVIDIA Quadro M2200 (4 GB), Windows 11 |
| Python | 3.13 |
| PyTorch | 2.14.0 (CUDA 12.6) |
| Ultralytics | 8.4.131 |
| OpenCV | 4.10.0 |
| PaddlePaddle / PaddleOCR | 3.3.1 (CPU) / 3.7.0 |
| EasyOCR (baseline) | 1.7.2 |

---

## 6. Limitations and Future Work

- [ ] **Evaluation scale.** The evaluation covers 47 and 33 distinct plates photographed under uncontrolled conditions. Confirming these results on a larger, independently collected set — ideally footage from the deployment gate camera — is required before drawing general conclusions.
- [ ] **Video coverage.** The video case study contains a single vehicle in daylight; multi-vehicle scenes, night-time footage, and occlusion remain untested.
- [ ] **Real-time margin.** At 18.4 fps, the pipeline processes a 30 fps source at about 0.6× real time on the test laptop. Setting the NVIDIA power-management mode to *Prefer maximum performance* is expected to reduce the idle-state penalty described in §4.2 but has not been measured.
- [ ] **Headless entry point.** `local_test.py` uses an OpenCV preview window; a container needs an entry point without `cv2.imshow` and with camera or RTSP stream inputs, which `collect_inputs` does not yet accept.
- [ ] **Backend delivery.** Crossing events are printed and returned but not yet sent to the backend; an asynchronous HTTP notifier, like the one in the Fire & Smoke deployment, would provide this.
- [ ] **Shared state.** `tracks`, `vehicle_numbers`, and the OCR reader are module-level state — adequate for one stream per process, but they must become per-stream objects before one process serves several cameras.
- [ ] **Locked plates.** A locked plate is not re-read; if the tracker exchanged the boxes of two vehicles, the earlier label would persist.
- [ ] **Vehicle numbering.** Numbering follows the confirmed plate, so a misread plate would create a new vehicle number, and a vehicle whose plate is never read receives none.
- [ ] **Vehicle classes.** Motorcycles are grouped with cars, and buses with trucks.
