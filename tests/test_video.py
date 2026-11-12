import unittest
from pathlib import Path
from struct import pack
from tempfile import TemporaryDirectory
from unittest.mock import patch

import cv2
import numpy as np

from video import KeyAction, PlaybackControls, ProcessingFPS, VideoError, VideoSource, save_snapshot


class VideoSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.capture = self.enterContext(patch("video.cv2.VideoCapture")).return_value
        self.capture.open.return_value = True
        self.image = np.zeros((3, 4, 3), dtype=np.uint8)

    def set_metadata(self, fps: float, frame_count: float) -> None:
        values = {cv2.CAP_PROP_FPS: fps, cv2.CAP_PROP_FRAME_COUNT: frame_count}
        self.capture.get.side_effect = values.__getitem__

    def avi_header_file(self, frame_count: int, *, indexed: bool = True) -> Path:
        directory = Path(self.enterContext(TemporaryDirectory()))
        path = directory / "sample.avi"
        flags = 0x10 if indexed else 0
        main_header = pack("<14I", 0, 0, 0, flags, frame_count, 0, 1, 0, 4, 3, 0, 0, 0, 0)
        header_list = b"hdrlavih" + pack("<I", len(main_header)) + main_header
        body = b"AVI LIST" + pack("<I", len(header_list)) + header_list
        path.write_bytes(b"RIFF" + pack("<I", len(body)) + body)
        return path

    def test_reads_all_file_frames_with_source_timestamps_and_stable_eof(self) -> None:
        self.set_metadata(fps=20.0, frame_count=2.0)
        second_image = self.image.copy()
        second_image[0, 0, 0] = 127
        self.capture.read.side_effect = [(True, self.image), (True, second_image), (False, None)]

        path = Path("sample.avi")
        with VideoSource(path) as source:
            first = source.read()
            second = source.read()
            self.assertEqual(source.source_fps, 20.0)
            self.assertEqual((first.frame_index, first.source_timestamp_s), (0, 0.0))
            self.assertEqual((second.frame_index, second.source_timestamp_s), (1, 0.05))
            self.assertIs(first.image, self.image)
            self.assertIs(second.image, second_image)
            self.assertIsNone(source.read())
            self.assertIsNone(source.read())

        self.capture.open.assert_called_once_with(str(path))
        self.assertEqual(self.capture.read.call_count, 3)
        self.capture.release.assert_called_once_with()

    def test_does_not_stop_at_the_reported_count_if_more_frames_can_be_read(self) -> None:
        path = self.avi_header_file(frame_count=1)
        self.set_metadata(fps=20.0, frame_count=1.0)
        self.capture.read.side_effect = [(True, self.image), (True, self.image), (False, None)]

        with VideoSource(path) as source:
            self.assertEqual(source.read().frame_index, 0)
            self.assertEqual(source.read().frame_index, 1)
            self.assertIsNone(source.read())

    def test_invalid_file_fps_does_not_create_a_source_timestamp(self) -> None:
        self.capture.read.return_value = (True, self.image)
        for fps in (0.0, -1.0, float("nan"), float("inf")):
            with self.subTest(fps=fps):
                self.set_metadata(fps=fps, frame_count=1.0)
                with VideoSource("sample.avi") as source:
                    self.assertIsNone(source.source_fps)
                    self.assertIsNone(source.read().source_timestamp_s)

    def test_unknown_length_can_end_after_a_readable_frame(self) -> None:
        self.set_metadata(fps=20.0, frame_count=0.0)
        self.capture.read.side_effect = [(True, self.image), (False, None)]

        with VideoSource("sample.avi") as source:
            self.assertEqual(source.read().frame_index, 0)
            self.assertIsNone(source.read())

    def test_mpeg_estimated_count_does_not_turn_normal_eof_into_an_error(self) -> None:
        self.set_metadata(fps=25.0, frame_count=1272.0)
        self.capture.read.side_effect = [(True, self.image), (False, None)]

        with VideoSource("sample.mpg") as source:
            self.assertEqual(source.read().frame_index, 0)
            self.assertIsNone(source.read())

    def test_unindexed_or_conflicting_avi_count_does_not_raise_early_eof(self) -> None:
        for indexed, frame_count in ((False, 3.0), (True, 4.0)):
            with self.subTest(indexed=indexed, frame_count=frame_count):
                path = self.avi_header_file(frame_count=3, indexed=indexed)
                self.set_metadata(fps=20.0, frame_count=frame_count)
                self.capture.read.side_effect = [(True, self.image), (False, None)]

                with VideoSource(path) as source:
                    self.assertEqual(source.read().frame_index, 0)
                    self.assertIsNone(source.read())

    def test_indexed_avi_that_ends_before_confirmed_count_fails_and_releases(self) -> None:
        path = self.avi_header_file(frame_count=3)
        self.set_metadata(fps=20.0, frame_count=3.0)
        self.capture.read.side_effect = [(True, self.image), (False, None)]

        with self.assertRaisesRegex(VideoError, "at frame 1.*reports 3"):
            with VideoSource(path) as source:
                source.read()
                source.read()

        self.capture.release.assert_called_once_with()

    def test_no_readable_frames_is_an_input_error(self) -> None:
        self.set_metadata(fps=0.0, frame_count=0.0)
        self.capture.read.return_value = (False, None)

        with self.assertRaisesRegex(VideoError, "no readable frames"):
            with VideoSource("empty.avi") as source:
                source.read()

        self.capture.release.assert_called_once_with()

    def test_camera_elapsed_time_uses_monotonic_clock_and_read_failure_is_error(self) -> None:
        self.set_metadata(fps=60.0, frame_count=1000.0)
        self.capture.read.side_effect = [(True, self.image), (True, self.image), (False, None)]

        with patch("video.monotonic", side_effect=(100.0, 100.5, 101.75)):
            with self.assertRaisesRegex(VideoError, "Camera 2 failed to read frame 2"):
                with VideoSource(2) as source:
                    self.assertEqual(source.source_fps, 60.0)
                    self.assertEqual(source.read().source_timestamp_s, 0.5)
                    second = source.read()
                    self.assertEqual((second.frame_index, second.source_timestamp_s), (1, 1.75))
                    source.read()

        self.capture.open.assert_called_once_with(2)
        self.capture.get.assert_called_once_with(cv2.CAP_PROP_FPS)
        self.capture.release.assert_called_once_with()

    def test_failed_file_and_camera_opens_release_capture(self) -> None:
        self.capture.open.return_value = False
        for source in ("missing.avi", 99):
            with self.subTest(source=source), self.assertRaisesRegex(VideoError, "Could not open"):
                VideoSource(source)

        self.assertEqual(self.capture.release.call_count, 2)
        self.capture.read.assert_not_called()

    def test_opencv_read_exception_is_reported_with_frame_context(self) -> None:
        self.set_metadata(fps=20.0, frame_count=1.0)
        self.capture.read.side_effect = cv2.error("decoder error")

        with self.assertRaisesRegex(VideoError, "Read failed at frame 0"):
            with VideoSource("sample.avi") as source:
                source.read()

        self.capture.release.assert_called_once_with()

    def test_invalid_bgr_image_is_rejected(self) -> None:
        self.set_metadata(fps=20.0, frame_count=1.0)
        self.capture.read.return_value = (True, self.image[:, :, 0])

        with self.assertRaisesRegex(VideoError, "Invalid BGR image"):
            with VideoSource("sample.avi") as source:
                source.read()

    def test_close_is_idempotent_and_closed_source_cannot_read(self) -> None:
        self.set_metadata(fps=20.0, frame_count=1.0)
        source = VideoSource("sample.avi")
        source.close()
        source.close()

        self.capture.release.assert_called_once_with()
        with self.assertRaisesRegex(VideoError, "is closed"):
            source.read()
        self.capture.read.assert_not_called()


