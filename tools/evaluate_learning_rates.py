"""Compare MOG2 learning rates on identical, lossless evaluation clips."""

import argparse
import csv
from hashlib import file_digest
import json
from pathlib import Path
import subprocess
import sys


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, content) -> None:
    path.write_text(json.dumps(content, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows) -> None:
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)


def sha256_file(path: Path) -> str:
    with path.open("rb") as content:
        return file_digest(content, "sha256").hexdigest()


def measurement_provenance(module: str, inputs):
    def git(*arguments):
        return subprocess.check_output(["git", *arguments], text=True).strip()

    return {
        "revision": git("rev-parse", "HEAD"),
        "dirty_at_start": bool(git("--no-optional-locks", "status", "--porcelain")),
        "module": module,
        "argv": sys.orig_argv,
        "input_hashes": {Path(path).as_posix(): sha256_file(Path(path)) for path in inputs},
    }


def command(arguments) -> None:
    result = subprocess.run(
        [sys.executable, *map(str, arguments)], capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    if result.returncode:
        raise RuntimeError(f"{' '.join(map(str, arguments))}\n{result.stdout}{result.stderr}")


def verified_source(asset, source_root: Path) -> Path:
    path = source_root / asset["path"]
    if sha256_file(path) != asset["sha256"]:
        raise ValueError(f"source hash mismatch: {path}")
    return path


def prepare_clip(event, asset, source: Path, clip_dir: Path) -> Path:
    start, end = event["clip_start_frame"], event["clip_end_frame"]
    name = f"{asset['id']}-{start}-{end}"
    clip, mapping = clip_dir / f"{name}.avi", clip_dir / f"{name}.csv"
    if not clip.exists() or not mapping.exists():
        arguments = [
            "-m", "tools.prepare_evaluation_clips", "--source", source,
            "--start", start, "--end", end, "--output", clip, "--mapping", mapping,
        ]
        if asset["role"] == "frame_archive":
            arguments.extend(["--member-pattern", asset["member_pattern"],
                              "--fps", event["archive_playback_fps"]])
        command(arguments)
    return clip


def run_app(clip: Path, work_dir: Path, name: str, rate: float, distance: float):
    run = work_dir / name
    run.mkdir(parents=True)
    log, summary_path = run / "frames.jsonl", run / "summary.json"
    app_arguments = [
        "main.py", "--video", clip, "--headless", "--frame-log", log,
        "--summary-json", summary_path, "--learning-rate", rate,
        "--min-area", 500, "--kernel-size", 5, "--max-missed", 5, "--max-distance", distance,
    ]
    command(app_arguments)
    summary = read_json(summary_path)
    summary["argv"] = [sys.executable, *map(str, app_arguments)]
    with log.open(encoding="utf-8") as frames_file:
        frames = [json.loads(line) for line in frames_file]
    if summary["status"] != "completed" or len(frames) != summary["frames_processed"]:
        raise RuntimeError(f"incomplete app run: {run}")
    for index, frame in enumerate(frames):
        if frame["frame_index"] != index:
            raise RuntimeError(f"frame order differs from source at index {index}")
    return frames, summary


def sustained_quiet(frames, first: int, *, threshold=0.10, consecutive=5):
    count = 0
    for offset, frame in enumerate(frames[first:]):
        count = count + 1 if frame["foreground_fraction"] <= threshold else 0
        if count == consecutive:
            return offset + 1 - consecutive
    return None


def load_inputs(args):
    events = read_json(args.plan)["events"]
    assets = {asset["id"]: asset for asset in read_json(args.sources)["assets"]}
    return events, assets


def arguments(description):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--plan", default=Path("experiments/event_plan.json"), type=Path)
    parser.add_argument("--sources", default=Path("experiments/data_sources.json"), type=Path)
    return parser


def main() -> int:
    parser = arguments(__doc__)
    parser.add_argument("--rates", nargs="+", type=float, default=[-1.0, 0.005, 0.05])
    args = parser.parse_args()
    if len(set(args.rates)) < 3 or any(rate != -1 and not 0 <= rate <= 1 for rate in args.rates):
        parser.error("choose three distinct rates, each -1 or within [0, 1]")
    measurement = measurement_provenance("tools.evaluate_learning_rates", (
        args.plan, args.sources, "tools/evaluate_learning_rates.py",
        "tools/prepare_evaluation_clips.py", "main.py", "motion_detector.py", "tracker.py",
        "video.py", "contracts.py",
    ))
    args.work_dir.mkdir(parents=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    events, assets = load_inputs(args)
    comparisons = {"overlap-05", "stop-04", "illumination-02"}
    rows, raw, provenance = [], [], []
    for event in events:
        event_id = event["event_id"]
        if event_id not in comparisons:
            continue
        asset = assets[event["source_id"]]
        source = verified_source(asset, args.source_root)
        clip = prepare_clip(event, asset, source, args.work_dir / "clips")
        offset = event["clip_start_frame"]
        anchor = event["anchor_frame"] - offset
        for rate in args.rates:
            frames, summary = run_app(clip, args.work_dir, f"{event_id}-{rate}", rate, 60)
            if len(frames) != event["clip_end_frame"] - offset + 1:
                raise RuntimeError(f"{event_id} did not process the complete clip")
            tail = frames[anchor:]
            rows.append({
                "event_id": event_id, "source_id": asset["id"], "learning_rate": rate,
                "clip_start": offset, "clip_end": event["clip_end_frame"], "frames": len(frames),
                "peak_foreground_after_anchor": max(f["foreground_fraction"] for f in tail),
                "mean_foreground_after_anchor": sum(f["foreground_fraction"] for f in tail) / len(tail),
                "first_quiet_offset_frames": sustained_quiet(frames, anchor),
                "source_fps": asset["source_fps"],
            })
            provenance.append({
                "event_id": event_id, "learning_rate": rate, "source_sha256": asset["sha256"],
                "clip_sha256": sha256_file(clip), "frame_map_sha256": sha256_file(clip.with_suffix(".csv")),
                "parameters": summary["parameters"], "versions": summary["versions"],
                "frames_processed": summary["frames_processed"], "app_git": summary["git"],
                "app_argv": summary["argv"],
            })
            for frame in frames:
                raw.append({
                    "event_id": event_id, "learning_rate": rate,
                    "source_frame": offset + frame["frame_index"],
                    "foreground_fraction": frame["foreground_fraction"],
                    "detections": len(frame["detections"]),
                    "observed_tracks": sum(t["observed_this_frame"] for t in frame["tracks"]),
                })
    write_csv(args.output_dir / "learning_rates.csv", rows)
    write_csv(args.output_dir / "learning_rate_frames.csv", raw)
    write_json(args.output_dir / "learning_rate_metadata.json", {
        "measurement": measurement,
        "quiet_definition": "first five consecutive clean foreground fractions at or below 0.10",
        "runs": provenance,
    })
    print(f"Measured {len(rows)} runs and {len(raw)} frames")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
