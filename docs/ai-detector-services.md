# AI detector services

How the fire/smoke and intrusion models run against live cameras and feed the
SFLMS backend, what was measured while tuning them, and what is still open.

See [camera-processing.md](camera-processing.md) for the ingestion contract and
the realtime protocol. This document covers the detector side.

---

## Shape of the system

Each model runs in **its own container**. They share nothing but the Docker
network, the backend API, and the `protected_media` directory.

```
        BROWSER
           │ :8080                    :8090 / :8091
           ▼                                  │  (MJPEG, direct)
      ┌─────────┐                             │
      │ frontend│  nginx proxies              │
      │  nginx  │  /api/ and /ws/ ──┐         │
      └─────────┘                   ▼         │
                              ┌──────────┐    │
      ┌──────────┐  5432      │ backend  │    │
      │ postgres │◄───────────┤  Django  │    │
      └──────────┘            │  +Daphne │    │
      ┌──────────┐  6379      └──────────┘    │
      │  redis   │◄──────┬────────▲           │
      └──────────┘       │        │ POST /api/v1/camera-events/
       cache/channels    │        │ (AIKey auth)
       /celery broker    │   ┌────┴──────┬───────────┐
                         │   │ detector  │ intrusion │
      ┌──────────┐       │   │  (fire)   │           │
      │  celery  │───────┘   └────┬──────┴─────┬─────┘
      │ worker   │                │ RTSP 8554  │
      │  beat    │                ▼            ▼
      └──────────┘            ┌──────────────────────┐
                              │      mediamtx        │
                              └──────────────────────┘
                                       ▲ RTSP publish
                                  HOST ffmpeg (webcam)
```

A model talks to exactly two things: **mediamtx** for frames in, **backend**
for events out. It never touches Postgres or Redis, and never another model.
Adding a third model is a new service block, not an architectural change.

### Why separate containers

- **Framework conflict.** The ANPR model (not yet containerised) needs
  PaddleOCR, i.e. `paddlepaddle`; the others need `torch`. Both bundle their
  own CUDA and conflict on `numpy`/`protobuf`/`opencv`.
- **Module collisions.** The fire and ANPR `Deployment/` folders both contain
  `Main.py`, `config.py` and `local_test.py`. On one `PYTHONPATH`,
  `import config` is ambiguous.
- **Failure isolation.** Fire detection is the safety-critical pipeline; an
  OCR hang must not take it down.

Keep **one CUDA version across all GPU containers** so they share Docker
layers. Two 12 GB images built from the same base and requirements occupied
16.5 GB on disk, not 24.6 GB, because the CUDA layer is stored once.

---

## Running it

```bash
# infra + app + both detectors
docker compose --profile detector --profile intrusion up -d

# then publish the laptop webcam from the Windows host
ops/start_laptop_camera.ps1
```

> `docker compose --profile X up` stops services outside that profile. Always
> pass **both** profiles, or the other detector and the frontend get stopped.

The publisher is a **host process with no supervision**. Docker Desktop on
Windows cannot forward a webcam into a Linux container, so the host encodes it
to RTSP and the containers read it back. It dies with every reboot, Docker
restart or closed window — if a feed goes quiet, check `Get-Process ffmpeg`
first.

| Service | Port | Notes |
| --- | --- | --- |
| frontend | 8080 | dashboard; proxies `/api/` and `/ws/` |
| backend | 8000 | Django + Daphne |
| detector (fire) | 8090 | MJPEG preview |
| intrusion | 8091 | MJPEG preview, distinct host port |
| mediamtx | 8554 | RTSP relay |

To test without a camera, put a video in the detector's `samples/` folder
(gitignored, mounted at `/samples`) and point the source at it. Files play at
their own frame rate, not as fast as they decode, and loop when `VIDEO_LOOP=1`:

```powershell
$env:VIDEO_SOURCE="/samples/<fire video>.mp4"            # fire / smoke
$env:INTRUSION_VIDEO_SOURCE="/samples/<people video>.mp4"  # intrusion
docker compose --profile detector --profile intrusion up -d
```

From Git Bash, prefix the command with `MSYS_NO_PATHCONV=1`, or it rewrites
`/samples/...` into a Windows path and the detector cannot open the file.

