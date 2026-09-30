# AI detector services

How the fire/smoke, intrusion and ANPR models run against live cameras and
feed the SFLMS backend, what was measured while tuning them, and what is still
open.

See [camera-processing.md](camera-processing.md) for the ingestion contract and
the realtime protocol. This document covers the detector side.

---

## Shape of the system

Each model runs in **its own container**. They share nothing but the Docker
network, the backend API, and the `protected_media` directory.

```
        BROWSER
           │ :8080                 :8090 / :8091 / :8092
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
       /celery broker    │   ┌────┴──────┬───────────┬──────────┐
                         │   │ detector  │ intrusion │   anpr   │
      ┌──────────┐       │   │  (fire)   │           │ (plates) │
      │  celery  │───────┘   └────┬──────┴─────┬─────┴────┬─────┘
      │ worker   │                │ RTSP 8554  │          │
      │  beat    │                ▼            ▼          ▼
      └──────────┘            ┌─────────────────────────────────┐
                              │            mediamtx             │
                              └─────────────────────────────────┘
                                       ▲ RTSP publish
                                  HOST ffmpeg (webcam)
```

A model talks to exactly two things: **mediamtx** for frames in, **backend**
for events out. It never touches Postgres or Redis, and never another model.
Adding a third model is a new service block, not an architectural change.

### Why separate containers

- **Framework weight.** The ANPR model needs PaddleOCR (`paddlepaddle`) next
  to `torch`. It uses the CPU build of PaddlePaddle, which brings no CUDA of
  its own, so the two coexist in the `anpr` image; but its pins (`numpy`, a
  desktop `opencv-contrib`) are reason enough not to share one environment
  with the other models.
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
# infra + app + all three detectors
docker compose --profile detector --profile intrusion --profile anpr up -d

# then publish the laptop webcam from the Windows host
ops/start_laptop_camera.ps1
```

> `docker compose --profile X up` stops services outside that profile. Always
> pass **every** profile you run, or the other detectors get stopped.

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
| anpr | 8092 | MJPEG preview; the admin draws the virtual line on its frame |
| mediamtx | 8554 | RTSP relay |

To test without a camera, put a video in the detector's `samples/` folder
(gitignored, mounted at `/samples`) and point the source at it. Files play at
their own frame rate, not as fast as they decode, and loop when `VIDEO_LOOP=1`:

```powershell
$env:VIDEO_SOURCE="/samples/<fire video>.mp4"            # fire / smoke
$env:INTRUSION_VIDEO_SOURCE="/samples/<people video>.mp4"  # intrusion
$env:ANPR_VIDEO_SOURCE="/samples/VID_sample.mp4"          # ANPR
docker compose --profile detector --profile intrusion --profile anpr up -d
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
When a pass ends early (model switched off, service stopping) the runner closes
ultralytics' stream reader itself: ultralytics does not, and every off/on used
to leave one more RTSP connection open.

### Alarm rules

| Setting | Default | Meaning |
| --- | --- | --- |
| `INTRUSION_DWELL_SECONDS` | 1.0 | time inside a restricted ROI before the alarm |
| `INTRUSION_REARM_SECONDS` | 2.0 | time outside before the same person can alarm again |
| `INTRUSION_STALE_SECONDS` | 10 | a track unseen this long is forgotten |

A person is inside when their **foot point** (bottom-centre of the box) is in
an ROI that is restricted right now. They raise **one alarm** after the dwell
time, and another only after leaving for the re-arm time — feet on an ROI edge
flicker in and out, and each flicker used to be a new alarm.

Times are measured in seconds, not frames: real time for a live camera, the
video's own timeline for a file. The old frame counts assumed 25 fps, but on a
live stream ultralytics hands over only the newest frame and the CPU runs
~2 inferences/s, so "0.35 s" took ~4.5 s and a track was forgotten after ~2 min.
1 s rather than 0.35 s, because with correct timing 0.35 s alarms on anyone
clipping an ROI corner while walking past.

