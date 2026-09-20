"""Intrusion detector service.

Watches a video file or RTSP stream for people entering the intrusion zone and
POSTs every confirmed intrusion to the SFLMS backend as a CameraEvent.

`intrusion_core.py` holds the detection logic (shared with the interactive
runner); this file is the service wrapper: environment configuration, the
MJPEG preview the dashboard embeds, backend delivery, and reconnection.

Environment:
    VIDEO_SOURCE      path or RTSP/HTTP URL of the stream to analyse
    VIDEO_LOOP        "1" to reopen the source when it ends (default 1)
    INTRUSION_ZONE    zone polygon as "x1,y1 x2,y2 ..." in pixels;
                      empty means the whole frame
    DETECTOR_DEVICE   "cpu" or a CUDA index (default 0)
    STREAM_PORT       MJPEG preview port (default 8090)
    MAX_RUNTIME_SECONDS  stop after N seconds; 0 disables

    plus the SFLMS_* ingestion variables read by sflms_client.py.

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

import numpy as np
from ultralytics import YOLO

import intrusion_core as core
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


def parse_zone(raw):
    """Parse "x1,y1 x2,y2 ..." into a polygon, or None for the whole frame."""
    raw = (raw or "").strip()
    if not raw:
        return None
    points = []
    for pair in raw.split():
        x, _, y = pair.partition(",")
        points.append([int(float(x)), int(float(y))])
    if len(points) < 3:
        raise SystemExit("INTRUSION_ZONE needs at least three x,y points.")
    return np.array(points, dtype=np.int32)


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
        self.configured_zone = parse_zone(os.environ.get("INTRUSION_ZONE"))
        self.device = resolve_device()
        self.model_path = resolve_model(self.device)

        # task= is required for .onnx: unlike a .pt, the file carries no
        # record of what the model was trained to do.
        self.model = YOLO(self.model_path, task="detect")
        self.client = SflmsIngestionClient()
        self.stream = StreamServer(
            port=int(os.environ.get("STREAM_PORT", "8090"))
        ).start()

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

    def on_alert(self, person_no, point, track_id, xyxy, conf, entered_at=None):
        if self.frame is None or xyxy is None:
            return
        now = utc_now()
        self.alert_count += 1
        print(
            f"[intrusion] confirmed person P{person_no} (track {track_id}) at {point}",
            flush=True,
        )
        self.client.send_alert(
            frame=self.frame,
            class_name="person",
            confidence=float(conf) if conf is not None else 1.0,
            bbox=xyxy,
            first_seen=self.first_seen.get(track_id, now),
            confirmed_at=now,
            track_id=track_id,
            entered_roi_at=entered_at,
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

        src_fps = core.source_fps(self.video_source)
        eff_fps = src_fps / max(1, int(core.VID_STRIDE))
        state = core.TrackState(
            dwell_frames=round(core.DWELL_CONFIRM_SECONDS * eff_fps),
            stale_frames=round(core.STALE_TRACK_TIMEOUT_S * eff_fps),
            on_alert=self.on_alert,
        )
        zone_polygon = self.configured_zone
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

            frame_idx += 1
            saw_frame = True
            self.frame = result.orig_img.copy()

            if zone_polygon is None:
                h, w = self.frame.shape[:2]
                zone_polygon = core.full_frame_polygon(w, h)
                print(
                    f"[intrusion] zone = full frame ({w}x{h}) @ {src_fps:g} fps",
                    flush=True,
                )

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
                    inside = core.is_inside_zone(point, zone_polygon)
                    self.first_seen.setdefault(track_id, utc_now())
                    state.update(track_id, inside, point, frame_idx, xyxy, det_conf)
                    boxes_info.append((
                        state.display_for(track_id), point, inside,
                        state.dwell_count[track_id],
                        track_id in state.alerted,
                        xyxy,
                    ))

            state.prune_stale(frame_idx)
            # prune_stale drops the track's own bookkeeping; mirror it here or
            # first_seen grows without bound on a long-running camera.
            for gone in set(self.first_seen) - set(state.last_seen):
                self.first_seen.pop(gone, None)

            annotated = core.draw_overlay(self.frame.copy(), zone_polygon, boxes_info)
            inside_n = sum(1 for box in boxes_info if box[2])
            annotated = core.draw_hud(
                annotated,
                f"SFLMS intrusion | persons {len(boxes_info)} | "
                f"inside {inside_n} | alerts {self.alert_count}",
            )
            self.stream.publish(annotated)

        return saw_frame

    # -- service loop ---------------------------------------------------

    def run(self):
        while not self.stopping:
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
            if not self.loop_video:
                print("[intrusion] stream ended", flush=True)
                break
            print("[intrusion] end of stream, restarting", flush=True)
            if not saw_frame:
                time.sleep(RESTART_BACKOFF_SECONDS)

    def close(self):
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
