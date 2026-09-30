"""Checks the intrusion rules without a camera or a model.

    python verify_intrusion_logic.py

TrackState: time inside before an alarm, re-arming only after a real exit,
forgetting tracks that left. restricted_now: the ROI schedules as the backend
defines them (0=Monday, overnight windows belong to their start day).
"""

import unittest
from datetime import datetime, timezone

from intrusion_core import TrackState, restricted_now


class TrackStateTest(unittest.TestCase):
    def setUp(self):
        self.alerts = []
        self.state = TrackState(
            dwell_seconds=1.0,
            stale_seconds=10.0,
            rearm_seconds=2.0,
            on_alert=lambda *args: self.alerts.append(args[2]),
        )

    def feed(self, track_id, inside, *times):
        for now in times:
            self.state.update(track_id, inside, (0, 0), now)

    def test_alarm_after_the_dwell_time_not_a_frame_count(self):
        # Two frames 1 s apart are enough; ten frames within 0.5 s are not.
        self.feed(1, True, 0.0, 1.0)
        self.feed(2, True, *[i * 0.05 for i in range(10)])
        self.assertEqual(self.alerts, [1])

    def test_one_alarm_while_the_person_stays_inside(self):
        self.feed(1, True, *[i * 0.5 for i in range(20)])
        self.assertEqual(self.alerts, [1])

    def test_edge_flicker_does_not_raise_a_new_alarm(self):
        self.feed(1, True, 0.0, 1.0)
        for step in range(10):
            base = 2.0 + step
            self.feed(1, False, base)
            self.feed(1, True, base + 0.5)
        self.assertEqual(self.alerts, [1])

    def test_new_alarm_after_a_real_exit(self):
        self.feed(1, True, 0.0, 1.0)
        self.feed(1, False, 2.0, 4.5)
        self.feed(1, True, 5.0, 6.0)
        self.assertEqual(self.alerts, [1, 1])

    def test_short_step_out_keeps_the_dwell_running(self):
        self.feed(1, True, 0.0)
        self.feed(1, False, 0.4)
        self.feed(1, True, 1.0)
        self.assertEqual(self.alerts, [1])

    def test_passing_outside_never_alarms(self):
        self.feed(1, False, *[i * 0.5 for i in range(20)])
        self.assertEqual(self.alerts, [])

    def test_track_forgotten_after_the_stale_time(self):
        self.feed(1, True, 0.0, 1.0)
        self.state.prune_stale(12.0)
        self.assertNotIn(1, self.state.last_seen)
        self.feed(1, True, 12.0, 13.0)
        self.assertEqual(self.alerts, [1, 1])


def at(text):
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


class RestrictedNowTest(unittest.TestCase):
    def schedule(self, start, end, days, zone="UTC"):
        return {
            "always_restricted": False,
            "from_time": start,
            "to_time": end,
            "days_of_week": days,
            "timezone_name": zone,
        }

    def test_no_schedule_means_always_restricted(self):
        self.assertTrue(restricted_now(None, at("2026-09-24T12:00:00")))
        self.assertTrue(restricted_now({"always_restricted": True}, at("2026-09-24T12:00:00")))

    def test_daytime_window_on_listed_days(self):
        office = self.schedule("09:00:00", "17:00:00", [0, 1, 2, 3, 4])
        self.assertTrue(restricted_now(office, at("2026-09-24T10:00:00")))  # Thursday
        self.assertFalse(restricted_now(office, at("2026-09-24T17:00:00")))  # end is exclusive
        self.assertFalse(restricted_now(office, at("2026-09-26T10:00:00")))  # Saturday

    def test_overnight_window_belongs_to_its_start_day(self):
        night = self.schedule("22:00:00", "06:00:00", [4])  # Friday night
        self.assertTrue(restricted_now(night, at("2026-09-25T23:00:00")))  # Friday 23:00
        self.assertTrue(restricted_now(night, at("2026-09-26T05:00:00")))  # Saturday 05:00
        self.assertFalse(restricted_now(night, at("2026-09-26T23:00:00")))  # Saturday night
        self.assertFalse(restricted_now(night, at("2026-09-25T05:00:00")))  # Friday morning

    def test_hours_are_in_the_schedule_timezone(self):
        office = self.schedule("09:00:00", "17:00:00", [3], zone="Asia/Damascus")  # UTC+3
        self.assertTrue(restricted_now(office, at("2026-09-24T06:30:00")))  # 09:30 local
        self.assertFalse(restricted_now(office, at("2026-09-24T14:30:00")))  # 17:30 local


if __name__ == "__main__":
    unittest.main(verbosity=2)
