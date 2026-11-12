import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np

from contracts import Detection
from motion_detector import MotionDetector


class MotionDetectorTests(unittest.TestCase):
    def test_background_model_filters_by_area_and_sorts_detections(self) -> None:
        detector = MotionDetector(min_area=36, kernel_size=1, learning_rate=0.0)
        background = np.zeros((64, 80, 3), dtype=np.uint8)
        detector.detect(background)
        self.assertEqual(detector.detect(background), [])

        image = background.copy()
        image[25:34, 7:16] = 255
        image[8:15, 30:37] = 255
        image[44:47, 63:66] = 255
        original = image.copy()

        self.assertEqual(
            detector.detect(image),
            [
                Detection((7, 25, 9, 9), (11, 29)),
                Detection((30, 8, 7, 7), (33, 11)),
            ],
        )
        np.testing.assert_array_equal(image, original)

    def test_shadows_are_removed_before_morphology(self) -> None:
        raw = np.zeros((35, 40), dtype=np.uint8)
        raw[4:15, 3:14] = 255
        raw[9, 8] = 0
        raw[22, 16] = 255
        raw[4:15, 23:34] = 127
        model = Mock()
        model.apply.return_value = raw

        with patch.object(cv2, "createBackgroundSubtractorMOG2", return_value=model) as create:
            detector = MotionDetector(min_area=0, kernel_size=3, shadow_threshold=0.7)

        detections = detector.detect(np.zeros((35, 40, 3), dtype=np.uint8))

        create.assert_called_once_with(detectShadows=True)
        model.setShadowThreshold.assert_called_once_with(0.7)
        self.assertEqual(detections, [Detection((3, 4, 11, 11), (8, 9))])
        np.testing.assert_array_equal(detector.last_raw_mask, raw)
        self.assertEqual(detector.last_clean_mask[9, 8], 255)
        self.assertEqual(detector.last_clean_mask[22, 16], 0)
        self.assertEqual(detector.last_clean_mask[9, 28], 0)

    def test_morphology_opens_before_closing(self) -> None:
        raw = np.zeros((25, 25), dtype=np.uint8)
        raw[5:20, 5:7] = 255
        raw[5:20, 8:10] = 255
        model = Mock()
        model.apply.return_value = raw

        with patch.object(cv2, "createBackgroundSubtractorMOG2", return_value=model):
            detector = MotionDetector(min_area=0, kernel_size=3)

        self.assertEqual(detector.detect(np.zeros((25, 25, 3), dtype=np.uint8)), [])
        self.assertFalse(np.any(detector.last_clean_mask))

    def test_learning_rate_is_applied_at_each_call(self) -> None:
        image = np.zeros((12, 12, 3), dtype=np.uint8)
        for rate in (-1.0, 0.0, 0.25, 1.0):
            with self.subTest(rate=rate):
                model = Mock()
                model.apply.return_value = np.zeros((12, 12), dtype=np.uint8)
                with patch.object(cv2, "createBackgroundSubtractorMOG2", return_value=model):
                    detector = MotionDetector(learning_rate=rate)

                first = detector.detect(image)
                second = detector.detect(image)

                self.assertEqual(first, [])
                self.assertEqual(second, [])
                self.assertIsNot(first, second)
                self.assertEqual(model.apply.call_count, 2)
                for call in model.apply.call_args_list:
                    self.assertIs(call.args[0], image)
                    self.assertEqual(call.kwargs, {"learningRate": rate})

    def test_reset_clears_masks_and_restarts_background_learning(self) -> None:
        image = np.zeros((20, 20, 3), dtype=np.uint8)
        detector = MotionDetector(min_area=36, kernel_size=3, learning_rate=0.5)

        self.assertIsNone(detector.last_raw_mask)
        self.assertIsNone(detector.last_clean_mask)
        self.assertTrue(detector.detect(image))
        self.assertEqual(detector.detect(image), [])
        detector.reset()

        self.assertIsNone(detector.last_raw_mask)
        self.assertIsNone(detector.last_clean_mask)
        self.assertTrue(detector.detect(image))
        self.assertEqual(detector.detect(image), [])

    def test_diagnostics_are_copies(self) -> None:
        detector = MotionDetector(min_area=0, kernel_size=1)
        detector.detect(np.zeros((12, 12, 3), dtype=np.uint8))

        raw = detector.last_raw_mask
        clean = detector.last_clean_mask
        raw[:] = 99
        clean[:] = 99

        self.assertFalse(np.any(detector.last_raw_mask == 99))
        self.assertFalse(np.any(detector.last_clean_mask == 99))

    def test_zero_area_contour_uses_bounding_box_center(self) -> None:
        raw = np.zeros((10, 10), dtype=np.uint8)
        raw[4, 2:5] = 255
        model = Mock()
        model.apply.return_value = raw
        with patch.object(cv2, "createBackgroundSubtractorMOG2", return_value=model):
            detector = MotionDetector(min_area=0, kernel_size=1)

        self.assertEqual(
            detector.detect(np.zeros((10, 10, 3), dtype=np.uint8)),
            [Detection((2, 4, 3, 1), (3, 4))],
        )

    def test_invalid_settings_are_rejected(self) -> None:
        invalid_settings = (
            {"min_area": -1},
            {"min_area": float("inf")},
            {"kernel_size": 0},
            {"kernel_size": 4},
            {"kernel_size": 3.0},
            {"learning_rate": -0.1},
            {"learning_rate": 1.1},
            {"learning_rate": float("nan")},
            {"shadow_threshold": -0.1},
        )
        for settings in invalid_settings:
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                MotionDetector(**settings)

    def test_invalid_frames_are_rejected_without_updating_diagnostics(self) -> None:
        detector = MotionDetector()
        invalid_frames = (
            np.zeros((0, 4, 3), dtype=np.uint8),
            np.zeros((4, 4), dtype=np.uint8),
            np.zeros((4, 4, 4), dtype=np.uint8),
            np.zeros((4, 4, 3), dtype=np.float32),
        )
        for image in invalid_frames:
            with self.subTest(shape=image.shape, dtype=image.dtype), self.assertRaises(ValueError):
                detector.detect(image)

        self.assertIsNone(detector.last_raw_mask)
        self.assertIsNone(detector.last_clean_mask)


if __name__ == "__main__":
    unittest.main()
