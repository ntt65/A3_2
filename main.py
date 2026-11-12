"""Run the motion detector, tracker and target matcher on a video or camera."""

import argparse
from collections.abc import Sequence
from contextlib import ExitStack, suppress
from dataclasses import asdict, dataclass
import json
from math import isfinite
from pathlib import Path
from platform import python_version
import subprocess
import sys
from time import perf_counter
from typing import TextIO

import cv2
import numpy as np

from contracts import BGRImage, Detection, Frame, TargetMatch, TrackSnapshot
from motion_detector import MotionDetector
from target_matcher import TargetMatcher
from tracker import Tracker
from video import KeyAction, PlaybackControls, ProcessingFPS, VideoError, VideoSource, save_snapshot
from visualizer import render_frame


WINDOW_NAME = "A3_2 Video Analysis"
FALLBACK_OUTPUT_FPS = 30.0


@dataclass(slots=True)
class RunResult:
    status: str = "completed"
    reason: str = "source_eof"
    frames_processed: int = 0
    source_fps: float | None = None
    annotated_video_fps: float | None = None
    error: str | None = None


def _finite_float(value: str) -> float:
    number = float(value)
    if not isfinite(number):
        raise argparse.ArgumentTypeError("must be finite")
    return number


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--video", type=Path, help="input video path")
    source.add_argument("--camera", type=int, help="camera index")
    parser.add_argument("--target", type=Path, help="image of the registered target")
    parser.add_argument("--headless", action="store_true", help="process without opening a window")
    parser.add_argument("--frame-log", type=Path, help="write per-frame JSONL to this path")
    parser.add_argument("--summary-json", type=Path, help="write run status and parameters as JSON")
    parser.add_argument(
        "--annotated-video", type=Path,
        help="write FFV1 to a .mkv path (30 FPS if the source FPS is unknown)",
    )
    parser.add_argument("--learning-rate", type=_finite_float, default=-1.0, help="MOG2 learning rate (-1: auto)")
    parser.add_argument("--min-area", type=_finite_float, default=500.0, help="minimum contour area in pixels")
    parser.add_argument("--kernel-size", type=int, default=5, help="odd morphology kernel size")
    parser.add_argument("--max-distance", type=_finite_float, default=60.0, help="maximum tracking distance")
    parser.add_argument("--max-missed", type=int, default=5, help="consecutive missed frames to retain")
    parser.add_argument(
        "--snapshot-dir", type=Path, default=Path("outputs/snapshots"),
        help="directory for PNG snapshots (s saves, p pauses/resumes, q quits)",
    )
    return parser


def _check_paths(args: argparse.Namespace, snapshot: Path | None = None) -> None:
    inputs = [args.video, args.target]
    outputs = [args.frame_log, args.summary_json, args.annotated_video, snapshot]
    occupied = {path.resolve() for path in inputs if path is not None}
    for path in outputs:
        if path is None:
            continue
        resolved = path.resolve()
        if resolved in occupied or (
            resolved.exists() and any(other.exists() and resolved.samefile(other) for other in occupied)
        ):
            raise ValueError(f"Input and output file paths must be distinct: {path}")
        occupied.add(resolved)


def _open_writer(path: Path, fps: float, image: BGRImage) -> cv2.VideoWriter:
    height, width = image.shape[:2]
    if width % 2 or height % 2:
        raise VideoError("FFV1 output requires even frame dimensions in OpenCV")
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(
        str(path), cv2.CAP_FFMPEG, cv2.VideoWriter_fourcc(*"FFV1"), fps, (width, height)
    )
    if not writer.isOpened():
        writer.release()
        raise VideoError(f"Could not open FFV1 output {path}")
    return writer


def _write_log(
    stream: TextIO,
    frame: Frame,
    detections: list[Detection],
    tracks: list[TrackSnapshot],
    target: TargetMatch | None,
    foreground_fraction: float,
) -> None:
    target_data = None if target is None else {**asdict(target), "match_rate": target.match_rate}
    row = {
        "frame_index": frame.frame_index,
        "source_timestamp_s": frame.source_timestamp_s,
        "detections": [asdict(detection) for detection in detections],
        "tracks": [asdict(track) for track in tracks],
        "target": target_data,
        "foreground_fraction": foreground_fraction,
    }
    stream.write(json.dumps(row, allow_nan=False, separators=(",", ":")) + "\n")


def _close_window() -> None:
    with suppress(cv2.error):
        cv2.destroyWindow(WINDOW_NAME)


def _window_visible() -> bool:
    with suppress(cv2.error):
        return cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) >= 1
    return False


