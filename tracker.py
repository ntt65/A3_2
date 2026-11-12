"""Greedy association of detections to tracks using centroid distance."""

from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from math import hypot, isfinite

from contracts import Detection, Point, TrackSnapshot


@dataclass(slots=True)
class _Track:
    detection: Detection
    trajectory: deque[Point]
    missed_frames: int = 0

    def observe(self, detection: Detection) -> None:
        self.detection = detection
        self.trajectory.append(detection.centroid)
        self.missed_frames = 0


class Tracker:
    """Keep track IDs across at most max_missed consecutive missed frames."""

    def __init__(
        self,
        max_distance: float = 60.0,
        max_missed: int = 5,
        trajectory_length: int = 30,
    ) -> None:
        if not isfinite(max_distance) or max_distance < 0:
            raise ValueError("max_distance must be finite and non-negative")
        if max_missed < 0:
            raise ValueError("max_missed must be non-negative")
        if trajectory_length < 1:
            raise ValueError("trajectory_length must be positive")
        self._max_distance = max_distance
        self._max_missed = max_missed
        self._trajectory_length = trajectory_length
        self._tracks: dict[int, _Track] = {}
        self._next_id = 1

    def update(self, detections: Sequence[Detection]) -> list[TrackSnapshot]:
        """Advance one frame and return active tracks in ascending ID order."""
        ordered = sorted(detections, key=lambda detection: (detection.bbox, detection.centroid))
        candidates: list[tuple[float, int, int]] = []
        for track_id, track in self._tracks.items():
            x, y = track.detection.centroid
            for index, detection in enumerate(ordered):
                other_x, other_y = detection.centroid
                distance = hypot(x - other_x, y - other_y)
                if distance <= self._max_distance:
                    candidates.append((distance, track_id, index))

        matched_ids: set[int] = set()
        matched_detections: set[int] = set()
        for _, track_id, index in sorted(candidates):
            if track_id in matched_ids or index in matched_detections:
                continue
            self._tracks[track_id].observe(ordered[index])
            matched_ids.add(track_id)
            matched_detections.add(index)

        expired: list[int] = []
        for track_id, track in self._tracks.items():
            if track_id in matched_ids:
                continue
            track.missed_frames += 1
            if track.missed_frames > self._max_missed:
                expired.append(track_id)
        for track_id in expired:
            del self._tracks[track_id]

        for index, detection in enumerate(ordered):
            if index in matched_detections:
                continue
            trajectory = deque([detection.centroid], maxlen=self._trajectory_length)
            self._tracks[self._next_id] = _Track(detection, trajectory)
            self._next_id += 1

        return [
            TrackSnapshot(
                track_id=track_id,
                bbox=track.detection.bbox,
                centroid=track.detection.centroid,
                trajectory=tuple(track.trajectory),
                missed_frames=track.missed_frames,
                observed_this_frame=track.missed_frames == 0,
            )
            for track_id, track in self._tracks.items()
        ]
