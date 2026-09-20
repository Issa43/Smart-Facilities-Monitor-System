"""Headless fire/smoke detection entry point that reports to SFLMS.

`local_test.py` is the interactive tool: it opens an OpenCV window and asks the
operator to drag a region of interest. Neither is possible in a container, so
this module runs the same detector and the same AlertManager with no GUI and no
operator input, and forwards every confirmed alert to the SFLMS backend.

Configuration comes from the environment (see the compose `detector` service):

    VIDEO_SOURCE      path or RTSP/HTTP URL of the stream to analyse
    VIDEO_LOOP        "1" to restart a finite file when it ends (default 1)
    DETECTOR_ROI      optional "x,y,w,h" in pixels; omitted means full frame
    MAX_RUNTIME_SECONDS  optional stop after N seconds (0 = run forever)

Detection thresholds stay in config.py so the model's tuned values remain the
single source of truth.
"""

import os
import signal
import sys
import time
from datetime import timezone as _tz

import cv2

from alert_manager import AlertManager
from config import FRAME_SKIP, MODEL_PATH
from config import DEVICE as CONFIG_DEVICE
from detector import Detector
from sflms_client import SflmsIngestionClient, utc_now
from stream_server import StreamServer
from video_source import VideoSource


# Pause between reopen attempts when the source is unavailable.
RESTART_BACKOFF_SECONDS = 2.0


def resolve_device():
    """config.py hard-codes DEVICE=0, which means *CUDA device 0*.

    That is right for this project's GPU host, but it raises rather than
    falling back when no CUDA device is present, so allow an override.
    """
    override = os.environ.get("DETECTOR_DEVICE", "").strip()
    if not override:
        return CONFIG_DEVICE
    return int(override) if override.isdigit() else override


BOX_COLOUR = {"Fire": (0, 0, 255), "Smoke": (255, 165, 0)}


