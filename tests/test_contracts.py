import unittest
from dataclasses import FrozenInstanceError

import numpy as np

from contracts import Detection, Frame, TargetMatch, TrackSnapshot


class FrameTests(unittest.TestCase):
    def test_first_frame_can_have_an_unknown_source_timestamp(self) -> None:
        image = np.zeros((2, 3, 3), dtype=np.uint8)
        frame = Frame(image=image, frame_index=0)

        self.assertEqual(frame.frame_index, 0)
        self.assertIsNone(frame.source_timestamp_s)
        self.assertIs(frame.image, image)

    def test_known_source_timestamps_include_zero(self) -> None:
        image = np.zeros((2, 3, 3), dtype=np.uint8)
        for timestamp in (0.0, 1.25):
            with self.subTest(timestamp=timestamp):
                frame = Frame(image=image, frame_index=0, source_timestamp_s=timestamp)
                self.assertEqual(frame.source_timestamp_s, timestamp)

    def test_invalid_source_position_is_rejected(self) -> None:
        image = np.zeros((2, 3, 3), dtype=np.uint8)
        with self.assertRaises(ValueError):
            Frame(image=image, frame_index=-1)

        for timestamp in (-0.1, float("inf"), float("nan")):
            with self.subTest(timestamp=timestamp), self.assertRaises(ValueError):
                Frame(image=image, frame_index=0, source_timestamp_s=timestamp)

    def test_frame_metadata_is_frozen_and_the_image_is_borrowed(self) -> None:
        image = np.zeros((2, 3, 3), dtype=np.uint8)
        frame = Frame(image=image, frame_index=0)

        with self.assertRaises(FrozenInstanceError):
            frame.frame_index = 1

        image[0, 0, 0] = 255
        self.assertEqual(frame.image[0, 0, 0], 255)


class TrackingContractTests(unittest.TestCase):
    def test_detection_uses_xywh_and_xy_tuples(self) -> None:
        detection = Detection(bbox=(3, 5, 8, 12), centroid=(7, 11))

        self.assertEqual(detection.bbox, (3, 5, 8, 12))
        self.assertEqual(detection.centroid, (7, 11))

    def test_unobserved_snapshot_retains_immutable_geometry_and_history(self) -> None:
        observed_points = [(4, 8), (7, 11)]
        snapshot = TrackSnapshot(
            track_id=2,
            bbox=(3, 5, 8, 12),
            centroid=(7, 11),
            trajectory=tuple(observed_points),
            missed_frames=1,
            observed_this_frame=False,
        )

        observed_points.append((9, 13))
        self.assertEqual(snapshot.bbox, (3, 5, 8, 12))
        self.assertEqual(snapshot.centroid, (7, 11))
        self.assertEqual(snapshot.trajectory, ((4, 8), (7, 11)))
        self.assertEqual(snapshot.missed_frames, 1)
        self.assertFalse(snapshot.observed_this_frame)
        with self.assertRaises(FrozenInstanceError):
            snapshot.observed_this_frame = True


class TargetMatchTests(unittest.TestCase):
    def test_zero_reference_features_make_rate_undefined(self) -> None:
        for frame_keypoints in (0, 20):
            with self.subTest(frame_keypoints=frame_keypoints):
                result = TargetMatch(False, 0, frame_keypoints, 0)
                self.assertFalse(result.detected)
                self.assertEqual(result.good_matches, 0)
                self.assertIsNone(result.match_rate)

    def test_no_frame_features_with_reference_has_zero_rate(self) -> None:
        result = TargetMatch(False, 20, 0, 0)

        self.assertFalse(result.detected)
        self.assertEqual(result.match_rate, 0.0)

    def test_rate_divides_by_reference_count_independently_of_detection(self) -> None:
        for detected in (False, True):
            with self.subTest(detected=detected):
                result = TargetMatch(detected, 20, 10, 5)
                self.assertIs(result.detected, detected)
                self.assertEqual(result.match_rate, 0.25)

    def test_negative_or_excessive_counts_are_rejected(self) -> None:
        for counts in ((-1, 3, 0), (3, -1, 0), (3, 3, -1), (3, 2, 3), (2, 3, 3)):
            with self.subTest(counts=counts), self.assertRaises(ValueError):
                TargetMatch(False, *counts)

    def test_detected_target_requires_a_good_match(self) -> None:
        with self.assertRaises(ValueError):
            TargetMatch(True, 3, 3, 0)


if __name__ == "__main__":
    unittest.main()
