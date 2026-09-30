"""SFLMS ingestion client for the ANPR detector.

Turns a vehicle that crossed the virtual line into a vehicle_entry or
vehicle_exit CameraEvent on the SFLMS backend.

The backend contract (api/v1/camera_events) for vehicle events:

- every field in VEHICLE_REQUIRED_FIELDS must be present and non-null, and
  nothing outside them may be sent (no class, confidence, bbox, confirmed_at);
- `authorized` must equal the backend's own authorized-vehicle registry at the
  moment it stores the event, so the client asks the registry right before it
  posts, and asks again once if the registry changed in between;
- `snapshot_path` must already exist in protected storage under

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
from urllib import parse, request
from urllib.error import HTTPError, URLError

import cv2


EVENT_TYPE_BY_DIRECTION = {"entry": "vehicle_entry", "exit": "vehicle_exit"}


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
        self.protected_root = Path(
            os.environ.get("SFLMS_PROTECTED_MEDIA_ROOT", "/app/protected_media")
        )
        self.timeout = float(os.environ.get("SFLMS_TIMEOUT", "10"))
        self.max_retries = int(os.environ.get("SFLMS_MAX_RETRIES", "3"))

    @property
    def authorization(self):
        return f"AIKey {self.key_id}:{self.secret}"

    @property
    def api_base(self):
        return self.api_url.rsplit("camera-events", 1)[0]

    def snapshot_key(self, stem):
        return str(
            PurePosixPath("security")
            / "camera-events"
            / self.facility_id
            / self.camera_id
            / f"{stem}.jpg"
        )


def _box(box):
    x1, y1, x2, y2 = (max(0, int(value)) for value in box)
    return {"x1": x1, "y1": y1, "x2": max(x1, x2), "y2": max(y1, y2)}


class SflmsIngestionClient:
    """Writes the snapshot, then checks the registry and POSTs on a background thread."""

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

    def build_payload(self, *, crossing, snapshot_key):
        """The event for one crossing; `authorized` is filled in just before sending."""
        return {
            "event_type": EVENT_TYPE_BY_DIRECTION[crossing["direction"]],
            "camera_id": self.config.camera_id,
            "source_event_id": str(uuid.uuid4()),
            # The ByteTrack id of the track that crossed. Several tracks can
            # belong to one vehicle; the plate is what identifies it.
            "track_id": str(crossing["track_id"]),
            "detected_at": iso(crossing["detected_at"]),
            "plate_number": crossing["plate_number"],
            # The detector's confidence that this is a plate, and the OCR
            # confidence of the plate number it was read as.
            "plate_confidence": round(float(crossing["plate_confidence"]), 6),
            "ocr_confidence": round(float(crossing["ocr_confidence"]), 6),
            "vehicle_type": crossing["vehicle_type"],
            "vehicle_confidence": round(float(crossing["vehicle_confidence"]), 6),
            "direction": crossing["direction"],
            "crossing_centroid": {
                "x": max(0, int(crossing["centroid"][0])),
                "y": max(0, int(crossing["centroid"][1])),
            },
            "bbox_plate": _box(crossing["bbox_plate"]),
            "bbox_vehicle": _box(crossing["bbox_vehicle"]),
            "snapshot_path": snapshot_key,
            "authorized": None,
        }

    # -- transport ------------------------------------------------------

    def _request(self, url, *, payload=None):
        headers = {"Authorization": self.config.authorization}
        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        http_request = request.Request(
            url, data=data, headers=headers, method="POST" if data else "GET"
        )
        with request.urlopen(http_request, timeout=self.config.timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8") or "null")

    def is_authorized(self, plate_number):
        """The backend registry's answer for this plate, right now."""
        query = parse.urlencode({"plate_number": plate_number})
        _, body = self._request(f"{self.config.api_base}vehicles/authorized/?{query}")
        return bool(body["authorized"])

    def _send_with_retry(self, payload):
        delay = 1.0
        registry_retry = True
        attempt = 1
        while attempt <= self.config.max_retries:
            try:
                payload["authorized"] = self.is_authorized(payload["plate_number"])
                status, _ = self._request(self.config.api_url, payload=payload)
                state = "authorized" if payload["authorized"] else "NOT authorized"
                print(
                    f"[sflms] {payload['event_type']} {payload['plate_number']} "
                    f"({state}) accepted ({status})",
                    flush=True,
                )
                return True
            except HTTPError as error:
                detail = error.read().decode("utf-8", "replace")[:400]
                # The registry changed between the lookup and the POST: look it
                # up again, once. Any other 4xx means the payload is wrong.
                if error.code == 400 and '"authorized"' in detail and registry_retry:
                    registry_retry = False
                    continue
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
            attempt += 1
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

    def send_crossing(self, *, frame, crossing):
        stamp = utc_now().strftime("%Y%m%d-%H%M%S")
        stem = f"vehicle-{crossing['direction']}-{stamp}-{uuid.uuid4().hex[:8]}"
        try:
            snapshot_key = self._write_snapshot(frame, stem)
        except (OSError, RuntimeError) as error:
            print(f"[sflms] snapshot write failed, dropping event: {error}", flush=True)
            return
        payload = self.build_payload(crossing=crossing, snapshot_key=snapshot_key)
        try:
            self.queue.put_nowait(payload)
        except queue.Full:
            print("[sflms] queue full, dropping event", flush=True)

    def close(self):
        self.queue.put(None)
        self.thread.join(timeout=self.config.timeout + 2)