def annotate(frame, detections, roi, status_text):
    """Draw boxes, ROI and a status line for the dashboard stream."""
    canvas = frame.copy()
    for item in detections:
        x1, y1, x2, y2 = item["box"]
        colour = BOX_COLOUR.get(item["class_name"], (0, 255, 0))
        cv2.rectangle(canvas, (x1, y1), (x2, y2), colour, 2)
        cv2.putText(
            canvas,
            f"{item['class_name']} {item['confidence']:.2f}",
            (x1, max(y1 - 8, 18)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, colour, 2, cv2.LINE_AA,
        )
    if roi:
        rx, ry, rw, rh = roi
        cv2.rectangle(canvas, (rx, ry), (rx + rw, ry + rh), (0, 255, 0), 2)
    cv2.putText(
        canvas, status_text, (10, 24),
        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2, cv2.LINE_AA,
    )
    return canvas


def parse_roi(raw):
    if not raw:
        return None
    try:
        x, y, w, h = (int(part.strip()) for part in raw.split(","))
    except ValueError:
        raise SystemExit('DETECTOR_ROI must look like "x,y,w,h" in pixels.')
    if w <= 0 or h <= 0:
        raise SystemExit("DETECTOR_ROI width and height must be positive.")
    return (x, y, w, h)


class WindowEvidence:
    """Keeps the strongest detection seen while a class is being voted on.

    AlertManager only reports *that* a class crossed its threshold. The backend
    needs a bbox, a confidence and a snapshot, so we retain the best frame seen
    since the class first appeared and hand that over when the alert fires.
    """

    def __init__(self):
        self._best = {}

    def observe(self, class_name, confidence, bbox, frame, now):
        current = self._best.get(class_name)
        if current is None:
            self._best[class_name] = {
                "confidence": confidence,
                "bbox": bbox,
                "frame": frame.copy(),
                "first_seen": now,
            }
            return
        current["first_seen"] = min(current["first_seen"], now)
        if confidence > current["confidence"]:
            current.update(confidence=confidence, bbox=bbox, frame=frame.copy())

    def take(self, class_name):
        return self._best.pop(class_name, None)


def run():
    video_source_value = os.environ.get("VIDEO_SOURCE", "").strip()
    if not video_source_value:
        raise SystemExit(
            "VIDEO_SOURCE is required. A webcam index cannot be used from a "
            "container; supply a video file path or an RTSP/HTTP stream URL."
        )
    if video_source_value.isdigit():
        video_source_value = int(video_source_value)

    loop_video = os.environ.get("VIDEO_LOOP", "1") == "1"
    roi = parse_roi(os.environ.get("DETECTOR_ROI", ""))
    max_runtime = float(os.environ.get("MAX_RUNTIME_SECONDS", "0"))

    device = resolve_device()
    print(f"[detector] model={MODEL_PATH} device={device}", flush=True)
    print(f"[detector] source={video_source_value} loop={loop_video} roi={roi}", flush=True)

    # Compose interpolates an unset ${STREAM_PORT} to an empty string rather
    # than leaving it unset, and os.environ.get would then return "" instead of
    # the default. Treat blank as absent. STREAM_PORT=0 disables the stream.
    stream_port = int(os.environ.get("STREAM_PORT", "").strip() or "8090")
    stream = StreamServer(port=stream_port).start() if stream_port else None
    if stream:
        print(f"[detector] MJPEG stream on http://localhost:{stream_port}/stream", flush=True)

    client = SflmsIngestionClient()
    detector = Detector(MODEL_PATH, device)
    alert_manager = AlertManager()
    evidence = WindowEvidence()

    stopping = {"flag": False}

    def stop(signum, _frame):
        print(f"[detector] signal {signum}, shutting down", flush=True)
        stopping["flag"] = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    last_detections = []
    status = "starting"
    alert_count = 0
    started = time.monotonic()
    video = VideoSource(video_source_value)
    frame_count = 0

    try:
        while not stopping["flag"]:
            if max_runtime and time.monotonic() - started > max_runtime:
                print("[detector] MAX_RUNTIME_SECONDS reached", flush=True)
                break

            success, frame = video.read()
            if not success:
                if loop_video and not isinstance(video_source_value, int):
                    print("[detector] end of stream, restarting", flush=True)
                    video.release()
                    # A looping file reopens instantly, but an RTSP source that
                    # nobody is publishing to fails immediately and forever.
                    # Without a pause that turns into a hot loop that pins a
                    # core and floods the log, so back off before retrying.
                    if not stopping["flag"]:
                        time.sleep(RESTART_BACKOFF_SECONDS)
                    video = VideoSource(video_source_value)
                    continue
                print("[detector] stream ended", flush=True)
                break

            frame_count += 1
            if frame_count % FRAME_SKIP:
                # Publish between inferences using the last known boxes so
                # the viewer sees full frame rate, not one frame in FRAME_SKIP.
                if stream:
                    stream.publish(annotate(frame, last_detections, roi, status))
                continue

            now = utc_now()
            detections = detector.detect(frame, roi)
            last_detections = detections
            status = (
                f"SFLMS {now.astimezone(_tz.utc).strftime('%H:%M:%S')} UTC | "
                f"objects={len(detections)} alerts={alert_count}"
            )
            if stream:
                stream.publish(annotate(frame, detections, roi, status))
            for item in detections:
                evidence.observe(
                    item["class_name"],
                    item["confidence"],
                    item["box"],
                    frame,
                    now,
                )

            detected_classes = {item["class_name"] for item in detections}
            for alert in alert_manager.update(detected_classes):
                class_name = alert["type"]
                best = evidence.take(class_name)
                if best is None:
                    # Threshold met on frames whose detections have already been
                    # consumed by a previous alert; nothing to evidence.
                    continue
                print(
                    f"[detector] {class_name} confirmed "
                    f"({alert['positive_checks']}/{alert['window_size']}) "
                    f"conf={best['confidence']:.3f}",
                    flush=True,
                )
                alert_count += 1
                client.send_alert(
                    frame=best["frame"],
                    class_name=class_name,
                    confidence=best["confidence"],
                    bbox=best["bbox"],
                    first_seen=best["first_seen"],
                    confirmed_at=now,
                )
    finally:
        video.release()
        client.close()
        if stream:
            stream.close()
        print("[detector] stopped", flush=True)


if __name__ == "__main__":
    sys.exit(run())
