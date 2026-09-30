"""Intrusion detector service.

Watches a video file or RTSP stream for people entering the intrusion zone and
POSTs every confirmed intrusion to the SFLMS backend as a CameraEvent.

`intrusion_core.py` holds the detection logic (shared with the interactive
runner); this file is the service wrapper: environment configuration, the
MJPEG preview the dashboard embeds, backend delivery, and reconnection.

Environment:
    VIDEO_SOURCE      path or RTSP/HTTP URL of the stream to analyse
    VIDEO_LOOP        "1" to reopen the source when it ends (default 1)
    DETECTOR_DEVICE   "cpu" or a CUDA index (default 0)
    STREAM_PORT       MJPEG preview port (default 8090)
    MAX_RUNTIME_SECONDS  stop after N seconds; 0 disables

    plus the SFLMS_* ingestion variables read by sflms_client.py.

The intrusion zones are the ROIs the admin draws for this camera in the SFLMS
console, and the model itself is switched on and off there per camera (see
camera_settings.py). With no ROI drawn nothing can be an intrusion, so no
alerts are raised; while the model is off the live view keeps running without
inference. An ROI with a restricted-hours schedule only raises alarms inside
those hours; an ROI without one is always restricted.

Unlike the fire/smoke detector this pipeline tracks objects, so ultralytics
owns the capture loop (model.track(stream=True)): ByteTrack needs contiguous
frames and persist=True to keep track ids stable, which a separate reader
thread handing over "the latest frame" would break.
"""

import os
import signal
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

import intrusion_core as core
from camera_settings import CameraSettings
from sflms_client import SflmsIngestionClient, utc_now
from stream_server import StreamServer


PROJECT_DIR = Path(__file__).resolve().parent
ONNX_WEIGHTS = PROJECT_DIR / "yolo26n.onnx"
TORCH_WEIGHTS = PROJECT_DIR / "yolo26n.pt"
TRACKER_CFG = os.environ.get("TRACKER_CFG", "").strip() or str(
    PROJECT_DIR / "bytetrack_sfms.yaml"
)

# Pause between reopen attempts when the source is unavailable. Without it a
# dead RTSP URL becomes a hot loop that pins a core and floods the log.
RESTART_BACKOFF_SECONDS = 2.0


def resolve_device():
    override = os.environ.get("DETECTOR_DEVICE", "").strip()
    if not override:
        return 0
    return int(override) if override.isdigit() else override


def resolve_model(device):
    """Pick the weights that match the device unless told otherwise.

    The two sensible configurations are ONNX Runtime on CPU and PyTorch on
    CUDA. Mixing them is a silent trap: this image installs plain
    onnxruntime, whose only execution provider is CPU, so asking for
    DETECTOR_DEVICE=0 while pointing at the .onnx graph would quietly keep
    running on the CPU while looking like it had moved to the GPU.
    """
    override = os.environ.get("MODEL_PATH", "").strip()
    if override:
        return override
    return str(TORCH_WEIGHTS if device != "cpu" else ONNX_WEIGHTS)


def zones_from(rois):
    """Backend ROIs as (roi_id, label, polygon, schedule) for drawing and hit tests."""
    zones = []
    for roi in rois:
        # cv2.putText draws only ASCII; an Arabic ROI name would come out as '?'.
        label = roi["name"] if roi["name"].isascii() else "ROI"
        polygon = np.array(roi["polygon"], dtype=np.int32)
        zones.append((roi["id"], label, polygon, roi.get("schedule")))
    return zones