Each detector needs its **own machine credential and camera id**, so events
attribute correctly and one can be revoked without touching the others. Every
detector must also mount `./protected_media`: snapshots do not travel over
HTTP, and the backend rejects an event whose JPEG is not already in protected
storage.

---

## Fire / smoke detector

`Models/SmokeAndFireModel/Deployment/` — `headless.py` is the service runner,
`local_test.py` remains the interactive one.

### Live settings

| Setting | Value | vs `config.py` default |
| --- | --- | --- |
| `CONF_THRESHOLD` | 0.378 | same (F1-optimal) |
| `WINDOW_SIZE` | 6 | same |
| `FRAME_SKIP` | 5 | same |
| `ALERT_THRESHOLD` | Fire 4 / Smoke 3 | same |
| `WINDOW_MAX_AGE_SECONDS` | 10 | same |
| `ALERT_REMINDER_SECONDS` | 300 | same |
| `INCIDENT_CLEAR_SECONDS` | 30 | same |

A detection counts at conf ≥ 0.378. Inference runs on every 5th frame
(~3.6/s on a ~18 fps stream); the last 6 checks form a rolling ~1.7 s window.
Fire alerts at 4 of 6, smoke at 3 of 6. Checks older than 10 s leave the
window, so a window never spans a stream outage. Each class raises one alert
per incident, then a reminder every 5 minutes while it is still confirmed; the
incident closes after 30 s without a detection. The snapshot is the strongest
frame from the confirming window, with every box of that class drawn on it.

### Why the threshold is the F1 point, not higher

Raising confidence is the wrong lever against false alarms. It does not drop
frames uniformly — it drops the ones the model finds hard (small, distant,
dim, smoke-obscured fire), which is exactly the early-stage fire the system
exists to catch, and it drops them *systematically*, not at random.

From the test-set curves in `Models/SmokeAndFireModel/Results/Test/`
(**read off the plots by eye — approximate**):

| Conf | Precision | Recall | P(alert) at 5-of-6 |
| --- | --- | --- | --- |
| 0.378 | ~0.78 | ~0.76 | 0.558 |
| 0.50 | ~0.83 | ~0.69 | 0.399 |
| 0.60 | ~0.87 | ~0.62 | 0.266 |
| 0.70 | ~0.92 | ~0.50 | 0.109 |
| 0.80 | ~0.95 | ~0.33 | 0.017 |

An earlier setting of 0.60 combined with a 5-of-6 gate taxed recall twice: a
real fire had only ~27 % chance of tripping an alert per window. Precision now
comes from the **temporal gate** instead — a lamp or skin tone clears the
threshold for a frame or two, a fire clears it for seconds. That is a
dimension the per-frame test set cannot measure, so it costs no recall.

### Why Fire 4 / Smoke 3

The frame count is a false-positive filter, so it belongs where the per-frame
signal is *less* reliable. Per class at 0.378 (same approximate reading):

| Class | Precision | Recall | k=3 | k=4 | k=5 |
| --- | --- | --- | --- | --- | --- |
| Fire | ~0.73 | ~0.72 | 0.944 | 0.780 | 0.464 |
| Smoke | ~0.83 | ~0.80 | 0.983 | 0.901 | 0.655 |

Smoke is the better-detected class on both axes, so fire gets the stronger
filter (4) and smoke the weaker (3). Smoke also precedes fire, so making it the
slower class to trip would undercut the earliest warning. The original
defaults were the reverse (3 / 4), with no derivation in the code, README or
git history; `config.py` now ships 4 / 3 so local runs match the container.

`ALERT_THRESHOLD`, `WINDOW_SIZE` and the incident timings play **no part in
`model.val()` metrics** — those are per-frame — so changing them cannot
invalidate reported mAP/P/R.

---

## Intrusion detector

`Models/IntrusionModel/Deployment/` — YOLO26n (person class) + ByteTrack +
polygon zone + per-track dwell confirmation.

`intrusion_core.py` is the detection logic ported from `IntrusionDetection.py`
with two changes: an injectable alert callback (where `raise_alert`'s comment
already marked the extension point) and env-overridable tuning that keeps the
measured values as defaults. `headless.py` is the service wrapper.

