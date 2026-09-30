"""Checks the ANPR service rules without a camera or a model.

    python verify_anpr_logic.py

A crossing waits for its plate and vehicle, survives the tracker splitting the
plate into a new track, is sent once, is not repeated for
the same plate and direction, and is dropped with its track. The IN arrow the
service and the admin page draw points to the side direction.py counts as IN.
"""

import unittest
from datetime import datetime, timezone

from crossings import (
    PendingCrossings,
    VehicleVotes,
    find_predecessor,
    in_direction,
    plate_confidence,
)
from direction import side_of_line, update_direction
from tracking import TrackState

T0 = datetime(2026, 9, 25, 8, 0, tzinfo=timezone.utc)
CAR = ("car", 0.9, (100, 100, 500, 400))


class PendingCrossingsTest(unittest.TestCase):
    def setUp(self):
        self.pending = PendingCrossings(repeat_seconds=30)

    def complete(self, track_id, plate="65-12377", vehicle=CAR, now=0.0):
        return self.pending.complete(track_id, plate=plate, ocr_confidence=0.95,
                                     plate_confidence=0.8, vehicle=vehicle, now=now)

    def test_waits_for_the_plate_and_the_vehicle(self):
        self.pending.crossed(1, "IN", (300, 300), (250, 280, 350, 320), T0)
        self.assertIsNone(self.complete(1, plate=None))
        self.assertIsNone(self.complete(1, vehicle=None))
        event = self.complete(1)
        self.assertEqual(event["direction"], "entry")
        self.assertEqual(event["plate_number"], "65-12377")
        self.assertEqual(event["bbox_vehicle"], CAR[2])

    def test_sent_once(self):
        self.pending.crossed(1, "OUT", (300, 300), (250, 280, 350, 320), T0)
        self.assertEqual(self.complete(1)["direction"], "exit")
        self.assertIsNone(self.complete(1))

    def test_same_plate_same_way_is_not_repeated_within_the_window(self):
        for track_id, now, expected in ((1, 0.0, True), (2, 10.0, False), (3, 31.0, True)):
            self.pending.crossed(track_id, "IN", (300, 300), (250, 280, 350, 320), T0)
            self.assertEqual(self.complete(track_id, now=now) is not None, expected)

    def test_the_other_direction_is_a_new_event(self):
        self.pending.crossed(1, "IN", (300, 300), (250, 280, 350, 320), T0)
        self.pending.crossed(2, "OUT", (300, 300), (250, 280, 350, 320), T0)
        self.assertIsNotNone(self.complete(1))
        self.assertIsNotNone(self.complete(2, now=5.0))

    def test_crossing_of_an_ended_track_is_dropped(self):
        self.pending.crossed(1, "IN", (300, 300), (250, 280, 350, 320), T0)
        self.assertEqual(len(self.pending.forget([1, 2])), 1)
        self.assertIsNone(self.complete(1))


class SplitTrackTest(unittest.TestCase):
    def test_new_track_continues_the_nearest_lost_plate(self):
        lost = {7: (500, 900, 600, 940), 8: (100, 300, 200, 340)}
        self.assertEqual(find_predecessor((520, 980, 625, 1022), lost), 7)

    def test_a_plate_too_far_away_is_a_different_vehicle(self):
        self.assertIsNone(find_predecessor((900, 1500, 1000, 1540), {7: (100, 300, 200, 340)}))

    def test_waiting_crossing_moves_to_the_successor(self):
        pending = PendingCrossings(repeat_seconds=30)
        pending.crossed(7, "IN", (550, 1060), (500, 1040, 600, 1080), T0)
        pending.hand_over(7, 9)
        self.assertEqual(pending.forget([7]), [])
        event = pending.complete(9, plate="17-42414", ocr_confidence=0.99,
                                 plate_confidence=0.8, vehicle=CAR, now=0.0)
        self.assertEqual(event["track_id"], 9)


class VehicleVotesTest(unittest.TestCase):
    def test_majority_class_with_its_mean_confidence_and_latest_box(self):
        votes = VehicleVotes()
        votes.add("car", 0.8, (0, 0, 10, 10))
        votes.add("truck", 0.9, (0, 0, 20, 20))
        votes.add("car", 0.6, (0, 0, 30, 30))
        self.assertEqual(votes.best(), ("car", 0.7, (0, 0, 30, 30)))

    def test_backend_keeps_bus_and_motorcycle(self):
        for coco in ("bus", "motorcycle"):
            votes = VehicleVotes()
            votes.add(coco, 0.5, (0, 0, 1, 1))
            self.assertEqual(votes.best()[0], coco)

    def test_nothing_matched(self):
        self.assertIsNone(VehicleVotes().best())

    def test_ocr_confidence_of_the_winning_plate(self):
        history = [("65-12377", 0.9), ("65-12371", 0.86), ("65-12377", 0.96)]
        self.assertAlmostEqual(plate_confidence(history, "65-12377"), 0.93)


class DirectionTest(unittest.TestCase):
    def test_arrow_points_to_the_in_side(self):
        for p1, p2 in (((0, 500), (1000, 500)), ((1000, 500), (0, 500)),
                       ((200, 0), (800, 1000))):
            nx, ny = in_direction(p1, p2)
            mid = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
            ahead = (mid[0] + nx * 50, mid[1] + ny * 50)
            self.assertEqual(side_of_line(ahead, p1, p2), 1)

    def test_moving_down_across_a_left_to_right_line_is_in(self):
        st, line = TrackState(), ((0, 500), (1000, 500))
        crossed = [update_direction(st, (500, y), *line, frame)
                   for frame, y in enumerate((300, 400, 600, 650, 700))]
        self.assertEqual(crossed, [False, False, False, False, True])
        self.assertEqual(st.direction, "IN")


if __name__ == "__main__":
    unittest.main(verbosity=2)
