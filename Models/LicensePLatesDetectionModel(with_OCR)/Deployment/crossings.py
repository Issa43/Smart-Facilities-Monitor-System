"""Turning line crossings into vehicle events, for the ANPR service.

A vehicle often crosses the virtual line before its plate has been read: the
plate is small while the car is far away, and the first readable frames come
as it gets close. The backend needs the plate number, the vehicle type and its
box on every event, so a crossing waits on its track until all of them are
known, and is dropped if the track ends first.

Pure logic with no model or camera, so verify_anpr_logic.py can check it.
"""

from collections import Counter, deque

# COCO class -> CameraEvent.vehicle_type. Kept one-to-one: the backend has its
# own bus and motorcycle types, unlike the local runner's CAR / Truck grouping.
BACKEND_VEHICLE_TYPE = {
    "car": "car",
    "motorcycle": "motorcycle",
    "bus": "bus",
    "truck": "truck",
}

# direction.py labels the side a track crossed to; the backend says entry/exit.
BACKEND_DIRECTION = {"IN": "entry", "OUT": "exit"}


def in_direction(p1, p2):
    """Unit vector pointing to the IN side of the line p1 -> p2.

    direction.side_of_line calls the side where the cross product is positive
    IN, and the normal (-dy, dx) is the one that points there: in image
    coordinates, below a line drawn left to right. The admin page draws the
    same arrow, so the admin sees which way counts as entry.
    """
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    length = max(1e-6, (dx * dx + dy * dy) ** 0.5)
    return -dy / length, dx / length


def find_predecessor(new_box, lost):
    """The lost track a new plate track most likely continues, or None.

    ByteTrack matches boxes by overlap, and at the few frames per second a live
    service processes, a plate moves more than its own height between frames,
    so one approaching car keeps getting new track ids. A track born just past
    the line then never sees itself cross it. `lost` maps recently lost track
    ids to their last box; the nearest one within two plate widths of the new
    box is taken as the same plate.
    """
    x1, y1, x2, y2 = new_box
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    reach = 2 * max(x2 - x1, y2 - y1)
    best, best_distance = None, reach
    for track_id, (ox1, oy1, ox2, oy2) in lost.items():
        distance = ((cx - (ox1 + ox2) / 2) ** 2 + (cy - (oy1 + oy2) / 2) ** 2) ** 0.5
        if distance < best_distance:
            best, best_distance = track_id, distance
    return best


class VehicleVotes:
    """Recent vehicle-model matches for one plate track."""

    def __init__(self, size=10):
        self.matches = deque(maxlen=size)  # (coco_class, confidence, box)

    def add(self, coco_class, confidence, box):
        if coco_class in BACKEND_VEHICLE_TYPE:
            self.matches.append((coco_class, float(confidence), tuple(box)))

    def best(self):
        """(backend type, mean confidence, latest box) of the majority class, or None."""
        if not self.matches:
            return None
        winner = Counter(match[0] for match in self.matches).most_common(1)[0][0]
        chosen = [match for match in self.matches if match[0] == winner]
        confidence = sum(match[1] for match in chosen) / len(chosen)
        return BACKEND_VEHICLE_TYPE[winner], confidence, chosen[-1][2]


def plate_confidence(history, plate):
    """Mean OCR confidence of the reads that voted for `plate`."""
    scores = [conf for text, conf in history if text == plate]
    return sum(scores) / len(scores) if scores else 0.0


class PendingCrossings:
    """Crossings waiting for their plate and vehicle, one per track."""

    def __init__(self, repeat_seconds):
        self.repeat_seconds = float(repeat_seconds)
        self.pending = {}   # track_id -> crossing fields known at the crossing
        self.last_sent = {}  # (plate, direction) -> time it was last sent

    def crossed(self, track_id, label, centroid, bbox_plate, detected_at):
        """Record that a track crossed; a later crossing replaces an unsent one."""
        self.pending[track_id] = {
            "track_id": track_id,
            "direction": BACKEND_DIRECTION[label],
            "centroid": centroid,
            "bbox_plate": bbox_plate,
            "detected_at": detected_at,
        }

    def complete(self, track_id, *, plate, ocr_confidence, plate_confidence,
                 vehicle, now):
        """The finished crossing for this track once its plate and vehicle are known.

        Returns None while something is still missing, and for the same plate
        crossing the same way within `repeat_seconds`: one vehicle whose plate
        the tracker lost and found again becomes two tracks, and both cross.
        """
        crossing = self.pending.get(track_id)
        if crossing is None or not plate or vehicle is None:
            return None
        del self.pending[track_id]

        # Only recent sends matter; without this the table grows with every
        # plate a long-running gate camera ever sees.
        self.last_sent = {
            key: sent for key, sent in self.last_sent.items()
            if now - sent < self.repeat_seconds
        }
        key = (plate, crossing["direction"])
        last = self.last_sent.get(key)
        if last is not None and now - last < self.repeat_seconds:
            return None
        self.last_sent[key] = now

        vehicle_type, vehicle_confidence, vehicle_box = vehicle
        return {
            **crossing,
            "plate_number": plate,
            "ocr_confidence": ocr_confidence,
            "plate_confidence": plate_confidence,
            "vehicle_type": vehicle_type,
            "vehicle_confidence": vehicle_confidence,
            "bbox_vehicle": vehicle_box,
        }

    def hand_over(self, old_track_id, new_track_id):
        """A crossing still waiting on a track that was split moves to its successor."""
        crossing = self.pending.pop(old_track_id, None)
        if crossing is not None:
            self.pending[new_track_id] = {**crossing, "track_id": new_track_id}

    def forget(self, track_ids):
        """Drop crossings of tracks that ended; returns the ones that were never sent."""
        return [self.pending.pop(tid) for tid in track_ids if tid in self.pending]
