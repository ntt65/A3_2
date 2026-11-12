"""Reproduce tracking observations from the preselected event plan."""

from collections import Counter
import json
from pathlib import Path
from xml.etree import ElementTree

from tools.evaluate_learning_rates import (
    arguments, load_inputs, measurement_provenance, prepare_clip, read_json, run_app,
    sha256_file, verified_source, write_csv, write_json,
)


def intersection_over_union(first, second) -> float:
    x1, y1, w1, h1 = first
    x2, y2, w2, h2 = second
    width = max(0, min(x1 + w1, x2 + w2) - max(x1, x2))
    height = max(0, min(y1 + h1, y2 + h2) - max(y1, y2))
    area = width * height
    return area / (w1 * h1 + w2 * h2 - area) if area else 0.0


def associated_tracks(boxes, tracks, threshold=0.20):
    candidates = []
    observed = [track for track in tracks if track["observed_this_frame"]]
    for subject, box in enumerate(boxes):
        if box is None:
            continue
        for track in observed:
            score = intersection_over_union(box, track["bbox"])
            if score >= threshold:
                candidates.append((-score, subject, track["track_id"]))
    associations, used_tracks = {}, set()
    for negative_score, subject, track_id in sorted(candidates):
        if subject not in associations and track_id not in used_tracks:
            associations[subject] = track_id, -negative_score
            used_tracks.add(track_id)
    return associations, observed


def bounds(x, y, width, height, asset):
    left = max(0, round(x - width / 2))
    top = max(0, round(y - height / 2))
    right = min(asset["width"], round(x + width / 2))
    bottom = min(asset["height"], round(y + height / 2))
    if right <= left or bottom <= top:
        return None
    return left, top, right - left, bottom - top


def manual_box(annotation, index, asset):
    if any(first <= index <= last for first, last in annotation["excluded"]):
        return None, "occluded_at_least_half"
    if any(first <= index <= last for first, last in annotation.get("uncertain", [])):
        return None, "visibility_uncertain"
    keys = annotation["keyframes"]
    if not keys[0][0] <= index <= keys[-1][0]:
        return None, "out_of_frame_or_unconfirmed"
    for first, last in zip(keys, keys[1:]):
        if first[0] <= index <= last[0]:
            weight = (index - first[0]) / (last[0] - first[0])
            start = first[1:] if len(first) == 5 else first[1:] + annotation["size"]
            end = last[1:] if len(last) == 5 else last[1:] + annotation["size"]
            position = [a + weight * (b - a) for a, b in zip(start, end)]
            box = bounds(*position, asset)
            return (box, "") if box else (None, "out_of_frame_or_unconfirmed")
    raise ValueError("manual annotations require two or more ordered keyframes")


def read_caviar(path: Path):
    reference = {}
    for frame in ElementTree.parse(path).iter("frame"):
        index = int(frame.attrib["number"])
        reference[index] = {}
        for subject in frame.findall("./objectlist/object"):
            box = subject.find("box")
            if box is not None:
                reference[index][int(subject.attrib["id"])] = (
                    tuple(float(box.attrib[key]) for key in ("xc", "yc", "w", "h")),
                    subject.findtext("appearance", default="").strip().lower(),
                )
    return reference


def caviar_box(reference, subject_id, index, asset):
    subject = reference.get(index, {}).get(subject_id)
    if subject is None:
        return None, "out_of_frame_or_unconfirmed"
    position, appearance = subject
    if appearance in {"occluded", "hidden"}:
        return None, "visibility_uncertain"
    box = bounds(*position, asset)
    return (box, "") if box else (None, "out_of_frame_or_unconfirmed")


def runs(rows, key, minimum):
    """Return contiguous (start frame, end frame, value) runs."""
    groups = []
    start = previous = None
    value = None
    for row in rows:
        index = row["source_frame"]
        item = key(row)
        if start is not None and (item != value or index != previous + 1):
            if previous - start + 1 >= minimum:
                groups.append((start, previous, value))
            start = None
        if item is not None and start is None:
            start, value = index, item
        previous = index
    if start is not None and previous - start + 1 >= minimum:
        groups.append((start, previous, value))
    return groups


def observed_id(row):
    return row["track_id"] if row["eligible"] else None


def failure_runs(rows):
    return [
        [start, end] for start, end, _ in runs(
            rows, lambda row: True if row["eligible"] and row["track_id"] is None else None, 10
        )
    ]


