"""ANPR detector service.

Reads plates from a video file or RTSP stream and POSTs every vehicle that
crosses the camera's virtual line to the SFLMS backend as a vehicle_entry or
vehicle_exit CameraEvent, with the plate number, the vehicle type and whether
the plate is in the authorized-vehicle registry.

The plate detector, OCR, voting and line geometry are the shared modules of
this folder (models, ocr_paddle, tracking, direction); local_test.py remains
the interactive runner for videos and photos. This file is the service
wrapper: live source, admin settings, backend delivery and the MJPEG preview.

Environment:
    VIDEO_SOURCE          path or RTSP/HTTP URL of the stream to analyse
    VIDEO_LOOP            "1" to reopen the source when it ends (default 1)
    DETECTOR_DEVICE       "cpu" or a CUDA index (default 0)
    STREAM_PORT           MJPEG preview port (default 8090)
    MAX_RUNTIME_SECONDS   stop after N seconds; 0 disables
    ANPR_VEHICLE_EVERY    run the vehicle model every N frames (default 2)
    ANPR_STATS_SECONDS    how often to log the processing rate (default 60)
    ANPR_REPEAT_SECONDS   the same plate crossing the same way again within
                          this long is not a new event (default 30)

    plus the SFLMS_* ingestion variables read by sflms_client.py and the
    ALPR_* model paths read by paths.py.

The virtual line is the one the admin draws for this camera in the SFLMS
console, and the model is switched on and off there (see camera_settings.py).
With no line drawn nothing can cross, so no events are sent; while the model
is off the live view keeps running without inference.

Frames come from a reader thread that keeps only the newest one, so a live
camera never builds up a backlog when inference is slower than the camera.
"""

import os
import signal
import sys
import time

import cv2
import numpy as np

import config
import ocr_paddle as ocr
from camera_settings import CameraSettings
from crossings import (
    PendingCrossings,
    VehicleVotes,
    find_predecessor,
    in_direction,
    plate_confidence,
)
from direction import update_direction
from models import load_models
from sflms_client import SflmsIngestionClient, utc_now
from stream_server import StreamServer
from tracking import TrackState, cleanup_stale_tracks, reset_tracks, tracks, vehicle_number
from video_source import VideoSource
from vehicle import match_vehicle_to_plate


RESTART_BACKOFF_SECONDS = 2.0
VEHICLE_EVERY = max(1, int(os.environ.get("ANPR_VEHICLE_EVERY", "").strip() or 2))
REPEAT_SECONDS = float(os.environ.get("ANPR_REPEAT_SECONDS", "").strip() or 30)
# A lost track can be continued by a new one for this many processed frames.
SPLIT_LOOKBACK_FRAMES = 10
STATS_SECONDS = float(os.environ.get("ANPR_STATS_SECONDS", "").strip() or 60)

GREEN = (0, 255, 0)        # plate read
ORANGE = (0, 200, 255)     # plate detected, OCR still trying
LINE_COLOR = (255, 200, 0)
VEHICLE_COLOR = (0, 255, 255)
DIRECTION_TEXT = {"entry": "ENTRY", "exit": "EXIT"}


def resolve_device():
    override = os.environ.get("DETECTOR_DEVICE", "").strip()
    if not override:
        return 0
    return int(override) if override.isdigit() else override


def text_scale(frame):
    """Line and text size for this frame: scaled with its shorter side, so a
    portrait 1080x1920 video gets the same text as a landscape 1920x1080 one."""
    return max(1.0, min(frame.shape[:2]) / 720.0)


def put_label(frame, text, x, y, scale, color, thickness):
    """Text at (x, y), moved left if it would run off the right edge."""
    (width, _), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, thickness)
    x = max(0, min(x, frame.shape[1] - width - 4))
    cv2.putText(frame, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness,
                cv2.LINE_AA)