Ultralytics owns the capture loop (`model.track(stream=True)`) because
ByteTrack needs contiguous frames and `persist=True` to keep ids stable — a
separate reader thread handing over "the latest frame" would break tracking.

### ONNX Runtime instead of PyTorch

Measured on a real frame from this camera, same container, CPU:

| Runtime | imgsz | Latency | FPS |
| --- | --- | --- | --- |
| PyTorch | 1280 | 3959 ms | 0.25 |
| PyTorch | 640 | 2685 ms | 0.37 |
| **ONNX** | **1280** | **854 ms** | **1.17** |
| **ONNX** | **640** | **287 ms** | **3.49** |

ONNX at **1280** beats PyTorch at **640** by more than 3×, so resolution does
not have to be traded for speed — which matters, because the model was tuned
at 1280 (measured 8.7 → 16.1 persons/frame vs 640). The export is fp32, so
this is a pure runtime win with **no accuracy cost**, unlike lowering `imgsz`.

It also lets the image be CPU-only: **733 MB** against ~12 GB.

> The export uses `dynamic=False`, so `INTRUSION_IMGSZ` **must match** the
> exported size or inference fails outright. Re-export to change it.

`resolve_model()` picks the weights from the device — `.pt` for CUDA, `.onnx`
for CPU. Mixing them fails silently: the CPU image installs plain
`onnxruntime`, whose only execution provider is `CPUExecutionProvider`, so
`DETECTOR_DEVICE=0` with the ONNX graph would keep running on CPU while the
log reported `device=0`.

`lap` (ByteTrack's linear-assignment solver) is pinned because ultralytics does
not declare it and pip-installs it on the first `track()` call — which needs a
network at container start and fails in an offline deployment.

### Backend contract

`intrusion_alert` requires more than fire does: everything in
`TRACKED_DETECTION_FIELDS` **plus** `entered_roi_at` and `time_restricted=true`
(`api/v1/camera_events/serializers.py`). `TrackState` stamps the moment a track
crosses into the zone, which is earlier than confirmation by the dwell time.

`time_restricted` is hardcoded `true`: this detector treats its zone as always
restricted. A deployment with a real schedule should check it and simply not
report outside the restricted window.

---

## Admin control: model switch and ROIs

Both detectors read their camera's settings from the backend at startup and
every `CONFIG_REFRESH_SECONDS` (30 s) through `camera_settings.py`, using their
own AI key: `GET /api/v1/cameras/<id>/active-models/` and, for intrusion,
`GET /api/v1/roi/?camera_id=<id>`. If the backend is unreachable the last known
settings stay in force.

| | Fire / smoke | Intrusion |
| --- | --- | --- |
| Area watched | whole frame, no ROI | the ROIs the admin drew; none drawn = no alerts |
| Model switched off | stops inferring, live view shows "model disabled" | same |
| Event `roi_id` | not sent | the ROI the person was standing in |

The admin draws ROIs in **Super Admin → AI camera configuration** by clicking
points on the intrusion detector's live frame (`/snapshot/raw` on its stream
port). `/info` on the same port names the camera the detector watches, so the
page warns when the frame belongs to a different camera. The backend also
rejects events from a switched-off model, so turning a model off takes effect
immediately even before the detector's next refresh.

---

## Diagrams

The fire / smoke diagrams live in `Diagrams/AI/ModelsPipeline/`, each as an
editable `.drawio` file with a PNG export beside it.

| Diagram | Shows |
| --- | --- |
| `FireAndSmokePipelineV5` | per-frame activity: sampling, model switch, YOLO26 preprocessing, inference, NMS, the sliding window and the incident / reminder logic |
| `FireAndSmokeVideoDataFlow` | webcam → ffmpeg → MediaMTX → detector → MJPEG / backend |
| `FireAndSmokeIncidentStates` | the per-class incident state machine |
| `FireAlarmSequence` | one alarm from confirmation to the security officer, including rejection |
| `AIServicesDeployment` | every container, its port and what it talks to |

Update the matching diagram in the same change when the pipeline, the alert
rules or the container layout change.

---

## Backend and dashboard fixes