class PlaybackTests(unittest.TestCase):
    def test_keys_pause_resume_save_and_quit(self) -> None:
        controls = PlaybackControls()
        self.assertFalse(controls.paused)
        self.assertIs(controls.handle_key(-1), KeyAction.NONE)
        self.assertIs(controls.handle_key(ord("x")), KeyAction.NONE)
        self.assertIs(controls.handle_key(ord("p")), KeyAction.PAUSE)
        self.assertTrue(controls.paused)
        self.assertIs(controls.handle_key(ord("s")), KeyAction.SAVE)
        self.assertIs(controls.handle_key(ord("q")), KeyAction.QUIT)
        self.assertTrue(controls.paused)
        self.assertIs(controls.handle_key(ord("p")), KeyAction.RESUME)
        self.assertFalse(controls.paused)

    def test_processing_fps_uses_active_durations_and_can_reset(self) -> None:
        meter = ProcessingFPS()
        self.assertIsNone(meter.fps)
        self.assertIsNone(meter.record_frame(0.0))
        self.assertAlmostEqual(meter.record_frame(0.02), 50.0)
        self.assertAlmostEqual(meter.record_frame(0.03), 40.0)
        self.assertAlmostEqual(meter.record_frame(float("nan")), 40.0)
        meter.reset()
        self.assertIsNone(meter.fps)
        self.assertAlmostEqual(meter.record_frame(0.04), 25.0)

    def test_processing_fps_only_uses_recent_frames(self) -> None:
        meter = ProcessingFPS()
        meter.record_frame(1.0)
        for _ in range(30):
            meter.record_frame(0.02)

        self.assertAlmostEqual(meter.fps, 50.0)


class SnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        # Use the writable checkout, where Windows can replace a completed file.
        checkout = Path(__file__).resolve().parents[1]
        self.directory = Path(self.enterContext(TemporaryDirectory(dir=checkout)))

    def test_png_preserves_rendered_pixels_at_a_unicode_path(self) -> None:
        image = np.arange(36, dtype=np.uint8).reshape(3, 4, 3)
        path = self.directory / "저장 결과" / "프레임.png"

        self.assertEqual(save_snapshot(image, path), path)
        data = np.frombuffer(path.read_bytes(), dtype=np.uint8)
        saved = cv2.imdecode(data, cv2.IMREAD_COLOR)

        self.assertEqual(list(path.parent.iterdir()), [path])
        np.testing.assert_array_equal(saved, image)

    def test_snapshot_write_failure_preserves_existing_directory(self) -> None:
        image = np.zeros((3, 4, 3), dtype=np.uint8)
        path = self.directory / "existing.png"
        path.mkdir()

        with self.assertRaisesRegex(VideoError, "Could not save snapshot"):
            save_snapshot(image, path)

        self.assertTrue(path.is_dir())
        self.assertEqual(list(path.parent.iterdir()), [path])


if __name__ == "__main__":
    unittest.main()