def draw_line(frame, line):
    p1, p2 = (tuple(int(v) for v in point) for point in line)
    h = frame.shape[0]
    k = text_scale(frame)
    cv2.line(frame, p1, p2, LINE_COLOR, int(round(2 * k)), cv2.LINE_AA)
    nx, ny = in_direction(p1, p2)
    mid = ((p1[0] + p2[0]) // 2, (p1[1] + p2[1]) // 2)
    tip = (int(mid[0] + nx * 45 * k), int(mid[1] + ny * 45 * k))
    cv2.arrowedLine(frame, mid, tip, LINE_COLOR, int(round(2 * k)), cv2.LINE_AA, tipLength=0.35)
    cv2.putText(frame, config.SIDE_POSITIVE_LABEL, (tip[0] + int(6 * k), tip[1] + int(6 * k)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6 * k, LINE_COLOR, int(round(2 * k)), cv2.LINE_AA)


def draw_hud(frame, text):
    h = frame.shape[0]
    k = text_scale(frame)
    org = (int(10 * k), h - int(12 * k))
    cv2.putText(frame, text, org, cv2.FONT_HERSHEY_SIMPLEX, 0.55 * k, (0, 0, 0),
                int(round(4 * k)), cv2.LINE_AA)
    cv2.putText(frame, text, org, cv2.FONT_HERSHEY_SIMPLEX, 0.55 * k, (255, 255, 255),
                int(round(1 * k)), cv2.LINE_AA)
    return frame


def clamp_box(box, width, height):
    x1, y1, x2, y2 = box
    return (max(0, min(width - 1, int(x1))), max(0, min(height - 1, int(y1))),
            max(0, min(width - 1, int(x2))), max(0, min(height - 1, int(y2))))


class AnprRunner:
    def __init__(self):
        source = os.environ.get("VIDEO_SOURCE", "").strip()
        if not source:
            raise SystemExit(
                "VIDEO_SOURCE is required. A webcam index cannot be used from a "
                "container; pass a file path or an RTSP/HTTP URL."
            )
        self.video_source = int(source) if source.isdigit() else source
        self.loop_video = os.environ.get("VIDEO_LOOP", "1").strip() != "0"
        self.max_runtime = float(os.environ.get("MAX_RUNTIME_SECONDS", "0") or 0)
        self.device = resolve_device()

        reader, self.plate_model, self.vehicle_model = load_models()
        ocr.init_reader(reader)

        self.client = SflmsIngestionClient()
        self.settings = CameraSettings(self.client.config, "anpr", with_line=True).start()
        self.stream = StreamServer(
            port=int(os.environ.get("STREAM_PORT", "").strip() or "8090"),
            info={"camera_id": self.client.config.camera_id, "model": "anpr"},
        ).start()

        self.pending = PendingCrossings(REPEAT_SECONDS)
        self.stats_since = time.monotonic()
        self.stats_frames = 0
        self.new_tracks = 0
        self.stopping = False
        self.started = time.monotonic()
        self.event_count = 0
        self.reset_state()

        print(f"[anpr] device={self.device} source={self.video_source} "
              f"loop={self.loop_video}", flush=True)
        print(f"[anpr] MJPEG stream on http://localhost:{self.stream.port}/stream", flush=True)

    def reset_state(self):
        """Forget every track: after a restart, a switch-off or a new line."""
        reset_tracks()
        self.vehicle_votes = {}
        self.first_seen = {}
        self.pending.pending.clear()
        self.frame_count = 0
        self.line = None

    # -- one frame ------------------------------------------------------

    def detect_plates(self, frame):
        results = self.plate_model.track(
            frame, imgsz=config.YOLO_IMGSZ, conf=config.YOLO_CONF, iou=0.45,
            persist=True, tracker="bytetrack.yaml", device=self.device, verbose=False,
        )
        detections = []
        for result in results:
            if result.boxes is None or result.boxes.id is None:
                continue
            detections += zip(result.boxes.xyxy.cpu().numpy(),
                              result.boxes.id.cpu().numpy().astype(int).tolist(),
                              result.boxes.conf.cpu().numpy())
        in_frame = {tid for _, tid, _ in detections}

        seen = []
        for box, tid, conf in detections:
            box = tuple(int(v) for v in box)
            if tid not in tracks:
                tracks[tid] = TrackState()
                self.new_tracks += 1
                self.continue_split_track(tid, box, in_frame)
            st = tracks[tid]
            st.box = box
            st.last_seen_frame = self.frame_count
            st.det_conf = float(conf)
            self.first_seen.setdefault(tid, utc_now())
            seen.append(tid)

            if self.line is not None:
                x1, y1, x2, y2 = st.box
                centroid = ((x1 + x2) / 2, (y1 + y2) / 2)
                if update_direction(st, centroid, *self.line, self.frame_count):
                    print(f"[anpr] track {tid} crossed -> {st.direction} "
                          f"(plate so far: {st.stable_text or 'unread'})", flush=True)
                    self.pending.crossed(tid, st.direction, centroid, st.box,
                                         self.first_seen[tid])
        return seen

    def continue_split_track(self, tid, box, in_frame):
        """Let a new track carry on a plate track the tracker just lost.

        Without this a crossing is missed whenever the plate's track is split
        near the line, and a crossing seen by the old track, still waiting for
        its plate, is dropped when the old track ends.
        """
        lost = {
            other: st.box for other, st in tracks.items()
            if other not in in_frame and st.box is not None
            and self.frame_count - st.last_seen_frame <= SPLIT_LOOKBACK_FRAMES
        }
        predecessor = find_predecessor(box, lost)
        if predecessor is None:
            return
        old, new = tracks.pop(predecessor), tracks[tid]
        for field in ("current_side", "pending_side", "pending_count", "direction",
                      "stable_text", "stable_votes", "vehicle_id", "vehicle_type",
                      "plate_type"):
            setattr(new, field, getattr(old, field))
        new.history.extend(old.history)
        if predecessor in self.first_seen:
            self.first_seen[tid] = self.first_seen.pop(predecessor)
        if predecessor in self.vehicle_votes:
            self.vehicle_votes[tid] = self.vehicle_votes.pop(predecessor)
        self.pending.hand_over(predecessor, tid)

    def detect_vehicles(self, frame, seen):
        results = self.vehicle_model(
            frame, imgsz=config.YOLO_IMGSZ, conf=config.VEHICLE_CONF,
            device=self.device, verbose=False,
        )
        detections = []
        for result in results:
            if result.boxes is None:
                continue
            for box, cls_id, conf in zip(result.boxes.xyxy.cpu().numpy(),
                                         result.boxes.cls.cpu().numpy().astype(int),
                                         result.boxes.conf.cpu().numpy()):
                name = config.COCO_VEHICLE_CLASSES.get(int(cls_id))
                if name:
                    detections.append((box, name, float(conf)))

        for tid in seen:
            st = tracks[tid]
            # vehicle.match_vehicle_to_plate picks the smallest vehicle box
            # holding the plate's centre; run it on this frame's boxes, then
            # take that box's confidence too, which the backend requires.
            matched = match_vehicle_to_plate(st.box, [(box, name) for box, name, _ in detections])
            if matched is None:
                continue
            candidates = [d for d in detections if d[1] == matched and _contains(d[0], st.box)]
            box, name, conf = min(candidates, key=lambda d: _area(d[0]))
            self.vehicle_votes.setdefault(tid, VehicleVotes()).add(name, conf, box)
            st.vehicle_type = name

    def read_plates(self, frame, seen):
        # Only plates seen in this frame and not yet settled: a lost track's
        # last box is road by now, and a locked plate cannot change.
        for tid in seen:
            st = tracks[tid]
            if st.stable_votes >= config.LOCK_VOTES:
                continue
            crop = ocr.crop_plate(frame, *st.box)
            text, plate_type, conf = ocr.extract_plate_number(crop)
            st.plate_type = plate_type
            if text:
                st.history.append((text, conf))
            voted, votes = ocr.get_voted_text(st.history, config.MIN_VOTES)
            if voted:
                st.stable_text = voted
                st.stable_votes = votes
                st.vehicle_id = vehicle_number(voted)

    def send_ready_crossings(self, frame):
        for tid in list(self.pending.pending):
            st = tracks.get(tid)
            if st is None:
                continue
            votes = self.vehicle_votes.get(tid)
            crossing = self.pending.complete(
                tid,
                plate=st.stable_text,
                ocr_confidence=plate_confidence(st.history, st.stable_text),
                plate_confidence=st.det_conf,
                vehicle=votes.best() if votes else None,
                now=time.monotonic(),
            )
            if crossing is None:
                continue
            self.event_count += 1
            print(f"[anpr] {crossing['direction']} {crossing['plate_number']} "
                  f"({crossing['vehicle_type']}, track {tid})", flush=True)
            self.client.send_crossing(frame=self.evidence_frame(frame, crossing),
                                      crossing=crossing)

    def forget_ended_tracks(self):
        before = set(tracks)
        cleanup_stale_tracks(self.frame_count)
        ended = before - set(tracks)
        for tid in ended:
            self.vehicle_votes.pop(tid, None)
            self.first_seen.pop(tid, None)
        for crossing in self.pending.forget(ended):
            print(f"[anpr] track {crossing['track_id']} crossed {crossing['direction']} "
                  "but its plate or vehicle was never read; no event", flush=True)

    # -- drawing --------------------------------------------------------

    def evidence_frame(self, frame, crossing):
        """The snapshot: line, the vehicle and its plate, and what was read."""
        snap = frame.copy()
        h, w = snap.shape[:2]
        k = text_scale(snap)
        if self.line is not None:
            draw_line(snap, self.line)
        vx1, vy1, vx2, vy2 = clamp_box(crossing["bbox_vehicle"], w, h)
        cv2.rectangle(snap, (vx1, vy1), (vx2, vy2), VEHICLE_COLOR, int(round(2 * k)))
        px1, py1, px2, py2 = clamp_box(crossing["bbox_plate"], w, h)
        cv2.rectangle(snap, (px1, py1), (px2, py2), GREEN, int(round(3 * k)))
        label = (f"{crossing['plate_number']} | {crossing['vehicle_type']} | "
                 f"{DIRECTION_TEXT[crossing['direction']]}")
        put_label(snap, label, px1, max(int(30 * k), py1 - int(10 * k)), 0.65 * k, GREEN,
                  int(round(2 * k)))
        return draw_hud(snap, f"SFLMS ANPR | {utc_now().strftime('%Y-%m-%d %H:%M:%S UTC')}")

    def annotate(self, frame):
        view = frame.copy()
        h, w = view.shape[:2]
        k = text_scale(view)
        if self.line is not None:
            draw_line(view, self.line)
        shown = 0
        for st in tracks.values():
            if st.box is None or self.frame_count - st.last_seen_frame > 2:
                continue
            shown += 1
            x1, y1, x2, y2 = clamp_box(st.box, w, h)
            if st.stable_text is None:
                cv2.rectangle(view, (x1, y1), (x2, y2), ORANGE, int(round(2 * k)))
                continue
            cv2.rectangle(view, (x1, y1), (x2, y2), GREEN, int(round(3 * k)))
            label = f"ID{st.vehicle_id} | {st.stable_text}"
            if st.vehicle_type:
                label += f" | {st.vehicle_type}"
            if st.direction:
                label += f" | {st.direction}"
            put_label(view, label, x1, max(int(30 * k), y1 - int(10 * k)), 0.65 * k, GREEN,
                      int(round(2 * k)))
        if self.line is None:
            return draw_hud(view, "SFLMS ANPR | no virtual line drawn for this camera")
        return draw_hud(view, f"SFLMS ANPR | plates {shown} | events {self.event_count}")

    # -- service loop ---------------------------------------------------

    def process(self, frame):
        if self.settings.line != self.line:
            # A new or removed line: sides measured against the old one mean
            # nothing, and a crossing half-counted on it must not complete.
            self.reset_state()
            self.line = self.settings.line
        self.frame_count += 1
        seen = self.detect_plates(frame)
        if seen and self.frame_count % VEHICLE_EVERY == 0:
            self.detect_vehicles(frame, seen)
        self.read_plates(frame, seen)
        self.send_ready_crossings(frame)
        self.forget_ended_tracks()
        self.stream.publish(self.annotate(frame), raw=frame)
        self.log_throughput()

    def log_throughput(self):
        self.stats_frames += 1
        elapsed = time.monotonic() - self.stats_since
        if elapsed >= STATS_SECONDS:
            print(f"[anpr] {self.stats_frames / elapsed:.1f} frames/s processed, "
                  f"{self.new_tracks} new plate track(s), {self.event_count} event(s) so far",
                  flush=True)
            self.stats_since, self.stats_frames, self.new_tracks = time.monotonic(), 0, 0

    def run(self):
        video = VideoSource(self.video_source)
        was_enabled = True
        try:
            while not self.stopping:
                if self.max_runtime and time.monotonic() - self.started > self.max_runtime:
                    print("[anpr] MAX_RUNTIME_SECONDS reached", flush=True)
                    break
                ok, frame = video.read()
                if not ok:
                    video.release()
                    if not self.loop_video:
                        print("[anpr] stream ended", flush=True)
                        break
                    print("[anpr] end of stream, restarting", flush=True)
                    time.sleep(RESTART_BACKOFF_SECONDS)
                    self.reset_state()
                    video = VideoSource(self.video_source)
                    continue

                if not self.settings.model_enabled:
                    if was_enabled:
                        print("[anpr] model disabled for this camera, streaming only", flush=True)
                        self.reset_state()
                    was_enabled = False
                    view = draw_hud(frame.copy(), "SFLMS ANPR | model disabled for this camera")
                    self.stream.publish(view, raw=frame)
                    continue
                was_enabled = True
                self.process(frame)
        finally:
            video.release()

    def close(self):
        self.settings.close()
        self.stream.close()
        self.client.close()


def _contains(vehicle_box, plate_box):
    vx1, vy1, vx2, vy2 = vehicle_box
    px1, py1, px2, py2 = plate_box
    cx, cy = (px1 + px2) / 2, (py1 + py2) / 2
    mx, my = (vx2 - vx1) * 0.1, (vy2 - vy1) * 0.1
    return vx1 - mx <= cx <= vx2 + mx and vy1 - my <= cy <= vy2 + my


def _area(box):
    return float(np.prod([box[2] - box[0], box[3] - box[1]]))


def main():
    runner = AnprRunner()

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
