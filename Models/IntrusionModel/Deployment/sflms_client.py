"""SFLMS ingestion client for the intrusion detector.

Turns a confirmed dwell decision into a CameraEvent on the SFLMS backend.

The backend contract (api/v1/camera_events) is strict for intrusion_alert:
every field in TRACKED_DETECTION_FIELDS must be present and non-null, and
`snapshot_path` must already exist in protected storage under

    security/camera-events/<facility_id>/<camera_id>/<stem>.jpg

There is no upload endpoint, so the snapshot is written directly to the
protected media root -- which is why this process shares that volume with
the backend container.
"""

import json
import os
import queue
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib import request
from urllib.error import HTTPError, URLError

import cv2


CLASS_TO_EVENT_TYPE = {"person": "intrusion_alert"}


def _require(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"{name} is required for SFLMS ingestion.")
    return value


def utc_now():
    return datetime.now(timezone.utc)


def iso(moment):
    return moment.isoformat().replace("+00:00", "Z")


class SflmsConfig:
    def __init__(self):
        self.api_url = os.environ.get(
            "SFLMS_API_URL", "http://backend:8000/api/v1/camera-events/"
        )
        self.key_id = _require("SFLMS_KEY_ID")
        self.secret = _require("SFLMS_SECRET")
        self.camera_id = _require("SFLMS_CAMERA_ID")
        self.facility_id = _require("SFLMS_FACILITY_ID")
        self.roi_id = _require("SFLMS_ROI_ID")
        self.protected_root = Path(
            os.environ.get("SFLMS_PROTECTED_MEDIA_ROOT", "/app/protected_media")
        )
        self.timeout = float(os.environ.get("SFLMS_TIMEOUT", "10"))
        self.max_retries = int(os.environ.get("SFLMS_MAX_RETRIES", "3"))

    @property
    def authorization(self):
        return f"AIKey {self.key_id}:{self.secret}"

    def snapshot_key(self, stem):
        return str(
            PurePosixPath("security")
            / "camera-events"
            / self.facility_id
            / self.camera_id
            / f"{stem}.jpg"
        )


class SflmsIngestionClient:
    """Writes the snapshot, then POSTs the event on a background thread."""

    def __init__(self, config=None):
        self.config = config or SflmsConfig()
        self.queue = queue.Queue(maxsize=100)
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()

    # -- snapshot -------------------------------------------------------

    def _write_snapshot(self, frame, stem):
        """Persist the evidence JPEG where the backend expects to find it."""
        key = self.config.snapshot_key(stem)
        destination = self.config.protected_root / key
        destination.parent.mkdir(parents=True, exist_ok=True)
        encoded, buffer = cv2.imencode(".jpg", frame)
        if not encoded:
            raise RuntimeError("Failed to encode the snapshot frame as JPEG.")
        # Write to a temporary name first: the backend rejects the event if the
        # file is missing, and a half-written file would be worse than none.
        temporary = destination.with_suffix(".jpg.part")
        temporary.write_bytes(buffer.tobytes())
        temporary.replace(destination)
        return key

    # -- payload --------------------------------------------------------

    def build_payload(self, *, class_name, confidence, bbox, first_seen, confirmed_at,
                      snapshot_key, track_id, entered_roi_at):
        object_class = class_name.lower()
        event_type = CLASS_TO_EVENT_TYPE[object_class]
        x1, y1, x2, y2 = (max(0, int(value)) for value in bbox)
        duration = max(0.0, (confirmed_at - first_seen).total_seconds())
        return {
            "event_type": event_type,
            "camera_id": self.config.camera_id,
            "roi_id": self.config.roi_id,
            "source_event_id": str(uuid.uuid4()),
            # Unlike the fire/smoke pipeline, this one really does track
            # objects, so the ByteTrack id is a genuine reference: every event
            # for the same person carries the same track_id and the backend
            # can correlate them.
            "track_id": str(track_id),
            "class": object_class,
            "confidence": round(float(confidence), 6),
            "bbox": {"x1": x1, "y1": y1, "x2": max(x1, x2), "y2": max(y1, y2)},
            "detected_at": iso(first_seen),
            "confirmed_at": iso(confirmed_at),
            "duration_seconds": round(duration, 3),
            "snapshot_path": snapshot_key,
            # Intrusion-only fields the backend requires.
            #
            # entered_roi_at is when this track crossed into the zone, which is
            # earlier than confirmed_at by the dwell time. The backend rejects
            # it if it precedes detected_at, so fall back to detected_at.
            "entered_roi_at": iso(max(entered_roi_at or first_seen, first_seen)),
            # The serializer accepts intrusion_alert only with
            # time_restricted=true, i.e. the event is reported because the zone
            # was off-limits at that moment. This detector treats its zone as
            # always restricted; a deployment with a schedule should check it
            # here and simply not report outside the restricted window.
            "time_restricted": True,
        }

    # -- transport ------------------------------------------------------

    def _post(self, payload):
        body = json.dumps(payload).encode("utf-8")
        http_request = request.Request(
            self.config.api_url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": self.config.authorization,
            },
            method="POST",
        )
        with request.urlopen(http_request, timeout=self.config.timeout) as response:
            return response.status, response.read().decode("utf-8", "replace")

    def _send_with_retry(self, payload):
        delay = 1.0
        for attempt in range(1, self.config.max_retries + 1):
            try:
                status, body = self._post(payload)
                print(f"[sflms] {payload['event_type']} accepted ({status})", flush=True)
                return True
            except HTTPError as error:
                detail = error.read().decode("utf-8", "replace")[:400]
                # 4xx means the payload itself is wrong; retrying cannot help.
                if 400 <= error.code < 500:
                    print(f"[sflms] rejected {error.code}: {detail}", flush=True)
                    return False
                print(f"[sflms] server error {error.code} (attempt {attempt})", flush=True)
            except (URLError, TimeoutError) as error:
                reason = getattr(error, "reason", error)
                print(f"[sflms] unreachable: {reason} (attempt {attempt})", flush=True)

            if attempt < self.config.max_retries:
                time.sleep(delay)
                delay *= 2
        return False

    def _worker(self):
        while True:
            item = self.queue.get()
            try:
                if item is None:
                    return
                self._send_with_retry(item)
            finally:
                self.queue.task_done()

    # -- public ---------------------------------------------------------

    def send_alert(self, *, frame, class_name, confidence, bbox, first_seen, confirmed_at,
                   track_id, entered_roi_at=None):
        stem = f"{class_name.lower()}-{confirmed_at.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
        try:
            snapshot_key = self._write_snapshot(frame, stem)
        except (OSError, RuntimeError) as error:
            print(f"[sflms] snapshot write failed, dropping alert: {error}", flush=True)
            return
        payload = self.build_payload(
            class_name=class_name,
            confidence=confidence,
            bbox=bbox,
            first_seen=first_seen,
            confirmed_at=confirmed_at,
            snapshot_key=snapshot_key,
            track_id=track_id,
            entered_roi_at=entered_roi_at,
        )
        try:
            self.queue.put_nowait(payload)
        except queue.Full:
            print("[sflms] queue full, dropping alert", flush=True)

    def close(self):
        self.queue.put(None)
        self.thread.join(timeout=self.config.timeout + 2)
