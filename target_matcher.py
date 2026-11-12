"""Recognize a registered target with ORB descriptors and Hamming distance."""

from math import isfinite
from pathlib import Path

import cv2
import numpy as np

from numpy.typing import NDArray

from contracts import BGRImage, TargetMatch


class TargetMatcher:
    """Accept unique ratio-tested matches and require a configurable count."""

    def __init__(
        self,
        reference: BGRImage,
        *,
        nfeatures: int = 1000,
        ratio: float = 0.75,
        min_matches: int = 12,
    ) -> None:
        if nfeatures < 1:
            raise ValueError("nfeatures must be positive")
        if not isfinite(ratio) or not 0 < ratio < 1:
            raise ValueError("ratio must be between zero and one")
        if min_matches < 1:
            raise ValueError("min_matches must be positive")

        self._ratio = ratio
        self._min_matches = min_matches
        self._orb = cv2.ORB_create(nfeatures=nfeatures, edgeThreshold=15)
        self._matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
        self._reference_count, self._reference_descriptors = self._features(reference)

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        *,
        nfeatures: int = 1000,
        ratio: float = 0.75,
        min_matches: int = 12,
    ) -> "TargetMatcher":
        """Load an image from a path, including Unicode paths on Windows."""
        path = Path(path)
        encoded = np.frombuffer(path.read_bytes(), dtype=np.uint8)
        image = cv2.imdecode(encoded, cv2.IMREAD_COLOR) if encoded.size else None
        if image is None:
            raise ValueError(f"Could not decode target image: {path}")
        return cls(image, nfeatures=nfeatures, ratio=ratio, min_matches=min_matches)

    def _features(self, image: BGRImage) -> tuple[int, NDArray[np.uint8] | None]:
        if image.size == 0:
            return 0, None
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        keypoints, descriptors = self._orb.detectAndCompute(gray, None)
        return len(keypoints), descriptors

    def match(self, image: BGRImage, /) -> TargetMatch:
        frame_count, descriptors = self._features(image)
        reference = self._reference_descriptors
        if reference is None or descriptors is None or len(descriptors) < 2:
            return TargetMatch(False, self._reference_count, frame_count, 0)

        nearest = self._matcher.knnMatch(reference, descriptors, k=2)
        candidates = [
            pair[0]
            for pair in nearest
            if len(pair) == 2 and pair[0].distance < self._ratio * pair[1].distance
        ]
        # Each query contributes one candidate. Count each frame keypoint once.
        good_matches = len({candidate.trainIdx for candidate in candidates})
        return TargetMatch(
            good_matches >= self._min_matches,
            self._reference_count,
            frame_count,
            good_matches,
        )