def _playback_keys(
    args: argparse.Namespace,
    controls: PlaybackControls,
    meter: ProcessingFPS,
    frame: Frame,
    rendered: BGRImage,
    delay_ms: int,
) -> str | None:
    while True:
        action = controls.handle_key(cv2.waitKey(delay_ms))
        if action is KeyAction.QUIT:
            return "user_quit"
        if not _window_visible():
            return "window_closed"
        if action is KeyAction.SAVE:
            destination = args.snapshot_dir / f"frame-{frame.frame_index:06d}.png"
            _check_paths(args, destination)
            print(f"Snapshot saved: {save_snapshot(rendered, destination)}")
        if action is KeyAction.RESUME:
            meter.reset()
        if not controls.paused:
            return None
        delay_ms = 30


def _run(args: argparse.Namespace, result: RunResult) -> None:
    detector = MotionDetector(
        min_area=args.min_area, kernel_size=args.kernel_size, learning_rate=args.learning_rate
    )
    tracker = Tracker(max_distance=args.max_distance, max_missed=args.max_missed)
    matcher = None if args.target is None else TargetMatcher.from_file(args.target)
    controls = PlaybackControls()
    meter = ProcessingFPS()

    with ExitStack() as resources:
        source = resources.enter_context(VideoSource(args.video if args.video is not None else args.camera))
        result.source_fps = source.source_fps
        log = None
        if args.frame_log is not None:
            args.frame_log.parent.mkdir(parents=True, exist_ok=True)
            log = resources.enter_context(args.frame_log.open("w", encoding="utf-8", newline="\n"))
        if not args.headless:
            cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
            resources.callback(_close_window)

        writer = None
        output_shape = None
        while True:
            started = perf_counter()
            frame = source.read()
            if frame is None:
                return

            detections = detector.detect(frame.image)
            tracks = tracker.update(detections)
            target = None if matcher is None else matcher.match(frame.image)
            fps = meter.record_frame(perf_counter() - started)

            if log is not None:
                mask = detector.last_clean_mask
                assert mask is not None  # detect() has produced the mask for this frame.
                _write_log(log, frame, detections, tracks, target, cv2.countNonZero(mask) / mask.size)

            result.frames_processed += 1
            if args.headless and args.annotated_video is None:
                continue

            rendered = render_frame(frame, tracks, target, fps)
            if args.annotated_video is not None:
                if writer is None:
                    output_fps = source.source_fps or FALLBACK_OUTPUT_FPS
                    writer = _open_writer(args.annotated_video, output_fps, rendered)
                    resources.callback(writer.release)
                    result.annotated_video_fps = output_fps
                    output_shape = rendered.shape
                if rendered.shape != output_shape:
                    raise VideoError("Frame dimensions changed during FFV1 output")
                writer.write(rendered)

            if not args.headless:
                cv2.imshow(WINDOW_NAME, rendered)
                delay_ms = 1
                if args.video is not None and source.source_fps is not None:
                    delay_ms = max(1, round(1000 * (1 / source.source_fps - (perf_counter() - started))))
                reason = _playback_keys(args, controls, meter, frame, rendered, delay_ms)
                if reason is not None:
                    result.status, result.reason = "stopped", reason
                    return


def _git_metadata() -> dict[str, str | bool | None]:
    checkout = Path(__file__).resolve().parent
    options = {"cwd": checkout, "check": True, "capture_output": True, "text": True, "timeout": 3}
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], **options).stdout.strip()
        status = subprocess.run(["git", "--no-optional-locks", "status", "--porcelain"], **options)
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return {"commit": None, "dirty": None}
    return {"commit": commit, "dirty": bool(status.stdout.strip())}


def _write_summary(
    args: argparse.Namespace, result: RunResult, git: dict[str, str | bool | None]
) -> None:
    summary = {
        **asdict(result),
        "parameters": {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()},
        "versions": {"python": python_version(), "opencv": cv2.__version__, "numpy": np.__version__},
        "git": git,
    }
    args.summary_json.parent.mkdir(parents=True, exist_ok=True)
    args.summary_json.write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.camera is not None and args.camera < 0:
        parser.error("--camera must be non-negative")
    if args.annotated_video is not None and args.annotated_video.suffix.lower() != ".mkv":
        parser.error("--annotated-video must have a .mkv extension")
    try:
        _check_paths(args)
    except (OSError, ValueError) as error:
        parser.error(str(error))

    result = RunResult()
    git = _git_metadata() if args.summary_json is not None else {}
    try:
        _run(args, result)
    except KeyboardInterrupt:
        result.status, result.reason = "stopped", "keyboard_interrupt"
    except (cv2.error, OSError, ValueError, VideoError) as error:
        result.status, result.reason, result.error = "failed", "runtime_error", str(error)

    if args.summary_json is not None:
        try:
            _write_summary(args, result, git)
        except (OSError, ValueError) as error:
            print(f"Could not write run summary: {error}", file=sys.stderr)
            return 1

    if result.error is not None:
        print(f"Error: {result.error}", file=sys.stderr)
        return 1
    print(f"Processed {result.frames_processed} frames ({result.reason}).")
    return 130 if result.reason == "keyboard_interrupt" else 0


if __name__ == "__main__":
    sys.exit(main())
