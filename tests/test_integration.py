from contextlib import ExitStack, redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from contracts import Frame
from main import main
from motion_detector import MotionDetector
from target_matcher import TargetMatcher
from tracker import Tracker
from video import VideoSource


class IntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.checkout = Path(__file__).resolve().parents[1]
        scratch = self.checkout / "tmp"
        scratch.mkdir(exist_ok=True)
        self.directory = Path(self.enterContext(TemporaryDirectory(dir=scratch)))
        self.video = self.directory / "source.mkv"
        self.reference = self.directory / "target.png"
        self.log = self.directory / "frames.jsonl"
        self.summary = self.directory / "summary.json"

        height, width, self.source_fps = 240, 320, 20.0
        reference = np.random.default_rng(724).integers(0, 256, (140, 140), dtype=np.uint8)
        reference = cv2.cvtColor(reference, cv2.COLOR_GRAY2BGR)
        self.assertTrue(cv2.imwrite(str(self.reference), reference))
        blank = np.zeros((height, width, 3), dtype=np.uint8)
        scene_one = blank.copy()
        scene_one[22:162, 4:144] = reference
        scene_two = blank.copy()
        scene_two[22:162, 14:154] = reference
        writer = cv2.VideoWriter(
            str(self.video), cv2.CAP_FFMPEG, cv2.VideoWriter_fourcc(*"FFV1"),
            self.source_fps, (width, height),
        )
        try:
            self.assertTrue(writer.isOpened(), "OpenCV FFV1 writer is unavailable")
            for image in (blank, scene_one, scene_two, blank):
                writer.write(image)
        finally:
            writer.release()

    def options(self) -> list[str]:
        return [
            "--video", str(self.video), "--target", str(self.reference),
            "--frame-log", str(self.log), "--summary-json", str(self.summary),
            "--learning-rate", "0", "--min-area", "100",
        ]

    def rows(self) -> list[dict]:
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]

    def test_headless_cli_preserves_all_source_frames_and_writes_ffv1(self) -> None:
        annotated = self.directory / "annotated.mkv"
        process = subprocess.run(
            [sys.executable, "-B", "main.py", *self.options(), "--headless", "--annotated-video", str(annotated)],
            cwd=self.checkout, capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        rows = self.rows()
        self.assertEqual([row["frame_index"] for row in rows], [0, 1, 2, 3])
        self.assertEqual([row["source_timestamp_s"] for row in rows], [0.0, 0.05, 0.1, 0.15])
        self.assertEqual([row["target"]["detected"] for row in rows], [False, True, True, False])
        self.assertGreater(rows[1]["foreground_fraction"], 0.0)
        self.assertEqual(rows[-1]["detections"], [])
        self.assertEqual(rows[-1]["foreground_fraction"], 0.0)
        seen_one = [track for track in rows[1]["tracks"] if track["observed_this_frame"]]
        seen_two = [track for track in rows[2]["tracks"] if track["observed_this_frame"]]
        self.assertEqual(len(seen_one), 1)
        self.assertEqual(len(seen_two), 1)
        self.assertEqual(seen_one[0]["track_id"], seen_two[0]["track_id"])
        self.assertEqual(len(seen_two[0]["trajectory"]), 2)
        self.assertFalse(any(track["observed_this_frame"] for track in rows[-1]["tracks"]))

        with VideoSource(annotated) as output:
            self.assertEqual(output.source_fps, self.source_fps)
            for index in range(4):
                frame = output.read()
                self.assertIsNotNone(frame)
                self.assertEqual(frame.frame_index, index)
                self.assertEqual(frame.image.shape, (240, 320, 3))
                self.assertTrue(np.any(frame.image))  # FPS and frame number overlay.
            self.assertIsNone(output.read())

        summary = json.loads(self.summary.read_text(encoding="utf-8"))
        self.assertEqual((summary["status"], summary["reason"], summary["frames_processed"]), ("completed", "source_eof", 4))
        self.assertEqual((summary["source_fps"], summary["annotated_video_fps"]), (20.0, 20.0))
        self.assertEqual(summary["parameters"]["learning_rate"], 0.0)
        self.assertEqual(summary["versions"]["opencv"], cv2.__version__)

    def test_pause_does_not_read_or_update_and_saves_the_displayed_frame(self) -> None:
        snapshots = self.directory / "스냅샷"
        annotated = self.directory / "annotated.mkv"
        displayed = []
        observed_calls = []
        source_read = VideoSource.read
        detect = MotionDetector.detect
        update = Tracker.update
        match = TargetMatcher.match

        def read_next(source: VideoSource):
            observed_calls.append("read")
            return source_read(source)

        def key(_delay: int) -> int:
            observed_calls.append("key")
            return next(keys)

        keys = iter((ord("p"), ord("s"), -1, ord("p"), ord("q")))
        with ExitStack() as mocks:
            mocks.enter_context(redirect_stdout(StringIO()))
            mocks.enter_context(patch("main.cv2.namedWindow"))
            close = mocks.enter_context(patch("main.cv2.destroyWindow"))
            mocks.enter_context(patch("main.cv2.getWindowProperty", return_value=1.0))
            mocks.enter_context(patch("main.cv2.waitKey", side_effect=key))
            mocks.enter_context(patch("main.cv2.imshow", side_effect=lambda _, image: displayed.append(image.copy())))
            mocks.enter_context(patch.object(VideoSource, "read", autospec=True, side_effect=read_next))
            detector = mocks.enter_context(patch.object(MotionDetector, "detect", autospec=True, side_effect=detect))
            tracker = mocks.enter_context(patch.object(Tracker, "update", autospec=True, side_effect=update))
            matcher = mocks.enter_context(patch.object(TargetMatcher, "match", autospec=True, side_effect=match))
            exit_code = main([
                *self.options(), "--snapshot-dir", str(snapshots), "--annotated-video", str(annotated)
            ])

        self.assertEqual(exit_code, 0)
        self.assertEqual(observed_calls, ["read", "key", "key", "key", "key", "read", "key"])
        self.assertEqual((detector.call_count, tracker.call_count, matcher.call_count), (2, 2, 2))
        self.assertEqual(len(displayed), 2)
        close.assert_called_once()
        saved = snapshots / "frame-000000.png"
        decoded = cv2.imdecode(np.frombuffer(saved.read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
        np.testing.assert_array_equal(decoded, displayed[0])
        with VideoSource(annotated) as output:
            for image in displayed:
                np.testing.assert_array_equal(output.read().image, image)
            self.assertIsNone(output.read())
        self.assertEqual([row["frame_index"] for row in self.rows()], [0, 1])
        summary = json.loads(self.summary.read_text(encoding="utf-8"))
        self.assertEqual((summary["status"], summary["reason"], summary["frames_processed"]), ("stopped", "user_quit", 2))

    def test_unconfigured_target_uses_null_and_headless_never_opens_gui(self) -> None:
        with redirect_stdout(StringIO()), patch("main.cv2.namedWindow") as window:
            result = main(["--video", str(self.video), "--headless", "--frame-log", str(self.log)])
        self.assertEqual(result, 0)
        window.assert_not_called()
        self.assertEqual([row["target"] for row in self.rows()], [None] * 4)

    def test_unknown_source_fps_only_uses_fallback_for_encoded_video(self) -> None:
        annotated = self.directory / "fallback.mkv"
        frame = Frame(np.zeros((240, 320, 3), dtype=np.uint8), 0)
        with patch("main.VideoSource") as capture, redirect_stdout(StringIO()):
            source = capture.return_value.__enter__.return_value
            source.source_fps = None
            source.read.side_effect = (frame, None)
            result = main([*self.options(), "--headless", "--annotated-video", str(annotated)])

        self.assertEqual(result, 0)
        capture.return_value.__exit__.assert_called_once()
        self.assertIsNone(self.rows()[0]["source_timestamp_s"])
        summary = json.loads(self.summary.read_text(encoding="utf-8"))
        self.assertIsNone(summary["source_fps"])
        self.assertEqual(summary["annotated_video_fps"], 30.0)
        with VideoSource(annotated) as output:
            self.assertEqual(output.source_fps, 30.0)
            self.assertIsNotNone(output.read())
            self.assertIsNone(output.read())

    def test_bad_input_records_a_failed_run_and_preserves_summary(self) -> None:
        missing = self.directory / "missing.mkv"
        with redirect_stderr(StringIO()):
            result = main(["--video", str(missing), "--headless", "--summary-json", str(self.summary)])

        self.assertEqual(result, 1)
        summary = json.loads(self.summary.read_text(encoding="utf-8"))
        self.assertEqual((summary["status"], summary["reason"], summary["frames_processed"]), ("failed", "runtime_error", 0))
        self.assertIn("Could not open video source", summary["error"])

    def test_output_cannot_overwrite_input(self) -> None:
        original = self.video.read_bytes()
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as error:
            main(["--video", str(self.video), "--headless", "--frame-log", str(self.video)])
        self.assertEqual(error.exception.code, 2)
        self.assertEqual(self.video.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
