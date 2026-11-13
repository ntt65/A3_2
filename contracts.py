"""Data and interfaces shared by the video-analysis modules."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from math import isfinite
from typing import Protocol, TypeAlias

import numpy as np
from numpy.typing import NDArray


BGRImage: TypeAlias = NDArray[np.uint8]
Point: TypeAlias = tuple[int, int]
BBox: TypeAlias = tuple[int, int, int, int]


@dataclass(frozen=True, slots=True, eq=False)
class Frame:
    """An H×W×3 BGR image with its original source position."""

    image: BGRImage = field(repr=False)
    frame_index: int
    source_timestamp_s: float | None = None

    def __post_init__(self) -> None:
        if self.frame_index < 0:
            raise ValueError("frame_index must be non-negative")
        timestamp = self.source_timestamp_s
        if timestamp is not None and (not isfinite(timestamp) or timestamp < 0):
            raise ValueError("source_timestamp_s must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class Detection:
    """A detected bounding box (x, y, w, h) and centroid (x, y)."""

    bbox: BBox
    centroid: Point


@dataclass(frozen=True, slots=True)
class TrackSnapshot:
    """A track's last observed geometry and current observation state."""

    track_id: int
    bbox: BBox
    centroid: Point
    trajectory: tuple[Point, ...]
    missed_frames: int
    observed_this_frame: bool


@dataclass(frozen=True, slots=True)
class TargetMatch:
    """A frame-level detection decision and unique feature-match counts."""

    detected: bool
    reference_keypoints: int
    frame_keypoints: int
    good_matches: int

    def __post_init__(self) -> None:
        if min(self.reference_keypoints, self.frame_keypoints) < 0:
            raise ValueError("keypoint counts must be non-negative")
        if not 0 <= self.good_matches <= min(self.reference_keypoints, self.frame_keypoints):
            raise ValueError("good_matches must be between zero and both keypoint counts")
        if self.detected and self.good_matches == 0:
            raise ValueError("a detected target requires at least one good match")

    @property
    def match_rate(self) -> float | None:
        """Return the matched fraction, or None if the reference has no keypoints."""
        if self.reference_keypoints == 0:
            return None
        return self.good_matches / self.reference_keypoints


class FrameSource(Protocol):
    @property
    def source_fps(self) -> float | None: ...

    def read(self) -> Frame | None: ...

    def close(self) -> None: ...


class MotionDetectorProtocol(Protocol):
    def detect(self, image: BGRImage, /) -> list[Detection]: ...


class TrackerProtocol(Protocol):
    def update(self, detections: Sequence[Detection], /) -> list[TrackSnapshot]: ...


class TargetMatcherProtocol(Protocol):
    def match(self, image: BGRImage, /) -> TargetMatch: ...