def switch_runs(rows, overlap_start: int, overlap_end: int):
    before = runs((row for row in rows if row["source_frame"] < overlap_start), observed_id, 3)
    after = runs((row for row in rows if row["source_frame"] > overlap_end), observed_id, 5)
    if not before or not after:
        return None
    return identity_changes(before[-1][2], after)


def continuity_changes(rows):
    baseline = runs(rows, observed_id, 3)
    if not baseline:
        return None
    first_start, first_end, identity = baseline[0]
    subsequent = runs((row for row in rows if row["source_frame"] > first_end), observed_id, 5)
    if first_end - first_start + 1 < 5 and not subsequent:
        return None
    return identity_changes(identity, subsequent)


def identity_changes(previous, candidates):
    switches = []
    for start, end, identity in candidates:
        if identity != previous:
            switches.append({
                "start_frame": start, "end_frame": end, "from_id": previous, "to_id": identity,
            })
            previous = identity
    return switches


def observe(event, asset, frames, manual, caviar):
    rows = []
    offset = event["clip_start_frame"]
    subject_count = len(event["subjects"])
    for index in range(event["start_frame"], event["end_frame"] + 1):
        if caviar is None:
            references = [manual_box(annotation, index, asset) for annotation in manual["subjects"]]
        else:
            references = [
                caviar_box(caviar, subject_id, index, asset) for subject_id in event["annotation_ids"]
            ]
        if len(references) != subject_count:
            raise ValueError(f"incomplete subject reference for {event['event_id']}")
        frame = frames[index - offset]
        matches, observed = associated_tracks([box for box, _ in references], frame["tracks"])
        candidates = json.dumps(
            [[track["track_id"], *track["bbox"]] for track in observed], separators=(",", ":"),
        )
        for subject, (box, reason) in enumerate(references):
            track_id, score = matches.get(subject, (None, None))
            rows.append({
                "event_id": event["event_id"], "subject": subject + 1, "source_frame": index,
                "source_timestamp_s": index / asset["source_fps"] if asset["source_fps"] else None,
                "eligible": box is not None, "excluded_reason": reason,
                "reference_bbox": json.dumps(box, separators=(",", ":")) if box else "",
                "track_id": track_id, "match_iou": round(score, 6) if score is not None else None,
                "observed_track_boxes": candidates,
            })
    return rows


def event_result(event, evidence, manual, distance):
    subjects, failures, switches, switch_eligible, valid_subjects = [], 0, 0, 0, 0
    continuity_count, continuity_eligible = 0, 0
    for subject in range(1, len(event["subjects"]) + 1):
        rows = [row for row in evidence if row["subject"] == subject]
        missing = failure_runs(rows)
        changes, continuity = None, None
        if event["condition"] == "overlap":
            changes = switch_runs(rows, manual["overlap_start"], manual["overlap_end"])
        else:
            continuity = continuity_changes(rows)
        if changes is not None:
            switch_eligible += 1
            switches += len(changes)
        if continuity is not None:
            continuity_eligible += 1
            continuity_count += len(continuity)
        assessable = bool(runs(rows, lambda row: True if row["eligible"] else None, 10))
        valid_subjects += int(assessable)
        failures += len(missing)
        subjects.append({
            "subject": subject, "failure_assessable": assessable,
            "failures": missing, "switches": changes, "continuity_changes": continuity,
        })

    exclusions = Counter(row["excluded_reason"] for row in evidence)
    return {
        "event_id": event["event_id"], "condition": event["condition"], "source_id": event["source_id"],
        "start_frame": event["start_frame"], "end_frame": event["end_frame"],
        "max_distance": distance, "valid_event": bool(valid_subjects),
        "eligible_target_frames": exclusions[""],
        "excluded_occluded_target_frames": exclusions["occluded_at_least_half"],
        "excluded_other_target_frames": len(evidence) - exclusions[""] - exclusions["occluded_at_least_half"],
        "id_switch_eligible_subjects": switch_eligible,
        "id_switch_count": switches if switch_eligible else None,
        "continuity_eligible_subjects": continuity_eligible,
        "continuity_change_count": continuity_count if continuity_eligible else None,
        "tracking_failure_count": failures, "failed_event": bool(failures) if valid_subjects else None,
        "observation_notes": event["notes"], "evidence_path": "event_frames.csv",
    }, subjects


