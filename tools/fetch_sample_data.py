"""Verify or fetch the exact evaluation assets listed in the source manifest."""

import argparse
from hashlib import file_digest
import json
from pathlib import Path
from shutil import copyfileobj
from tempfile import TemporaryDirectory
from urllib.request import urlopen


def verify(path: Path, asset: dict) -> None:
    size = path.stat().st_size
    if size != asset["size_bytes"]:
        raise ValueError(f"{path}: expected {asset['size_bytes']} bytes, found {size}")
    with path.open("rb") as stream:
        actual = file_digest(stream, "sha256").hexdigest()
    if actual != asset["sha256"]:
        raise ValueError(f"{path}: SHA256 mismatch (found {actual})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="root for manifest paths")
    manifest_path = Path(__file__).resolve().parents[1] / "experiments" / "data_sources.json"
    parser.add_argument("--manifest", type=Path, default=manifest_path)
    parser.add_argument("--asset", action="append", help="select an asset ID, repeatable")
    parser.add_argument("--check", action="store_true", help="verify local files without downloading")
    args = parser.parse_args()

    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        if manifest["schema_version"] != 1:
            raise ValueError("unsupported source manifest version")
        assets = {asset["id"]: asset for asset in manifest["assets"]}
        root = args.root.resolve()
        for asset_id in args.asset or assets:
            asset = assets[asset_id]
            path = (root / asset["path"]).resolve()
            if not path.is_relative_to(root):
                raise ValueError(f"{asset_id}: asset path escapes the specified root")
            if args.check or path.exists():
                verify(path, asset)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                with TemporaryDirectory(dir=path.parent) as staging:
                    candidate = Path(staging) / path.name
                    with urlopen(asset["url"], timeout=45) as response, candidate.open("wb") as stream:
                        copyfileobj(response, stream)
                    verify(candidate, asset)
                    candidate.rename(path)
            print(f"{asset_id}: verified {asset['sha256']}")
    except (KeyError, OSError, ValueError) as error:
        parser.exit(1, f"Source verification failed: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
