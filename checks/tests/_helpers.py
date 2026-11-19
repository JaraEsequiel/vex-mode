import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SHA = "a" * 64


def make_repo(files: dict, lock: dict | None = None) -> Path:
    root = Path(tempfile.mkdtemp(prefix="vexcheck-"))
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    if lock is not None:
        (root / "vendor.lock").write_text(json.dumps(lock))
    return root


def lock(files=(), original=()):
    return {
        "upstream": {"repo": "https://github.com/cursor/plugins", "commit": "35a9094"},
        "files": list(files),
        "original": list(original),
    }


def entry(path, sha=SHA, pending_refs=()):
    return {"path": path, "upstream_path": "pstack/" + path, "upstream_sha256": sha, "pending_refs": list(pending_refs)}