def aggregate(rows):
    groups = {}
    for row in rows:
        groups.setdefault((row["max_distance"], row["condition"]), []).append(row)
    summaries = []
    for (distance, condition), items in groups.items():
        valid = sum(item["valid_event"] for item in items)
        failed = sum(item["failed_event"] is True for item in items)
        switch_eligible = sum(item["id_switch_eligible_subjects"] for item in items)
        continuity_eligible = sum(item["continuity_eligible_subjects"] for item in items)
        summaries.append({
            "max_distance": distance, "condition": condition, "planned_events": len(items),
            "valid_events": valid, "failed_events": failed,
            "tracking_failures": sum(item["tracking_failure_count"] for item in items),
            "failure_rate": failed / valid if valid else None,
            "id_switch_eligible_subjects": switch_eligible,
            "id_switch_count": sum(item["id_switch_count"] or 0 for item in items) if switch_eligible else None,
            "continuity_eligible_subjects": continuity_eligible,
            "continuity_change_count": sum(item["continuity_change_count"] or 0 for item in items) if continuity_eligible else None,
            "excluded_occluded_target_frames": sum(item["excluded_occluded_target_frames"] for item in items),
            "excluded_other_target_frames": sum(item["excluded_other_target_frames"] for item in items),
        })
    return summaries


def main() -> int:
    parser = arguments(__doc__)
    parser.add_argument("--manual", default=Path("experiments/annotations/manual_subjects.json"), type=Path)
    args = parser.parse_args()
    measurement = measurement_provenance("tools.summarize_events", (
        args.plan, args.sources, args.manual, "tools/summarize_events.py",
        "tools/evaluate_learning_rates.py", "tools/prepare_evaluation_clips.py",
        "main.py", "motion_detector.py", "tracker.py", "video.py", "contracts.py",
    ))
    args.work_dir.mkdir(parents=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    events, assets = load_inputs(args)
    manual = read_json(args.manual)["events"]
    paths, references, results = {}, {}, {}
    rows, raw, detailed, provenance = [], [], [], []
    for event in events:
        event_id, source_id = event["event_id"], event["source_id"]
        asset = assets[source_id]
        if source_id not in paths:
            paths[source_id] = verified_source(asset, args.source_root)
            if "annotation_id" in asset:
                ground_truth = assets[asset["annotation_id"]]
                references[source_id] = read_caviar(verified_source(ground_truth, args.source_root))
        clip = prepare_clip(event, asset, paths[source_id], args.work_dir / "clips")
        for distance in (60, 30) if event["condition"] == "overlap" else (60,):
            key = (clip.stem, distance)
            if key not in results:
                results[key] = run_app(clip, args.work_dir, f"{clip.stem}-gate{distance}", -1, distance)
                _, summary = results[key]
                provenance.append({
                    "clip": clip.name, "source_id": source_id, "source_sha256": asset["sha256"],
                    "annotation_sha256": assets[asset["annotation_id"]]["sha256"] if "annotation_id" in asset else None,
                    "clip_sha256": sha256_file(clip), "frame_map_sha256": sha256_file(clip.with_suffix(".csv")),
                    "clip_start_frame": event["clip_start_frame"], "clip_end_frame": event["clip_end_frame"],
                    "frames_processed": summary["frames_processed"], "parameters": summary["parameters"],
                    "versions": summary["versions"], "app_git": summary["git"],
                    "app_argv": summary["argv"],
                })
            frames, _ = results[key]
            expected_count = event["clip_end_frame"] - event["clip_start_frame"] + 1
            if len(frames) != expected_count:
                raise RuntimeError(f"expected {expected_count} frames in {clip}")
            annotation = manual.get(event_id)
            evidence = observe(event, asset, frames, annotation, references.get(source_id))
            row, details = event_result(event, evidence, annotation, distance)
            row["source_file"] = paths[source_id].name
            detailed.append({"event_id": event_id, "max_distance": distance, "subjects": details})
            raw.extend({"max_distance": distance, **item} for item in evidence)
            rows.append(row)
    write_csv(args.output_dir / "event_results.csv", rows)
    write_csv(args.output_dir / "event_frames.csv", raw)
    write_csv(args.output_dir / "event_summary.csv", aggregate(rows))
    write_json(args.output_dir / "event_details.json", detailed)
    write_json(args.output_dir / "event_metadata.json", {
        "measurement": measurement,
        "association": "one-to-one highest IoU >= 0.20 with currently observed boxes",
        "switch": "3 consecutive pre-overlap observations to establish ID, 5 consecutive after separation",
        "continuity": "outside overlap, 3 consecutive observations establish ID, 5 consecutive confirm a different ID",
        "failure": "10 consecutive eligible source frames without a matched observed track",
        "runs": provenance,
    })
    print(f"Measured {len(rows)} event comparisons, {len(raw)} subject-frame records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
