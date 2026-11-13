"""Draw the analysis results on a copy of the source frame."""

from collections.abc import Sequence

import cv2

from contracts import BGRImage, Frame, Point, TargetMatch, TrackSnapshot


def _label(image: BGRImage, text: str, origin: Point, color: tuple[int, int, int]) -> None:
    cv2.putText(image, text, origin, cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(image, text, origin, cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)


def render_frame(
    frame: Frame,
    tracks: Sequence[TrackSnapshot],
    target: TargetMatch | None,
    processing_fps: float | None,
) -> BGRImage:
    """Show observed track geometry, its trajectory and the target decision."""
    image = frame.image.copy()
    for track in tracks:
        if not track.observed_this_frame:
            continue
        for start, end in zip(track.trajectory, track.trajectory[1:]):
            cv2.line(image, start, end, (0, 170, 255), 2, cv2.LINE_AA)
        x, y, width, height = track.bbox
        cv2.rectangle(image, (x, y), (x + width - 1, y + height - 1), (0, 225, 0), 2)
        cv2.circle(image, track.centroid, 3, (0, 170, 255), -1, cv2.LINE_AA)
        _label(image, f"ID:{track.track_id}", (x, max(13, y - 5)), (255, 255, 255))

    fps_text = "--" if processing_fps is None else f"{processing_fps:.1f}"
    _label(image, f"FPS: {fps_text}  Frame: {frame.frame_index}", (8, 20), (255, 255, 255))
    if target is not None and target.detected:
        _label(image, "TARGET DETECTED", (8, 42), (0, 225, 255))
    return image
