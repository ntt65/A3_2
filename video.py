"""Video capture, playback controls, processing FPS, and frame snapshots."""

from collections import deque
from contextlib import suppress
from enum import Enum, auto
from math import isfinite
from pathlib import Path
from struct import unpack_from
from tempfile import NamedTemporaryFile
from time import monotonic
from types import TracebackType

import cv2
import numpy as np

from contracts import BGRImage, Frame


class VideoError(RuntimeError):
    """A capture or snapshot operation failed."""


def _indexed_avi_frame_count(source: str) -> int | None:
    """Read the declared frame count from a standard indexed AVI header."""
    path = Path(source)
    if path.suffix.lower() != ".avi":
        return None

    try:
        with path.open("rb") as stream:
            header = stream.read(52)
    except OSError:
        return None

    if (
        len(header) < 52
        or not header.startswith(b"RIFF")
        or header[8:16] != b"AVI LIST"
        or header[20:28] != b"hdrlavih"
        or unpack_from("<I", header, 28)[0] < 56
    ):
        return None

    # AVIMAINHEADER starts at byte 32. The flags and total frames are at +12 and +16.
    flags, count = unpack_from("<II", header, 44)
    return count if flags & 0x10 and count > 0 else None  # AVIF_HASINDEX


class VideoSource:
    """Read a file or camera sequentially and release it on context exit."""

    def __init__(self, source: str | Path | int) -> None:
        source = str(source) if isinstance(source, Path) else source
        self._source = source
        self._capture = cv2.VideoCapture()
        self._closed = False
        self._eof = False
        self._next_index = 0
        self._expected_frame_count: int | None = None
        self._camera_started_at: float | None = None

        try:
            if not self._capture.open(self._source):
                raise VideoError(f"Could not open video source {self._source!r}")

            if isinstance(source, int):
                self._camera_started_at = monotonic()
            else:
                count = _indexed_avi_frame_count(source)
                if count is not None and self._capture.get(cv2.CAP_PROP_FRAME_COUNT) == count:
                    self._expected_frame_count = count

            fps = self._capture.get(cv2.CAP_PROP_FPS)
            self._source_fps = fps if isfinite(fps) and fps > 0 else None
        except cv2.error as error:
            self.close()
            raise VideoError(f"Could not open video source {self._source!r}") from error
        except VideoError:
            self.close()
            raise

    @property
    def source_fps(self) -> float | None:
        return self._source_fps

    def read(self) -> Frame | None:
        """Return the next frame or None at normal file EOF.

        An indexed AVI header that agrees with the backend can identify early
        EOF. For other files, OpenCV may report only a failed read and an
        estimated count, which cannot distinguish a late decode failure from EOF.
        """
        if self._closed:
            raise VideoError(f"Video source {self._source!r} is closed")
        if self._eof:
            return None

        index = self._next_index
        try:
            ok, image = self._capture.read()
        except cv2.error as error:
            raise VideoError(f"Read failed at frame {index} from {self._source!r}") from error

        if not ok:
            if isinstance(self._source, int):
                raise VideoError(f"Camera {self._source} failed to read frame {index}")
            if self._expected_frame_count is not None and index < self._expected_frame_count:
                raise VideoError(
                    f"Video {self._source!r} ended early at frame {index}; "
                    f"the source reports {self._expected_frame_count} frames"
                )
            if index == 0:
                raise VideoError(f"Video {self._source!r} has no readable frames")
            self._eof = True
            return None

        if (
            image is None
            or image.size == 0
            or image.ndim != 3
            or image.shape[2] != 3
            or image.dtype != np.uint8
        ):
            raise VideoError(f"Invalid BGR image at frame {index} from {self._source!r}")

        timestamp = None
        if self._camera_started_at is not None:
            timestamp = monotonic() - self._camera_started_at
        elif self._source_fps is not None:
            timestamp = index / self._source_fps

        frame = Frame(image=image, frame_index=index, source_timestamp_s=timestamp)
        self._next_index += 1
        return frame

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._capture.release()

    def __enter__(self) -> "VideoSource":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


class KeyAction(Enum):
    NONE = auto()
    QUIT = auto()
    SAVE = auto()
    PAUSE = auto()
    RESUME = auto()


class PlaybackControls:
    """Interpret OpenCV waitKey results while the caller owns the frame loop."""

    def __init__(self) -> None:
        self._paused = False

    @property
    def paused(self) -> bool:
        return self._paused

    def handle_key(self, key_code: int) -> KeyAction:
        if key_code in (ord("q"), ord("Q")):
            return KeyAction.QUIT
        if key_code in (ord("s"), ord("S")):
            return KeyAction.SAVE
        if key_code in (ord("p"), ord("P")):
            self._paused = not self._paused
            return KeyAction.PAUSE if self._paused else KeyAction.RESUME
        return KeyAction.NONE


class ProcessingFPS:
    """Compute throughput over the last 30 valid, actively processed frames."""

    def __init__(self) -> None:
        self._durations: deque[float] = deque(maxlen=30)

    @property
    def fps(self) -> float | None:
        if not self._durations:
            return None
        value = len(self._durations) / sum(self._durations)
        return value if isfinite(value) and value > 0 else None

    def record_frame(self, elapsed_s: float) -> float | None:
        """Record a frame's elapsed processing time in seconds."""
        if isfinite(elapsed_s) and elapsed_s > 0:
            self._durations.append(elapsed_s)
        return self.fps

    def reset(self) -> None:
        """Clear earlier timings when playback resumes."""
        self._durations.clear()


def save_snapshot(image: BGRImage, path: str | Path) -> Path:
    """Write the rendered frame losslessly to a PNG, including Unicode paths."""
    destination = Path(path)
    if destination.suffix.lower() != ".png":
        raise VideoError(f"Snapshot path must end in .png: {destination}")

    temporary: Path | None = None
    try:
        ok, encoded = cv2.imencode(".png", image)
        if not ok:
            raise VideoError(f"Could not encode snapshot {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=destination.parent, delete=False) as output:
            temporary = Path(output.name)
            output.write(encoded.tobytes())
        temporary.replace(destination)
        temporary = None
    except (cv2.error, OSError) as error:
        raise VideoError(f"Could not save snapshot {destination}") from error
    finally:
        if temporary is not None:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)
    return destination
