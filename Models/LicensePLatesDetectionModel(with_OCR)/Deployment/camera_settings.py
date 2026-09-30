"""What the SFLMS admin console has configured for this detector's camera.

The admin switches AI models on and off per camera, draws ROIs on it (each with
optional restricted hours) and draws its virtual line. The detector polls those
settings in the background, so a change takes effect within
CONFIG_REFRESH_SECONDS without restarting anything. When the backend cannot be
reached the last known settings stay in force.

The fire/smoke, intrusion and ANPR detectors each keep an identical copy of
this file, because each is built as its own container.
"""

import json
import os
import threading
from urllib import request
from urllib.error import HTTPError, URLError


class CameraSettings:
    def __init__(self, config, model_identifier, *, with_rois=False, with_line=False):
        self.config = config
        self.model_identifier = model_identifier
        self.with_rois = with_rois
        self.with_line = with_line
        self.refresh_seconds = float(os.environ.get("CONFIG_REFRESH_SECONDS", "30"))
        self.api_base = config.api_url.rsplit("camera-events", 1)[0]
        # Until the backend answers, assume the model is on: a detector that
        # cannot reach its configuration should not silently stop watching.
        self.model_enabled = True
        self.rois = []
        # The virtual line as ((x1, y1), (x2, y2)), or None when none is drawn.
        self.line = None
        self._stopped = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self.refresh()
        self._thread.start()
        return self

    def close(self):
        self._stopped.set()

    def _run(self):
        while not self._stopped.wait(self.refresh_seconds):
            self.refresh()

    def refresh(self):
        try:
            models = self._get(f"cameras/{self.config.camera_id}/active-models/")
            enabled = any(
                item.get("model_identifier") == self.model_identifier
                and item.get("is_active", True)
                for item in models
            )
            rois = self._fetch_rois() if self.with_rois else []
            line = self._fetch_line() if self.with_line else None
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, KeyError) as error:
            print(f"[settings] refresh failed, keeping last known: {error}", flush=True)
            return

        if enabled != self.model_enabled:
            state = "enabled" if enabled else "disabled"
            print(f"[settings] {self.model_identifier} model {state} for this camera", flush=True)
        if rois == self.rois:
            # Keep the same object, so a detector that checks `is` for a change
            # does not rebuild its zones every refresh.
            rois = self.rois
        elif self.with_rois:
            print(f"[settings] {len(rois)} ROI(s) for this camera", flush=True)
        if self.with_line and line != self.line:
            print(f"[settings] virtual line {line or 'not drawn'}", flush=True)
        self.model_enabled = enabled
        self.rois = rois
        self.line = line

    def _fetch_rois(self):
        camera = self.config.camera_id
        # An ROI's restricted hours; an ROI without a schedule is always
        # restricted. The backend only returns active ones to a detector.
        schedules = {
            item["roi_id"]: {
                "always_restricted": item["always_restricted"],
                "from_time": item["from_time"],
                "to_time": item["to_time"],
                "days_of_week": item["days_of_week"],
                "timezone_name": item["timezone_name"],
            }
            for item in self._get_all(f"restricted-schedules/?camera_id={camera}")
        }
        return [
            {
                "id": item["id"],
                "name": item["name"],
                "polygon": [_xy(point) for point in item["polygon"]],
                "schedule": schedules.get(item["id"]),
            }
            for item in self._get_all(f"roi/?camera_id={camera}")
        ]

    def _fetch_line(self):
        # A camera has at most one active line; the backend returns only that.
        lines = self._get_all(f"virtual-lines/?camera_id={self.config.camera_id}")
        if not lines:
            return None
        return (_xy(lines[0]["line_start"]), _xy(lines[0]["line_end"]))

    def _get_all(self, url):
        """Every item of a list endpoint, following pagination."""
        items = []
        while url:
            page = self._get(url)
            items.extend(page["results"] if isinstance(page, dict) else page)
            url = page.get("next") if isinstance(page, dict) else None
        return items

    def _get(self, path_or_url):
        url = path_or_url if "://" in path_or_url else self.api_base + path_or_url
        http_request = request.Request(
            url, headers={"Authorization": self.config.authorization}, method="GET"
        )
        with request.urlopen(http_request, timeout=self.config.timeout) as response:
            return json.loads(response.read().decode("utf-8"))


def _xy(point):
    """A point as (x, y). The API stores {"x": .., "y": ..}; points created
    outside the API may hold plain [x, y] pairs, which are accepted too."""
    if isinstance(point, dict):
        return (point["x"], point["y"])
    x, y = point
    return (x, y)
