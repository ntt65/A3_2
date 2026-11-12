"""Export an inclusive source-frame range as lossless AVI and a frame map."""

import argparse
import csv
from hashlib import sha256
from itertools import chain
from math import isfinite
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from zipfile import BadZipFile, ZipFile

import cv2
import numpy as np


def read_video(capture, start: int, end: int):
    for index in range(end + 1):
        ok, image = capture.read()
        if not ok:
            raise ValueError(f"video ended at frame {index} before requested frame {end}")
        if index >= start:
            yield index, "", image


def read_archive(archive: ZipFile, pattern: re.Pattern, start: int, end: int):
    members = {}
    for name in archive.namelist():
        match = pattern.fullmatch(name)
        if match:
            index = int(match.group("frame"))
            if index in members:
                raise ValueError(f"archive contains duplicate frame index {index}")
            members[index] = name
    for index in range(start, end + 1):
        if index not in members:
            raise ValueError(f"archive is missing requested frame {index}")
        name = members[index]
        data = np.frombuffer(archive.read(name), dtype=np.uint8)
        image = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"cannot decode archive member {name}")
        yield index, name, image


def write_clip(frames, fps: float, output: Path, mapping: Path) -> int:
    if not isfinite(fps) or fps <= 0:
        raise ValueError("a positive finite playback FPS is required")

    frames = iter(frames)
    first = next(frames)
    height, width = first[2].shape[:2]
    writer = cv2.VideoWriter(str(output), cv2.VideoWriter_fourcc(*"FFV1"), fps, (width, height))
    try:
        if not writer.isOpened():
            raise OSError(f"cannot open FFV1 writer for {output}")
        digest = sha256()
        with mapping.open("w", encoding="utf-8", newline="") as stream:
            rows = csv.writer(stream)
            rows.writerow(("clip_frame", "source_frame", "source_member"))
            count = 0
            for index, member, image in chain((first,), frames):
                if image.shape != first[2].shape:
                    raise ValueError(f"frame {index} has a different image shape")
                digest.update(image.tobytes())
                writer.write(image)
                rows.writerow((count, index, member))
                count += 1
    finally:
        writer.release()

    capture = cv2.VideoCapture(str(output))
    try:
        actual_fps = capture.get(cv2.CAP_PROP_FPS)
        if abs(actual_fps - fps) > 0.001:
            raise OSError(f"FFV1 output FPS mismatch: {actual_fps} versus {fps}")
        decoded = sha256()
        for _, _, image in read_video(capture, 0, count - 1):
            if image.shape != first[2].shape:
                raise OSError("FFV1 output has different dimensions than its source")
            decoded.update(image.tobytes())
        extra, _ = capture.read()
        if extra or digest.digest() != decoded.digest():
            raise OSError("FFV1 output does not reproduce the selected source pixels")
    finally:
        capture.release()
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="video file or ZIP of image frames")
    parser.add_argument("--start", type=int, required=True, help="first source index, inclusive")
    parser.add_argument("--end", type=int, required=True, help="last source index, inclusive")
    parser.add_argument("--output", type=Path, required=True, help="new FFV1 .avi file")
    parser.add_argument("--mapping", type=Path, required=True, help="new frame map .csv file")
    parser.add_argument("--member-pattern", help="archive-member regex with a named 'frame' group")
    parser.add_argument("--fps", type=float, help="explicit playback FPS for an image archive")
    args = parser.parse_args()

    if not 0 <= args.start <= args.end:
        parser.error("frame range must satisfy 0 <= start <= end")
    if args.output.suffix.lower() != ".avi" or args.mapping.suffix.lower() != ".csv":
        parser.error("output must end in .avi and mapping must end in .csv")
    if args.output.exists() or args.mapping.exists():
        parser.error("output and mapping must be new files")
    if (args.member_pattern is None) != (args.fps is None):
        parser.error("--member-pattern and --fps must be supplied together for a ZIP archive")

    try:
        for destination in (args.output, args.mapping):
            destination.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=args.output.parent) as video_stage, \
             TemporaryDirectory(dir=args.mapping.parent) as map_stage:
            video = Path(video_stage) / args.output.name
            mapping = Path(map_stage) / args.mapping.name
            if args.member_pattern is not None:
                pattern = re.compile(args.member_pattern)
                if "frame" not in pattern.groupindex:
                    raise ValueError("the archive member pattern needs a named 'frame' group")
                with ZipFile(args.source) as archive:
                    frames = read_archive(archive, pattern, args.start, args.end)
                    count = write_clip(frames, args.fps, video, mapping)
            else:
                capture = cv2.VideoCapture(str(args.source))
                try:
                    if not capture.isOpened():
                        raise OSError(f"cannot open {args.source}")
                    fps = capture.get(cv2.CAP_PROP_FPS)
                    frames = read_video(capture, args.start, args.end)
                    count = write_clip(frames, fps, video, mapping)
                finally:
                    capture.release()
            video.rename(args.output)
            try:
                mapping.rename(args.mapping)
            except OSError:
                args.output.unlink()
                raise
    except (BadZipFile, OSError, ValueError, re.error, cv2.error) as error:
        parser.exit(1, f"Clip preparation failed: {error}\n")
    print(f"Verified {count} lossless frames and wrote {args.output} and {args.mapping}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
