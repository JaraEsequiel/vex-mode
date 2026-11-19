"""Every file under skills/, rules/ and agents/ is either vendored (with provenance) or declared original."""
import hashlib
import re
from pathlib import Path

from _util import iter_files, load_lock

SHA256 = re.compile(r"^[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")


def run(root: Path) -> list[str]:
    lock = load_lock(root)
    if lock is None:
        return ["vendor.lock: missing"]
    errors = []
    vendored = {}
    for item in lock.get("files", []):
        path = item.get("path", "")
        vendored[path] = item
        if not (root / path).is_file():
            errors.append(f"vendor.lock: listed path does not exist: {path}")
        if not SHA256.match(item.get("upstream_sha256", "")):
            errors.append(f"vendor.lock: {path}: upstream_sha256 is not 64 hex chars")
        if "upstream_commit" in item and not COMMIT.match(str(item["upstream_commit"])):
            errors.append(f"vendor.lock: {path}: upstream_commit is not a 40-hex git sha")
        if not item.get("upstream_path"):
            errors.append(f"vendor.lock: {path}: upstream_path missing")
        local = root / path
        if not item.get("adapted") and local.is_file() and hashlib.sha256(local.read_bytes()).hexdigest() != item.get("upstream_sha256"):
            errors.append(f"{path}: differs from upstream but is not marked \"adapted\": true in vendor.lock")
    original = set(lock.get("original", []))
    for f in iter_files(root):
        rel = f.relative_to(root).as_posix()
        if rel not in vendored and rel not in original:
            errors.append(f"{rel}: not in vendor.lock (vendor it with scripts/vendor.py or list it under 'original')")
    return errors
