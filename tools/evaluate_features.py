"""Measure five controlled ORB rotation and occlusion conditions."""

import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path
import platform

import cv2
import numpy as np

from target_matcher import TargetMatcher
from tools.evaluate_learning_rates import measurement_provenance


def load_image(path: Path):
    encoded = np.frombuffer(path.read_bytes(), dtype=np.uint8)
    image = cv2.imdecode(encoded, cv2.IMREAD_COLOR) if encoded.size else None
    if image is None:
        raise ValueError(f"could not decode {path}")
    return image


def conditions(image):
    height, width = image.shape[:2]
    side = int(np.ceil(np.hypot(height, width))) + 32
    x, y = (side - width) // 2, (side - height) // 2
    frontal = np.full((side, side, 3), 127, dtype=np.uint8)
    frontal[y:y + height, x:x + width] = image
    yield "frontal", 0, 0.0, frontal
    for angle in (30, 60):
        matrix = cv2.getRotationMatrix2D((side / 2, side / 2), angle, 1.0)
        rotated = cv2.warpAffine(frontal, matrix, (side, side), borderValue=(127,) * 3)
        yield f"rotate_{angle}", angle, 0.0, rotated
    for fraction in (0.3, 0.5):
        hidden = round(width * fraction)
        occluded = frontal.copy()
        occluded[y:y + height, x:x + hidden] = 127
        yield f"occlude_{round(fraction * 100)}", 0, hidden / width, occluded


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--positive-scene", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    measurement = measurement_provenance("tools.evaluate_features", (
        "tools/evaluate_features.py", "tools/evaluate_learning_rates.py", "target_matcher.py", "contracts.py",
    ))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    cv2.setNumThreads(1)
    cv2.setRNGSeed(0)

    reference = load_image(args.reference)
    matcher = TargetMatcher(reference)
    rows = []
    for condition, degrees, occluded_fraction, frame in conditions(reference):
        result = matcher.match(frame)
        rows.append({
            "condition": condition, "rotation_deg": degrees,
            "occluded_fraction": occluded_fraction,
            "reference_keypoints": result.reference_keypoints,
            "frame_keypoints": result.frame_keypoints,
            "good_matches": result.good_matches, "match_rate": result.match_rate,
            "detected": result.detected,
        })

    with (args.output_dir / "feature_conditions.csv").open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)

    metadata = {
        "measurement": measurement,
        "python": platform.python_version(), "opencv": cv2.__version__, "numpy": np.__version__,
        "reference_file": args.reference.name,
        "reference_sha256": sha256(args.reference.read_bytes()).hexdigest(),
        "nfeatures": 1000, "ratio": 0.75, "min_matches": 12,
        "method": "same physical image, in-plane rotation on padded canvas, flat left-side occlusion",
    }
    if args.positive_scene:
        positive = matcher.match(load_image(args.positive_scene))
        metadata["positive_scene"] = {
            "file": args.positive_scene.name,
            "sha256": sha256(args.positive_scene.read_bytes()).hexdigest(),
            "reference_keypoints": positive.reference_keypoints,
            "frame_keypoints": positive.frame_keypoints,
            "good_matches": positive.good_matches,
            "match_rate": positive.match_rate, "detected": positive.detected,
        }
    (args.output_dir / "feature_metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Measured {len(rows)} ORB conditions in {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
