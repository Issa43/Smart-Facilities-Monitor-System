"""Headless fire/smoke detection entry point that reports to SFLMS.

`local_test.py` is the interactive tool: it opens an OpenCV window and asks the
operator to drag a region of interest. Neither is possible in a container, so
this module runs the same detector and the same AlertManager with no GUI and no
operator input, and forwards every confirmed alert to the SFLMS backend.

Configuration comes from the environment (see the compose `detector` service):

    VIDEO_SOURCE      path or RTSP/HTTP URL of the stream to analyse
    VIDEO_LOOP        "1" to restart a finite file when it ends (default 1)
    MAX_RUNTIME_SECONDS  optional stop after N seconds (0 = run forever)

Fire and smoke are watched across the whole frame. Whether the model runs at
all is switched per camera in the SFLMS admin console (see camera_settings.py);
while it is off the detector keeps streaming video but stops detecting.

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
from camera_settings import CameraSettings
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


def draw_boxes(canvas, detections):
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


def annotate(frame, detections, status_text):
    """Draw boxes and a status line for the dashboard stream."""
    canvas = frame.copy()
    draw_boxes(canvas, detections)
    cv2.putText(
        canvas, status_text, (10, 24),
        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2, cv2.LINE_AA,
    )
    return canvas


def collect_evidence(detections, frame, now):
    """Group this check's detections by class, with the frame they came from.

    AlertManager stores each entry in the same window as the check, so an alert
    carries evidence only from the checks that confirmed it. The frame is not
    copied: VideoSource.read() already returns a fresh array per frame.
    """
    evidence = {}
    for item in detections:
        entry = evidence.setdefault(
            item["class_name"], {"frame": frame, "boxes": [], "seen_at": now}
        )
        entry["boxes"].append(item)
    return evidence


def build_snapshot(evidence):
    """Pick the strongest frame from the window and draw every box on it.

    The payload's bbox and confidence come from the single strongest box, but
    the snapshot shows all of that class's boxes, so a guard can tell a real
    fire from, say, a lamp that scored higher.
    """
    def strongest(entry):
        return max(entry["boxes"], key=lambda item: item["confidence"])

    best = max(evidence, key=lambda entry: strongest(entry)["confidence"])
    snapshot = best["frame"].copy()
    draw_boxes(snapshot, best["boxes"])
    return {
        "snapshot": snapshot,
        "box": strongest(best),
        "first_seen": min(entry["seen_at"] for entry in evidence),
    }


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
    max_runtime = float(os.environ.get("MAX_RUNTIME_SECONDS", "0"))

    device = resolve_device()
    print(f"[detector] model={MODEL_PATH} device={device}", flush=True)
    print(f"[detector] source={video_source_value} loop={loop_video}", flush=True)

    client = SflmsIngestionClient()
    settings = CameraSettings(client.config, "fire_smoke").start()

    # Compose interpolates an unset ${STREAM_PORT} to an empty string rather
    # than leaving it unset, and os.environ.get would then return "" instead of
    # the default. Treat blank as absent. STREAM_PORT=0 disables the stream.
    stream_port = int(os.environ.get("STREAM_PORT", "").strip() or "8090")
    stream = (
        StreamServer(
            port=stream_port,
            info={"camera_id": client.config.camera_id, "model": "fire_smoke"},
        ).start()
        if stream_port
        else None
    )
    if stream:
        print(f"[detector] MJPEG stream on http://localhost:{stream_port}/stream", flush=True)

    detector = Detector(MODEL_PATH, device)
    alert_manager = AlertManager()

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
                    stream.publish(annotate(frame, last_detections, status), raw=frame)
                continue

            if not settings.model_enabled:
                # Switched off for this camera in the admin console: keep the
                # live view, skip the model, raise nothing.
                last_detections = []
                status = "Fire/smoke model disabled for this camera"
                if stream:
                    stream.publish(annotate(frame, [], status), raw=frame)
                continue

            now = utc_now()
            detections = detector.detect(frame)
            last_detections = detections
            status = (
                f"SFLMS {now.astimezone(_tz.utc).strftime('%H:%M:%S')} UTC | "
                f"objects={len(detections)} alerts={alert_count}"
            )
            if stream:
                stream.publish(annotate(frame, detections, status), raw=frame)

            evidence = collect_evidence(detections, frame, now)
            for alert in alert_manager.update(set(evidence), evidence=evidence):
                class_name = alert["type"]
                best = build_snapshot(alert["evidence"])
                kind = "reminder" if alert["reminder"] else "confirmed"
                print(
                    f"[detector] {class_name} {kind} "
                    f"({alert['positive_checks']}/{alert['window_size']}) "
                    f"conf={best['box']['confidence']:.3f}",
                    flush=True,
                )
                alert_count += 1
                client.send_alert(
                    frame=best["snapshot"],
                    class_name=class_name,
                    confidence=best["box"]["confidence"],
                    bbox=best["box"]["box"],
                    first_seen=best["first_seen"],
                    confirmed_at=now,
                )
    finally:
        video.release()
        settings.close()
        client.close()
        if stream:
            stream.close()
        print("[detector] stopped", flush=True)


if __name__ == "__main__":
    sys.exit(run())
