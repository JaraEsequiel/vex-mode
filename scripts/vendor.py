"""Copy an upstream file byte-identically and record its provenance in vendor.lock.

Usage: python3 scripts/vendor.py <upstream_root> <upstream_path> <dest>
"""
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path


def _head(upstream_root: Path) -> str | None:
    r = subprocess.run(["git", "-C", str(upstream_root), "rev-parse", "HEAD"], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def vendor(upstream_root: Path, upstream_path: str, dest: Path, repo_root: Path) -> dict:
    src = Path(upstream_root) / upstream_path
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    rel = dest.resolve().relative_to(Path(repo_root).resolve()).as_posix()
    lock_path = Path(repo_root) / "vendor.lock"
    lock = json.loads(lock_path.read_text())
    previous = next((f for f in lock["files"] if f["path"] == rel), None)
    item = {
        "path": rel,
        "upstream_path": upstream_path,
        "upstream_sha256": hashlib.sha256(src.read_bytes()).hexdigest(),
        "pending_refs": previous["pending_refs"] if previous else [],
    }
    commit = _head(Path(upstream_root))
    if commit:
        item["upstream_commit"] = commit
    if previous and previous.get("removed_refs"):
        item["removed_refs"] = previous["removed_refs"]
    lock["files"] = [f for f in lock["files"] if f["path"] != rel] + [item]
    lock["files"].sort(key=lambda f: f["path"])
    lock_path.write_text(json.dumps(lock, indent=2) + "\n")
    return item


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    repo = Path(__file__).resolve().parents[1]
    print(json.dumps(vendor(Path(sys.argv[1]), sys.argv[2], repo / sys.argv[3], repo)))