class IntrusionRunner:
    """One detector process: model, zone, backend client and MJPEG preview."""

    def __init__(self):
        self.video_source = os.environ.get("VIDEO_SOURCE", "").strip()
        if not self.video_source:
            raise SystemExit(
                "VIDEO_SOURCE is required. A webcam index cannot be used from a "
                "container; pass a file path or an RTSP/HTTP URL."
            )
        self.loop_video = os.environ.get("VIDEO_LOOP", "1").strip() != "0"
        self.max_runtime = float(os.environ.get("MAX_RUNTIME_SECONDS", "0") or 0)
        self.device = resolve_device()
        self.model_path = resolve_model(self.device)

        # task= is required for .onnx: unlike a .pt, the file carries no
        # record of what the model was trained to do.
        self.model = YOLO(self.model_path, task="detect")
        self.client = SflmsIngestionClient()
        self.settings = CameraSettings(
            self.client.config, "intrusion", with_rois=True
        ).start()
        self.stream = StreamServer(
            port=int(os.environ.get("STREAM_PORT", "8090")),
            info={"camera_id": self.client.config.camera_id, "model": "intrusion"},
        ).start()
        self.zones = []
        self._zones_source = None
        # ROI ids restricted at the current frame; recomputed every frame
        # because a schedule can start or end at any moment.
        self.restricted = set()

        self.stopping = False
        self.started = time.monotonic()
        self.alert_count = 0
        # The frame being processed, so the alert callback can attach it as the
        # snapshot: the callback fires from inside TrackState.update, which has
        # no access to the frame itself.
        self.frame = None
        self.first_seen = {}

        print(f"[intrusion] model={self.model_path} device={self.device}", flush=True)
        print(
            f"[intrusion] source={self.video_source} loop={self.loop_video}", flush=True
        )
        print(
            f"[intrusion] MJPEG stream on http://localhost:{self.stream.port}/stream",
            flush=True,
        )

    # -- alerting -------------------------------------------------------

    def roi_containing(self, point):
        """The restricted ROI the point stands in, or None."""
        for roi_id, _, polygon, _ in self.zones:
            if roi_id in self.restricted and core.is_inside_zone(point, polygon):
                return roi_id
        return None

    def zones_to_draw(self):
        return [
            (label, polygon, roi_id in self.restricted)
            for roi_id, label, polygon, _ in self.zones
        ]

    def evidence_frame(self, person_no, point, xyxy, roi_id):
        """The snapshot: the ROIs and the person who raised the alarm, in red."""
        # inside=False only drops the dwell from the label; confirmed=True
        # still draws the box red.
        frame = core.draw_overlay(
            self.frame.copy(),
            self.zones_to_draw(),
            [(person_no, point, False, 0.0, True, xyxy)],
        )
        label = next(label for zone_id, label, _, _ in self.zones if zone_id == roi_id)
        stamp = utc_now().strftime("%Y-%m-%d %H:%M:%S UTC")
        return core.draw_hud(frame, f"SFLMS intrusion | P{person_no} in {label} | {stamp}")

    def on_alert(self, person_no, point, track_id, xyxy, conf, entered_at=None):
        if self.frame is None or xyxy is None:
            return
        roi_id = self.roi_containing(point)
        if roi_id is None:
            # The ROI was removed between the dwell starting and confirming.
            return
        now = utc_now()
        self.alert_count += 1
        print(
            f"[intrusion] confirmed person P{person_no} (track {track_id}) at {point}",
            flush=True,
        )
        self.client.send_alert(
            frame=self.evidence_frame(person_no, point, xyxy, roi_id),
            class_name="person",
            confidence=float(conf) if conf is not None else 1.0,
            bbox=xyxy,
            first_seen=self.first_seen.get(track_id, now),
            confirmed_at=now,
            track_id=track_id,
            entered_roi_at=entered_at,
            roi_id=roi_id,
        )

    # -- one pass over the source ---------------------------------------

    def run_pass(self):
        """Consume the source until it ends. Returns True if any frame arrived."""
        results = self.model.track(
            source=self.video_source,
            classes=[core.PERSON_CLASS_ID],
            conf=core.CONF_THRESHOLD,
            imgsz=core.IMGSZ,
            tracker=TRACKER_CFG,
            vid_stride=max(1, int(core.VID_STRIDE)),
            device=self.device,
            persist=True,
            stream=True,
            verbose=False,
        )

        # A file is processed at inference speed, so its clock is its own
        # timeline (frame number / fps). A live source is processed as it
        # arrives, with frames dropped when inference falls behind, so its
        # clock is real time.
        is_file = os.path.isfile(self.video_source)
        seconds_per_frame = max(1, int(core.VID_STRIDE)) / core.source_fps(self.video_source)
        state = core.TrackState(
            dwell_seconds=core.DWELL_CONFIRM_SECONDS,
            stale_seconds=core.STALE_TRACK_TIMEOUT_S,
            rearm_seconds=core.REARM_SECONDS,
            on_alert=self.on_alert,
        )
        try:
            return self._consume(results, state, is_file, seconds_per_frame)
        finally:
            # ultralytics never stops its stream reader when the consumer
            # stops early (model switched off, service stopping): the reader
            # thread and its RTSP connection stayed open, one more every time
            # the model was switched off and on again.
            results.close()
            dataset = getattr(getattr(self.model, "predictor", None), "dataset", None)
            if dataset is not None and hasattr(dataset, "close"):
                dataset.close()

    def _consume(self, results, state, is_file, seconds_per_frame):
        night_mode = None
        frame_idx = 0
        saw_frame = False

        for result in results:
            if self.stopping:
                break
            if self.max_runtime and time.monotonic() - self.started > self.max_runtime:
                print("[intrusion] MAX_RUNTIME_SECONDS reached", flush=True)
                self.stopping = True
                break

            if not self.settings.model_enabled:
                # Switched off in the admin console: stop inferring. run()
                # takes over with the plain live view.
                break

            frame_idx += 1
            saw_frame = True
            now = frame_idx * seconds_per_frame if is_file else time.monotonic()
            self.frame = result.orig_img.copy()
            if self.settings.rois is not self._zones_source:
                self._zones_source = self.settings.rois
                self.zones = zones_from(self.settings.rois)
            moment = utc_now()
            self.restricted = {
                roi_id for roi_id, _, _, schedule in self.zones
                if core.restricted_now(schedule, moment)
            }

            dark = core.frame_is_dark(self.frame)
            active_conf = core.CONF_NIGHT if dark else core.CONF_DAY
            if dark != night_mode:
                night_mode = dark
                print(
                    f"[intrusion] {'night' if dark else 'day'} mode, conf {active_conf}",
                    flush=True,
                )

            boxes_info = []
            boxes = result.boxes
            if boxes is not None and boxes.id is not None:
                for track_id, xyxy, det_conf in zip(
                    boxes.id.tolist(), boxes.xyxy.tolist(), boxes.conf.tolist()
                ):
                    if det_conf < active_conf:
                        continue
                    track_id = int(track_id)
                    point = core.foot_point(xyxy, self.frame.shape)
                    inside = self.roi_containing(point) is not None
                    self.first_seen.setdefault(track_id, utc_now())
                    state.update(track_id, inside, point, now, xyxy, det_conf)
                    boxes_info.append((
                        state.display_for(track_id), point, inside,
                        state.dwell(track_id, now),
                        track_id in state.alerted,
                        xyxy,
                    ))

            state.prune_stale(now)
            # prune_stale drops the track's own bookkeeping; mirror it here or
            # first_seen grows without bound on a long-running camera.
            for gone in set(self.first_seen) - set(state.last_seen):
                self.first_seen.pop(gone, None)

            annotated = core.draw_overlay(
                self.frame.copy(), self.zones_to_draw(), boxes_info
            )
            inside_n = sum(1 for box in boxes_info if box[2])
            if not self.zones:
                hud = "SFLMS intrusion | no ROI drawn for this camera"
            elif not self.restricted:
                hud = "SFLMS intrusion | no ROI restricted right now"
            else:
                hud = (
                    f"SFLMS intrusion | persons {len(boxes_info)} | "
                    f"inside {inside_n} | alerts {self.alert_count}"
                )
            annotated = core.draw_hud(annotated, hud)
            self.stream.publish(annotated, raw=self.frame)

        return saw_frame

    # -- model switched off ---------------------------------------------

    def run_paused(self):
        """Keep the live view (and ROI drawing) going while the model is off."""
        print("[intrusion] model disabled for this camera, streaming only", flush=True)
        is_file = "://" not in self.video_source
        capture = cv2.VideoCapture(self.video_source)
        fps = capture.get(cv2.CAP_PROP_FPS) if is_file else 0
        interval = 1 / fps if fps and fps > 0 else 0
        try:
            while not self.stopping and not self.settings.model_enabled:
                if self.max_runtime and time.monotonic() - self.started > self.max_runtime:
                    self.stopping = True
                    break
                ok, frame = capture.read()
                if not ok:
                    capture.release()
                    time.sleep(RESTART_BACKOFF_SECONDS)
                    capture = cv2.VideoCapture(self.video_source)
                    continue
                hud = core.draw_hud(
                    frame.copy(), "SFLMS intrusion | model disabled for this camera"
                )
                self.stream.publish(hud, raw=frame)
                if interval:
                    time.sleep(interval)
        finally:
            capture.release()

    # -- service loop ---------------------------------------------------

    def run(self):
        while not self.stopping:
            if not self.settings.model_enabled:
                self.run_paused()
                continue
            try:
                saw_frame = self.run_pass()
            except (ConnectionError, OSError) as error:
                # ultralytics raises ConnectionError from inside the generator
                # when the source cannot be opened. That means "the camera is
                # down", not "stop the service", so it takes the same
                # backoff-and-retry path as a source that ended.
                if self.stopping or not self.loop_video:
                    print(f"[intrusion] source unavailable: {error}", flush=True)
                    break
                print(f"[intrusion] source unavailable, retrying: {error}", flush=True)
                time.sleep(RESTART_BACKOFF_SECONDS)
                continue

            if self.stopping:
                break
            if not self.settings.model_enabled:
                continue
            if not self.loop_video:
                print("[intrusion] stream ended", flush=True)
                break
            print("[intrusion] end of stream, restarting", flush=True)
            if not saw_frame:
                time.sleep(RESTART_BACKOFF_SECONDS)

    def close(self):
        self.settings.close()
        self.stream.close()
        self.client.close()


def main():
    runner = IntrusionRunner()

    def stop(signum, frame):
        runner.stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    try:
        runner.run()
    finally:
        runner.close()


if __name__ == "__main__":
    sys.exit(main())
