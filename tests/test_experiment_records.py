import json
from collections import Counter
from pathlib import Path
import unittest

import numpy as np

from tools.evaluate_features import conditions
from tools.evaluate_learning_rates import sustained_quiet
from tools.summarize_events import associated_tracks, continuity_changes, failure_runs, manual_box, switch_runs


def history(values, first=0):
    return [
        {"source_frame": index, "eligible": identity != -1, "track_id": identity}
        for index, identity in enumerate(values, first)
    ]


class EvaluationTests(unittest.TestCase):
    def test_failure_threshold_and_recovery(self) -> None:
        rows = history([None] * 9 + [8] + [None] * 11, first=20)
        self.assertEqual(failure_runs(rows), [[30, 40]])

    def test_excluded_frame_breaks_missing_run(self) -> None:
        self.assertEqual(failure_runs(history([None] * 6 + [-1] + [None] * 6)), [])

    def test_uncertain_visibility_is_distinct_from_physical_occlusion(self) -> None:
        annotation = {
            "size": [10, 20], "keyframes": [[10, 50, 50], [15, 60, 50]],
            "excluded": [[12, 12]], "uncertain": [[13, 13]],
        }
        asset = {"width": 100, "height": 100}
        self.assertEqual(manual_box(annotation, 12, asset), (None, "occluded_at_least_half"))
        self.assertEqual(manual_box(annotation, 13, asset), (None, "visibility_uncertain"))
        self.assertEqual(manual_box(annotation, 11, asset), ((47, 40, 10, 20), ""))

    def test_switch_threshold_and_sustained_error_count_once(self) -> None:
        old = [3] * 3 + [None] * 2
        self.assertIsNone(switch_runs(history(old + [4] * 4), 3, 4))
        self.assertEqual(switch_runs(history(old + [4] * 8), 3, 4), [
            {"start_frame": 5, "end_frame": 12, "from_id": 3, "to_id": 4},
        ])

    def test_switch_requires_a_stable_pre_overlap_identity(self) -> None:
        rows = history([1, 2, 1, None, None, 7, 7, 7, 7, 7])
        self.assertIsNone(switch_runs(rows, 3, 4))

    def test_continuity_uses_stable_baseline_and_does_not_bridge_exclusions(self) -> None:
        rows = history([8] * 3 + [2] * 3 + [-1] + [2] * 2 + [7] * 5)
        self.assertEqual(continuity_changes(rows), [
            {"start_frame": 9, "end_frame": 13, "from_id": 8, "to_id": 7},
        ])

    def test_association_uses_observed_boxes_once_and_rejects_whole_frame(self) -> None:
        target = (0, 0, 30, 40)
        matches, _ = associated_tracks([target, (3, 3, 30, 40)], [
            {"track_id": 1, "bbox": target, "observed_this_frame": True},
            {"track_id": 2, "bbox": target, "observed_this_frame": False},
            {"track_id": 3, "bbox": (0, 0, 100, 100), "observed_this_frame": True},
        ])
        self.assertEqual(matches, {0: (1, 1.0)})

    def test_learning_quiet_threshold_requires_five_consecutive_frames(self) -> None:
        frames = [{"foreground_fraction": value} for value in [0.6, 0.1, 0.1, 0.3] + [0.1] * 5]
        self.assertEqual(sustained_quiet(frames, 1), 3)
        self.assertIsNone(sustained_quiet(frames, 5))

    def test_orb_conditions_use_same_canvas_and_exact_mask_widths(self) -> None:
        rows = list(conditions(np.zeros((10, 20, 3), dtype=np.uint8)))
        self.assertEqual([(label, degrees, fraction) for label, degrees, fraction, _ in rows], [
            ("frontal", 0, 0.0), ("rotate_30", 30, 0.0), ("rotate_60", 60, 0.0),
            ("occlude_30", 0, 0.3), ("occlude_50", 0, 0.5),
        ])
        self.assertEqual(len({image.shape for _, _, _, image in rows}), 1)
        self.assertEqual([np.count_nonzero(row[3][:, :, 0] == 0) for row in rows[-2:]], [140, 100])

    def test_preselected_event_counts_and_manual_annotations(self) -> None:
        root = Path(__file__).resolve().parents[1] / "experiments"
        plan = json.loads((root / "event_plan.json").read_text(encoding="utf-8"))["events"]
        manual = json.loads((root / "annotations/manual_subjects.json").read_text(encoding="utf-8"))["events"]
        self.assertEqual(Counter(event["condition"] for event in plan), {
            "single_moving": 10, "overlap": 10, "stop": 5, "illumination": 5,
        })
        for event in plan:
            if not event["annotation_ids"]:
                self.assertEqual(len(manual[event["event_id"]]["subjects"]), len(event["subjects"]))


if __name__ == "__main__":
    unittest.main()
