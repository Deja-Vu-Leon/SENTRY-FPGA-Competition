from collections import namedtuple
import unittest

from vehicle_risk import CAUTION, HIGH, NORMAL, UNKNOWN, VehicleMonitor, filter_vehicle_duplicates


Detection = namedtuple("Detection", "box label score", defaults=("car", .9))


def car(distance, center=240):
    half = round(.9 * 480 * 1.8 / distance / 2)
    return Detection((center-half, 70, center+half, 170))


class VehicleRiskTests(unittest.TestCase):
    def setUp(self):
        self.monitor = VehicleMonitor(.9, 10)

    def at(self, time, distance, *, center=240, measured=True, ego_kmh=None):
        return self.monitor.update([car(distance, center)], 480, time, measured=measured, ego_kmh=ego_kmh)[0]

    def test_red_needs_two_close_measurements_and_clears_after_recovery(self):
        self.assertEqual(self.at(0, 15).level, UNKNOWN)
        self.assertEqual(self.at(.10, 15).level, NORMAL)
        self.assertEqual(self.at(.20, 9).level, NORMAL)
        self.assertEqual(self.at(.25, 9, measured=False).level, NORMAL)
        self.assertEqual(self.at(.30, 9).level, HIGH)
        self.assertEqual(self.at(.40, 15).level, HIGH)
        self.assertEqual(self.at(.50, 15).level, HIGH)
        self.assertEqual(self.at(.60, 15).level, HIGH)
        self.assertEqual(self.at(.70, 15).level, NORMAL)

    def test_fast_closing_requires_measured_trend_and_travel_corridor(self):
        for index, distance in enumerate((28, 24, 20, 16)):
            target = self.at(index*.18, distance)
        self.assertEqual((target.level, target.reason), (HIGH, "快速接近"))
        self.assertLess(target.ttc_s, 2.2)
        self.assertGreater(target.closing_kmh, 60.)
        self.monitor.reset()
        for index, distance in enumerate((28, 24, 20, 16)):
            side_target = self.at(index*.18, distance, center=120)
        self.assertEqual(side_target.level, NORMAL)

    def test_same_gap_warns_when_closing_but_not_when_opening(self):
        for index, distance in enumerate((29, 27.5, 26, 24)):
            closing = self.at(index*.18, distance, ego_kmh=72)
        self.assertEqual(closing.level, CAUTION)
        self.assertGreater(closing.ttc_s, 2.2)
        self.assertLess(closing.ttc_s, 4.0)
        self.assertAlmostEqual(closing.speed_kmh + closing.closing_kmh, 72)
        predicted = self.at(.60, 21, measured=False, ego_kmh=72)
        self.assertEqual(predicted.closing_kmh, closing.closing_kmh)
        self.monitor.reset()
        for index, distance in enumerate((16, 18, 20, 22)):
            opening = self.at(index*.18, distance)
        self.assertEqual(opening.level, NORMAL)
        self.assertLess(opening.closing_kmh, 0)
        self.assertIsNone(opening.ttc_s)
        self.assertIsNone(opening.speed_kmh)

    def test_manual_speed_estimates_same_direction_and_warns_short_front_headway(self):
        for index in range(4):
            target = self.at(index*.18, 17, ego_kmh=60)
        self.assertEqual((target.level, target.reason), (CAUTION, "跟车时距短"))
        self.assertEqual(target.speed_kmh, 60)
        self.monitor = VehicleMonitor(.9, 10, rear_view=True)
        for index, distance in enumerate((29, 27.5, 26, 24)):
            rear = self.at(index*.18, distance, ego_kmh=60)
        self.assertAlmostEqual(rear.speed_kmh - rear.closing_kmh, 60)

    def test_speed_waits_for_distinct_measurements_and_rejects_width_jitter(self):
        for _ in range(5):
            pending = self.at(0, 24)
        self.assertIsNone(pending.closing_kmh)
        for index, distance in enumerate((16, 22, 17, 24, 17), start=1):
            jittering = self.at(index*.15, distance)
        self.assertIsNone(jittering.closing_kmh)
        self.assertIsNone(jittering.ttc_s)

    def test_missing_or_clipped_box_never_inherits_a_confirmed_distance(self):
        self.at(0, 9)
        self.assertEqual(self.at(.1, 9).level, HIGH)
        self.assertEqual(self.monitor.update([], 480, .2, measured=True), {})
        self.assertEqual(self.at(.3, 9).level, UNKNOWN)
        clipped = Detection((0, 70, 80, 170))
        self.assertIsNone(self.monitor.update([clipped], 480, .4, measured=True)[0].distance_m)

    def test_duplicate_vehicle_labels_preserve_person_and_distinct_car(self):
        original = car(12)
        duplicate = original._replace(label="truck", score=.5)
        person = original._replace(label="person", score=.6)
        separate = car(12, 80)
        self.assertCountEqual(filter_vehicle_duplicates([duplicate, person, original, separate]),
                              [person, original, separate])


if __name__ == "__main__":
    unittest.main()
