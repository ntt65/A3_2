"""Find moving regions with a MOG2 background model."""

from math import isfinite

import cv2
import numpy as np
from numpy.typing import NDArray

from contracts import BGRImage, Detection


class MotionDetector:
    """Detect foreground in consecutive BGR frames from one video source.

    The default learning rate (-1) lets MOG2 choose how fast to update.
    Use reset() before an independent run. Initial frames train the new
    background model and can contain foreground responses.
    """

    def __init__(
        self,
        *,
        min_area: float = 500.0,
        kernel_size: int = 5,
        learning_rate: float = -1.0,
        shadow_threshold: float = 0.5,
    ) -> None:
        if not isfinite(min_area) or min_area < 0:
            raise ValueError("min_area must be finite and non-negative")
        if not isinstance(kernel_size, int) or kernel_size < 1 or kernel_size % 2 == 0:
            raise ValueError("kernel_size must be a positive odd integer")
        if learning_rate != -1.0 and not 0 <= learning_rate <= 1:
            raise ValueError("learning_rate must be -1 or between 0 and 1")
        if not 0 <= shadow_threshold <= 1:
            raise ValueError("shadow_threshold must be between 0 and 1")

        self._min_area = min_area
        self._learning_rate = learning_rate
        self._shadow_threshold = shadow_threshold
        self._kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (kernel_size, kernel_size)
        )
        self.reset()

    @property
    def last_raw_mask(self) -> NDArray[np.uint8] | None:
        """Return a copy of the latest MOG2 mask, including shadow labels."""
        return None if self._raw_mask is None else self._raw_mask.copy()

    @property
    def last_clean_mask(self) -> NDArray[np.uint8] | None:
        """Return a copy of the latest binary mask after morphology."""
        return None if self._clean_mask is None else self._clean_mask.copy()

    def reset(self) -> None:
        """Discard learned background and diagnostic masks, keeping settings."""
        self._background = cv2.createBackgroundSubtractorMOG2(detectShadows=True)
        self._background.setShadowThreshold(self._shadow_threshold)
        self._raw_mask: NDArray[np.uint8] | None = None
        self._clean_mask: NDArray[np.uint8] | None = None

    def detect(self, image: BGRImage, /) -> list[Detection]:
        """Update MOG2 and return foreground detections in coordinate order."""
        if (
            image.ndim != 3
            or image.shape[2] != 3
            or image.size == 0
            or image.dtype != np.uint8
        ):
            raise ValueError("image must be a non-empty uint8 BGR image")

        raw_mask = self._background.apply(image, learningRate=self._learning_rate)
        foreground = cv2.compare(raw_mask, 255, cv2.CMP_EQ)
        opened = cv2.morphologyEx(foreground, cv2.MORPH_OPEN, self._kernel)
        clean_mask = cv2.morphologyEx(opened, cv2.MORPH_CLOSE, self._kernel)
        self._raw_mask = raw_mask
        self._clean_mask = clean_mask

        contours, _ = cv2.findContours(clean_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        detections = []
        for contour in contours:
            if cv2.contourArea(contour) < self._min_area:
                continue
            x, y, width, height = cv2.boundingRect(contour)
            moments = cv2.moments(contour)
            if moments["m00"]:
                centroid = (
                    int(moments["m10"] / moments["m00"]),
                    int(moments["m01"] / moments["m00"]),
                )
            else:
                centroid = (x + width // 2, y + height // 2)
            detections.append(Detection(bbox=(x, y, width, height), centroid=centroid))

        detections.sort(key=lambda detection: (detection.bbox, detection.centroid))
        return detections
