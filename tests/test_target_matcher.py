from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import cv2
import numpy as np

from target_matcher import TargetMatcher


class TargetMatcherTests(unittest.TestCase):
    def setUp(self) -> None:
        generator = np.random.default_rng(412)
        noise = generator.integers(0, 256, (180, 180), dtype=np.uint8)
        self.reference = cv2.cvtColor(noise, cv2.COLOR_GRAY2BGR)

    def test_shifted_target_is_detected(self) -> None:
        scene = np.zeros((240, 250, 3), dtype=np.uint8)
        scene[35:215, 45:225] = self.reference
        result = TargetMatcher(self.reference).match(scene)

        self.assertTrue(result.detected)
        self.assertGreaterEqual(result.good_matches, 12)
        self.assertLessEqual(result.good_matches, min(result.reference_keypoints, result.frame_keypoints))
        self.assertAlmostEqual(result.match_rate, result.good_matches / result.reference_keypoints)

    def test_unrelated_textured_scene_is_not_detected(self) -> None:
        generator = np.random.default_rng(591)
        scene = generator.integers(0, 256, (180, 180, 3), dtype=np.uint8)
        result = TargetMatcher(self.reference).match(scene)
        self.assertFalse(result.detected)
        self.assertGreater(result.frame_keypoints, 0)

    def test_blank_or_empty_frame_retains_reference_count(self) -> None:
        matcher = TargetMatcher(self.reference)
        for scene in (np.zeros_like(self.reference), np.zeros((0, 0, 3), dtype=np.uint8)):
            with self.subTest(shape=scene.shape):
                result = matcher.match(scene)
                self.assertFalse(result.detected)
                self.assertGreater(result.reference_keypoints, 0)
                self.assertEqual((result.frame_keypoints, result.good_matches, result.match_rate), (0, 0, 0.0))

    def test_blank_reference_retains_frame_count(self) -> None:
        result = TargetMatcher(np.zeros_like(self.reference)).match(self.reference)
        self.assertFalse(result.detected)
        self.assertEqual((result.reference_keypoints, result.good_matches, result.match_rate), (0, 0, None))
        self.assertGreater(result.frame_keypoints, 0)

    def test_detection_depends_on_minimum_count(self) -> None:
        result = TargetMatcher(self.reference, nfeatures=100, min_matches=101).match(self.reference)
        self.assertGreater(result.good_matches, 0)
        self.assertFalse(result.detected)

    def test_loads_unicode_reference_path(self) -> None:
        with TemporaryDirectory() as directory:
            target = Path(directory) / "참조.png"
            encoded, data = cv2.imencode(".png", self.reference)
            self.assertTrue(encoded)
            target.write_bytes(data.tobytes())
            self.assertTrue(TargetMatcher.from_file(target).match(self.reference).detected)

    def test_invalid_reference_file_has_clear_error(self) -> None:
        with TemporaryDirectory() as directory:
            target = Path(directory) / "invalid.png"
            target.write_bytes(b"broken image")
            with self.assertRaisesRegex(ValueError, "Could not decode target image"):
                TargetMatcher.from_file(target)

    def test_invalid_configuration(self) -> None:
        for settings in ({"nfeatures": 0}, {"ratio": 1}, {"ratio": float("nan")}, {"min_matches": 0}):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                TargetMatcher(self.reference, **settings)