- **Paginated lists failed past page 1.** nginx passed `Host $host`, which
  drops the port, so DRF built `next=http://localhost/...` and the browser
  requested page 2 on port 80. `fetchAllPages` follows `next` in a loop, so the
  whole query rejected. Fixed with `$http_host`. Single-page lists were
  unaffected, which is why only the alerts page appeared broken.
- **WebSocket URL threw** on the relative `API_BASE_URL` the containerised
  frontend uses; now resolved against the page origin.
- **`Camera.last_seen_at` was never written**, so every camera read as
  never-seen.
- **Empty alerts page for some users.** Both the alert queryset and the
  realtime recipient list scope on active facility assignments. A
  `security_officer` with no assignment sees nothing and receives no live push —
  correct behaviour, but it looks like a broken page. Check assignments before
  debugging anything else.
- **Dashboard now renders one panel per detector** instead of a single
  hardcoded feed, since each model publishes its own annotated stream.

---

## Operational notes

- **RTSP over TCP on both ends.** Only 8554 is published, so UDP RTP goes to
  unmapped ports and the session dies after seconds. The host publisher uses
  `-rtsp_transport tcp`; the containers set
  `OPENCV_FFMPEG_CAPTURE_OPTIONS=rtsp_transport;tcp` (OpenCV exposes no API for
  this).
- **Reconnect backoff.** Both detectors back off before reopening a dead
  source. Without it the fire detector hot-looped, pinning a core and flooding
  MediaMTX with hundreds of connections per second — which was itself knocking
  the publisher offline. The intrusion runner additionally catches the
  `ConnectionError` ultralytics raises from inside its generator.
- **`.gitattributes` pins shell scripts and compose files to LF.** With
  `core.autocrlf=true` on Windows, a CRLF entrypoint fails at container start
  with `set: Illegal option -`.
- **DirectShow device names differ per machine** (`Integrated Webcam` here,
  `Integrated Camera` elsewhere). `start_laptop_camera.ps1` checks the device
  exists and lists the alternatives rather than failing cryptically.
- **Heavy CUDA builds destabilise Docker Desktop.** Several times the engine
  stopped responding or every container exited (137) mid-build. Nothing is lost
  — images and volumes live in the WSL disk — but expect to restart Docker
  Desktop and bring the stack back up.

---

## Measured state

| | Value |
| --- | --- |
| Fire detector | GPU, **534 MiB** VRAM, **~16.8 fps** |
| Intrusion detector | CPU/ONNX, **733 MB** image, **~2.3 fps** |
| GPU headroom | 3508 MiB free of 4096 |
| Fire image | 12.4 GB (CUDA wheels) |

---

## Open items

1. **Alerts are unreviewed.** ~90 events sit at `status=new` with
   `is_false_positive` unset, so every threshold decision above is reasoned
   from test-set curves rather than measured on the real room. Labelling ~20
   snapshots would settle whether fire really is the noisier class in practice,
   and whether Fire 4 / Smoke 3 should move.
2. **Intrusion on GPU.** The fire detector uses only 534 MiB of 4096, so both
   fit — the earlier claim that they could not was an assumption, never
   measured. Expect ~15–30 fps against the current 2.3. Cost: rebuild against
   the `cu126` index (~12 GB image) and set `INTRUSION_DEVICE=0` with
   `gpus: all`. Maxwell (sm_52) pins it to `torch==2.14.0+cu126`; PyTorch
   dropped sm_5x from its 12.8/12.9 builds.
3. **Dwell timing assumes source fps.** `dwell_frames` is computed from the
   source frame rate, not the achieved inference rate. At 2.3 fps the 0.35 s
   window covers far fewer frames than intended, so confirmation takes longer
   in wall-clock terms than configured. Moving to GPU largely removes this.
4. **Unpinned dependencies.** Both requirements files pin `torch` but leave
   `torchvision`, `ultralytics` and `opencv-python-headless` floating. A
   rebuild months from now could pull an incompatible `torchvision`.
5. **ANPR model not containerised.** Needs its own image because of
   `paddlepaddle`. The pattern is now proven twice.
6. **Both detectors watch the same camera.** Fine for testing; point them at
   different sources for a real demo.
