import unittest

from contracts import Detection
from tracker import Tracker


def at(x: int, y: int = 10) -> Detection:
    return Detection((x - 1, y - 1, 2, 2), (x, y))


class TrackerTests(unittest.TestCase):
    def test_empty_before_first_observation(self) -> None:
        self.assertEqual(Tracker().update([]), [])

    def test_motion_keeps_id_and_bounds_history(self) -> None:
        tracker = Tracker(trajectory_length=2)
        original, = tracker.update([at(1)])
        tracker.update([at(2)])
        current, = tracker.update([at(3)])
        self.assertEqual((original.track_id, current.track_id), (1, 1))
        self.assertEqual(original.trajectory, ((1, 10),))
        self.assertEqual(current.trajectory, ((2, 10), (3, 10)))

    def test_missing_track_retains_last_geometry_and_recovers(self) -> None:
        tracker = Tracker(max_missed=2)
        initial, = tracker.update([at(2)])
        missing, = tracker.update([])
        second_miss, = tracker.update([])
        self.assertEqual(missing.bbox, initial.bbox)
        self.assertEqual(second_miss.trajectory, initial.trajectory)
        self.assertEqual(second_miss.missed_frames, 2)
        self.assertFalse(second_miss.observed_this_frame)
        current, = tracker.update([at(4)])
        self.assertEqual(current.track_id, initial.track_id)
        self.assertTrue(current.observed_this_frame)
        self.assertEqual(current.missed_frames, 0)
        self.assertEqual(current.trajectory, ((2, 10), (4, 10)))

    def test_expiry_does_not_recycle_id(self) -> None:
        tracker = Tracker(max_missed=1)
        tracker.update([at(2)])
        self.assertEqual(len(tracker.update([])), 1)
        self.assertEqual(tracker.update([]), [])
        current, = tracker.update([at(2)])
        self.assertEqual(current.track_id, 2)

    def test_zero_max_missed_retires_track_on_first_miss(self) -> None:
        tracker = Tracker(max_missed=0)
        tracker.update([at(3)])
        self.assertEqual(tracker.update([]), [])

    def test_inclusive_distance_and_new_id_outside_gate(self) -> None:
        tracker = Tracker(max_distance=5)
        tracker.update([at(2, 2)])
        same, = tracker.update([at(5, 6)])
        self.assertEqual(same.track_id, 1)
        old, new = tracker.update([at(5, 12)])
        self.assertEqual((old.track_id, new.track_id), (1, 2))
        self.assertFalse(old.observed_this_frame)
        self.assertTrue(new.observed_this_frame)

    def test_greedy_matching_is_one_to_one(self) -> None:
        tracker = Tracker(max_distance=10)
        tracker.update([at(1), at(8)])
        first, second, third = tracker.update([at(2), at(3), at(25)])
        self.assertEqual(
            [(track.track_id, track.centroid) for track in (first, second, third)],
            [(1, (2, 10)), (2, (3, 10)), (3, (25, 10))],
        )

    def test_equal_distance_uses_track_id_then_detection_geometry(self) -> None:
        for measurements in ([at(5, 11), at(5, 9)], [at(5, 9), at(5, 11)]):
            with self.subTest(measurements=measurements):
                tracker = Tracker()
                tracker.update([at(10), at(0)])
                first, second = tracker.update(measurements)
                self.assertEqual(first.centroid, (5, 9))
                self.assertEqual(second.centroid, (5, 11))

    def test_invalid_settings(self) -> None:
        for settings in (
            {"max_distance": -1},
            {"max_distance": float("nan")},
            {"max_distance": float("inf")},
            {"max_missed": -1},
            {"trajectory_length": 0},
        ):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                Tracker(**settings)
