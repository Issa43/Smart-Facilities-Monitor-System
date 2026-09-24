"""
Exercises the alert decisions with fabricated detections, so the window,
incident and evidence rules are checked without a camera, the model or the
backend.

Run from this folder:  python verify_alert_logic.py

Named so the repository's Django pytest run does not collect it: this folder's
config.py would clash with the Django `config` package.
"""
import os
import sys
import unittest

# Pin the tuning so the cases below do not depend on the environment.
os.environ.update({
    "WINDOW_SIZE": "6",
    "FIRE_ALERT_FRAMES": "4",
    "SMOKE_ALERT_FRAMES": "3",
    "WINDOW_MAX_AGE_SECONDS": "10",
    "ALERT_REMINDER_SECONDS": "300",
    "INCIDENT_CLEAR_SECONDS": "10",
})
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np  # noqa: E402

from alert_manager import AlertManager  # noqa: E402
from headless import build_snapshot, collect_evidence  # noqa: E402

STEP = 0.3  # seconds between inference checks, ~5 frames of an 18 fps stream


def feed(manager, pattern, start=0.0, cls="Fire"):
    """Feed a string of 1/0 checks for one class; return (alerts, next time)."""
    alerts = []
    now = start
    for mark in pattern:
        alerts += manager.update({cls} if mark == "1" else set(), now=now)
        now += STEP
    return alerts, now


class WindowTests(unittest.TestCase):
    def test_fire_needs_four_of_six(self):
        alerts, _ = feed(AlertManager(), "111000")
        self.assertEqual(alerts, [])
        alerts, _ = feed(AlertManager(), "110110")
        self.assertEqual([a["type"] for a in alerts], ["Fire"])

    def test_smoke_needs_three_of_six(self):
        alerts, _ = feed(AlertManager(), "101010", cls="Smoke")
        self.assertEqual([a["type"] for a in alerts], ["Smoke"])

    def test_no_alert_before_window_is_full(self):
        alerts, _ = feed(AlertManager(), "11111")
        self.assertEqual(alerts, [])

    def test_checks_across_an_outage_do_not_combine(self):
        manager = AlertManager()
        _, now = feed(manager, "111")
        # 20 s outage, then one more positive: 4 of 6 by count, but the first
        # three checks are too old to belong to the same window.
        alerts, _ = feed(manager, "011", start=now + 20)
        self.assertEqual(alerts, [])


class IncidentTests(unittest.TestCase):
    def test_ongoing_fire_alerts_once_then_reminds(self):
        manager = AlertManager()
        alerts, now = feed(manager, "1" * 6)
        self.assertEqual(len(alerts), 1)
        self.assertFalse(alerts[0]["reminder"])

        # A minute more of fire: still the same incident, so silent.
        alerts, now = feed(manager, "1" * 200, start=now)
        self.assertEqual(alerts, [])

        # Past the 300 s mark the fire is re-reported as a reminder.
        alerts, _ = feed(manager, "1" * 1000, start=now)
        self.assertTrue(alerts)
        self.assertTrue(all(a["reminder"] for a in alerts))
        self.assertEqual(len(alerts), 1)

    def test_brief_gap_keeps_the_incident_open(self):
        manager = AlertManager()
        _, now = feed(manager, "1" * 6)
        # 3 s without fire is under INCIDENT_CLEAR_SECONDS: same incident.
        alerts, _ = feed(manager, "0" * 10 + "1" * 6, start=now)
        self.assertEqual(alerts, [])

    def test_fire_returning_after_it_cleared_is_a_new_incident(self):
        manager = AlertManager()
        _, now = feed(manager, "1" * 6)
        # 12 s without fire closes the incident.
        alerts, _ = feed(manager, "0" * 40 + "1" * 6, start=now)
        self.assertEqual(len(alerts), 1)
        self.assertFalse(alerts[0]["reminder"])

    def test_classes_have_separate_incidents(self):
        manager = AlertManager()
        _, now = feed(manager, "1" * 6)
        alerts, _ = feed(manager, "1" * 6, start=now, cls="Smoke")
        self.assertEqual([a["type"] for a in alerts], ["Smoke"])


def detection(cls, confidence, box):
    return {"class_name": cls, "confidence": confidence, "box": box}


class EvidenceTests(unittest.TestCase):
    def frame(self):
        return np.zeros((100, 100, 3), dtype=np.uint8)

    def run_checks(self, manager, checks, start=0.0):
        alerts, now = [], start
        for detections in checks:
            evidence = collect_evidence(detections, self.frame(), now)
            alerts += manager.update(set(evidence), now=now, evidence=evidence)
            now += STEP
        return alerts, now

    def test_evidence_comes_only_from_the_confirming_window(self):
        manager = AlertManager()
        # A lamp scores 0.95 once, long before the real fire.
        _, now = self.run_checks(manager, [[detection("Fire", 0.95, (0, 0, 5, 5))]])
        fire = [[detection("Fire", 0.6, (50, 50, 60, 60))]] * 6
        alerts, _ = self.run_checks(manager, fire, start=now + 60)

        best = build_snapshot(alerts[0]["evidence"])
        self.assertEqual(best["box"]["confidence"], 0.6)
        self.assertEqual(best["first_seen"], now + 60)

    def test_snapshot_shows_every_box_of_the_class(self):
        manager = AlertManager()
        lamp = detection("Fire", 0.9, (5, 5, 20, 20))
        fire = detection("Fire", 0.7, (60, 60, 90, 90))
        alerts, _ = self.run_checks(manager, [[lamp, fire]] * 6)

        best = build_snapshot(alerts[0]["evidence"])
        self.assertEqual(best["box"], lamp)
        # Both boxes are drawn: pixels on each rectangle's edge are coloured.
        self.assertTrue(best["snapshot"][5, 10].any())
        self.assertTrue(best["snapshot"][60, 75].any())


if __name__ == "__main__":
    unittest.main(verbosity=2)