The snapshot shows the ROIs and the person who raised the alarm in red, with
the ROI name and time.

> Each new track id is a new person to the detector. A tracker id switch in a
> crowd, or a looping test video (every loop restarts all tracks), therefore
> raises a new alarm for someone already reported. The 11 s `PeopleWalking.mp4`
> loop with an ROI over the whole hall gives ~10 alarms per loop for that reason.

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

`time_restricted` is always `true` because the detector only reports people in
an ROI that is restricted at that moment. Each ROI's restricted-hours schedule
(`/api/v1/restricted-schedules/`) is read with the ROIs; an ROI without one is
always restricted. Outside its hours an ROI is drawn grey and marked "(open)",
and people in it raise nothing.

---

## ANPR detector

`Models/LicensePLatesDetectionModel(with_OCR)/Deployment/` — `headless.py` is
the service runner, `local_test.py` remains the interactive one for videos and
photos. The plate detector, PaddleOCR reading, voting and line geometry are the
modules the deployment README measures (96.4 % exact reads, no wrong reads, on
83 photos); the service adds what a live gate needs around them.

| Setting | Default | Meaning |
| --- | --- | --- |
| `ANPR_REPEAT_SECONDS` | 30 | the same plate crossing the same way again within this is one vehicle |
| `ANPR_VEHICLE_EVERY` | 2 | run the vehicle model every N processed frames |
| `ANPR_DEVICE` | 0 | GPU for the plate and vehicle models; OCR is always CPU |

A vehicle crossing the admin's line becomes `vehicle_entry` (towards the side
the arrow on the line points to) or `vehicle_exit`. The backend needs the plate
number, the vehicle type and box on every such event, and a car usually crosses
before its plate is readable, so **a crossing waits on its track** until the
plate is confirmed (3 agreeing reads) and the vehicle model has matched it; it
is dropped, with a log line, if the track ends first.

At the ~14 frames/s the service processes, a plate moves more than its own
height between frames and ByteTrack keeps giving it new ids. A track born just
past the line then never sees itself cross. **A new track within two plate
widths of a track lost in the last 10 frames continues it** — its side of the
line, its readings, any crossing still waiting. On the one-car sample this took
the crossings caught from 2 of 5 loops to every loop.

`authorized` must equal the backend's registry at the moment it stores the
event, so the client asks `/vehicles/authorized/?plate_number=` right before
each POST and asks again once if the POST is rejected for a registry change.
Unauthorized vehicles raise a security alert; authorized ones are logged only.
Register plates as the detector reads them, e.g. `17-42414`.

The image is built on `python:3.12-slim` by default. Set
`ANPR_BASE_IMAGE=sflms-detector:dev` to build it on the fire image instead:
pip then finds the same torch + CUDA already installed and downloads only
PaddlePaddle (CPU) and PaddleOCR. A from-scratch build here timed out
downloading the CUDA wheels from `pypi.nvidia.com`; the layered one took ~30
minutes. PaddleOCR fetches its ~10 MB model on first start into the
`anpr_paddlex` volume.

---

## Admin control: model switch, ROIs and the virtual line

Every detector reads its camera's settings from the backend at startup and
every `CONFIG_REFRESH_SECONDS` (30 s) through `camera_settings.py`, using its
own AI key: `GET /api/v1/cameras/<id>/active-models/`; for intrusion also
`GET /api/v1/roi/?camera_id=<id>` and `restricted-schedules`, for ANPR
`GET /api/v1/virtual-lines/?camera_id=<id>`. If the backend is unreachable the
last known settings stay in force.

| | Fire / smoke | Intrusion | ANPR |
| --- | --- | --- | --- |
| Area watched | whole frame, no ROI | the ROIs the admin drew; none drawn = no alerts | the virtual line; none drawn = no events |
| Model switched off | stops inferring, live view shows "model disabled" | same | same |
| Event `roi_id` | not sent | the ROI the person was standing in | not sent |
| Restricted hours | — | an ROI's schedule; outside it the ROI is "open" and raises nothing | — |

The admin draws ROIs in **Super Admin → AI camera configuration** by clicking
points on the intrusion detector's live frame (`/snapshot/raw` on its stream
port). `/info` on the same port names the camera the detector watches, so the
page warns when the frame belongs to a different camera. The backend also
rejects events from a switched-off model, so turning a model off takes effect
immediately even before the detector's next refresh.

The virtual line is drawn the same way, on the ANPR detector's frame (port
8092): two clicks, and an arrow shows which side counts as entry. Drawing again
replaces the current line. A camera has one line and an ROI one schedule, and
disabling is soft, so the backend reuses a disabled line or schedule for the
next one; before, the disabled row kept the slot and every new one was a 409.

---

## Diagrams

The detector diagrams live in `Diagrams/AI/ModelsPipeline/`, one folder per
model, each as an editable `.drawio` file with a PNG export beside it.

| Diagram | Shows |
| --- | --- |
| `FireAndSmoke/FireAndSmokePipelineV5` | per-frame activity: sampling, model switch, YOLO26 preprocessing, inference, NMS, the sliding window and the incident / reminder logic |
| `FireAndSmoke/FireAndSmokeVideoDataFlow` | webcam → ffmpeg → MediaMTX → detector → MJPEG / backend |
| `FireAndSmoke/FireAndSmokeIncidentStates` | the per-class incident state machine |
| `FireAndSmoke/FireAlarmSequence` | one alarm from confirmation to the security officer, including rejection |
| `FireAndSmoke/AIServicesDeployment` | every container of the system, including all three detectors, its port and what it talks to |
| `Intrusion/IntrusionPipeline` | per-frame activity: model switch, YOLO26 + ByteTrack, day / night confidence, restricted ROIs, dwell, re-arm |
| `Intrusion/IntrusionVideoDataFlow` | webcam → MediaMTX → detector → MJPEG, plus the admin drawing ROIs on `/snapshot/raw` |
| `Intrusion/IntrusionPersonStates` | the per-person state machine: outside, inside, alarmed |
| `Intrusion/IntrusionAlarmSequence` | admin setup, the 30 s settings refresh, and one alarm to the security officer |
| `ANPR/AnprPipeline` | per-frame activity: model switch and line, YOLO26 plate detection, ByteTrack and split tracks, OCR voting, crossings, vehicle matching, repeats and sending |
| `ANPR/AnprVideoDataFlow` | camera → MediaMTX → detector → MJPEG / backend, plus the admin drawing the line |
| `ANPR/AnprCrossingStates` | how a crossing waits for its plate and vehicle, moves with a split track, and is sent or dropped |
| `ANPR/AnprVehicleSequence` | admin setup, the settings refresh, the registry check and one vehicle event to the security officer |

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
| ANPR detector | GPU plates + vehicles, CPU OCR, **~14 fps** in the container on the 1080×1920 sample |
| ANPR image | 14.1 GB, ~12.4 GB of it shared with the fire image when built on it |
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
3. **Tracker memory is still in frames.** ByteTrack's `track_buffer` (90
   frames, 3.75 s at 24 fps) is counted in processed frames, so at ~2 fps on a
   live CPU stream it holds a lost track for ~45 s. The alarm rules no longer
   depend on it; moving to GPU brings it back near its intended length.
4. **Unpinned dependencies.** Both requirements files pin `torch` but leave
   `torchvision`, `ultralytics` and `opencv-python-headless` floating. A
   rebuild months from now could pull an incompatible `torchvision`.
5. **ANPR verified on one clip.** The service was run on the 14.9 s one-car
   sample video only. A real gate camera, several vehicles at once, night
   footage and plates that only become readable past the line are untested.
6. **All detectors default to the same webcam feed.** Fine for testing; point
   them at different sources for a real demo.
