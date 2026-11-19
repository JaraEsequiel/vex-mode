"""Compare every file copied from pstack (vendor.lock) with the current upstream (design §6.6).

    python3 scripts/upstream_drift.py [--fetch | --upstream PATH] [--fail] [--gh-issue]
    python3 scripts/upstream_drift.py [--fetch | --upstream PATH] --accept skills/<x>/SKILL.md

A changed unadapted file is re-copied with scripts/vendor.py. A changed adapted file must not be re-copied:
re-apply the upstream diff shown in the report onto our adaptation, then --accept it.
"""
import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CACHE = Path(os.environ.get("VEX_UPSTREAM", Path.home() / ".cache/vex-mode/upstream"))
ISSUE_TITLE = "pstack upstream drift"
ISSUE_LABEL = "upstream-drift"


class DriftError(Exception):
    pass


def _git(path: Path, *args: str, check: bool = True) -> str:
    r = subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise DriftError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout


def _lock(repo: Path) -> dict:
    return json.loads((repo / "vendor.lock").read_text())


def fetch(url: str, dest: Path = CACHE) -> Path:
    if (dest / ".git").is_dir():
        _git(dest, "fetch", "-q", "origin")
        _git(dest, "reset", "-q", "--hard", "origin/HEAD")
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(["git", "clone", "-q", url, str(dest)], capture_output=True, text=True)
        if r.returncode != 0:
            raise DriftError(f"git clone {url} failed: {r.stderr.strip()}")
    return dest


def report(repo: Path, upstream: Path) -> list[dict]:
    lock = _lock(repo)
    default = (lock.get("upstream") or {}).get("commit")
    entries = []
    for item in lock.get("files", []):
        src = upstream / item["upstream_path"]
        frm = item.get("upstream_commit") or default
        e = {"path": item["path"], "upstream_path": item["upstream_path"], "adapted": bool(item.get("adapted")),
             "from_commit": frm, "diff": ""}
        if not src.is_file():
            e["status"] = "deleted"
        elif hashlib.sha256(src.read_bytes()).hexdigest() == item["upstream_sha256"]:
            e["status"] = "same"
        else:
            e["status"] = "changed"
            e["diff"] = _git(upstream, "diff", frm, "HEAD", "--", item["upstream_path"], check=False)
        entries.append(e)
    return entries


def render(entries: list[dict], head: str) -> str:
    drift = [e for e in entries if e["status"] != "same"]
    lines = [f"# {ISSUE_TITLE}", "",
             f"Upstream HEAD `{head[:12]}`: {len(drift)} of {len(entries)} copied files changed upstream.", ""]
    if not drift:
        return "\n".join(lines + ["No drift."]) + "\n"
    for e in drift:
        lines += [f"### `{e['path']}` ({'adapted' if e['adapted'] else 'verbatim'})", "",
                  f"Upstream: `{e['upstream_path']}`, ours from `{(e['from_commit'] or '?')[:12]}`.", ""]
        if e["status"] == "deleted":
            lines += ["The file was deleted upstream. Decide whether to keep our copy as `original` or drop it.", ""]
        elif e["adapted"]:
            lines += ["Do not re-copy it: re-apply this upstream change onto our adaptation where it applies, "
                      f"then `python3 scripts/upstream_drift.py --fetch --accept {e['path']}`.", "",
                      "```diff", e["diff"].rstrip(), "```", ""]
        else:
            lines += [f"Re-copy it: `python3 scripts/vendor.py <upstream> {e['upstream_path']} {e['path']}` "
                      "(commit `vendor: …`), then re-check its references.", "",
                      "```diff", e["diff"].rstrip(), "```", ""]
    return "\n".join(lines) + "\n"


def accept(repo: Path, upstream: Path, path: str) -> None:
    """Record that `path` is reconciled with the current upstream: new hash and commit."""
    lock = _lock(repo)
    item = next((f for f in lock["files"] if f["path"] == path), None)
    if item is None:
        raise DriftError(f"{path} is not in vendor.lock")
    data = (upstream / item["upstream_path"]).read_bytes()
    if not item.get("adapted") and (repo / path).read_bytes() != data:
        raise DriftError(f"{path} is verbatim but differs from upstream; re-copy it with scripts/vendor.py")
    item["upstream_sha256"] = hashlib.sha256(data).hexdigest()
    item["upstream_commit"] = _git(upstream, "rev-parse", "HEAD").strip()
    (repo / "vendor.lock").write_text(json.dumps(lock, indent=2) + "\n")


def _gh(*args: str) -> str:
    cmd = [*shlex.split(os.environ.get("VEX_GH", "gh")), *args]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise DriftError(f"{' '.join(args[:2])} failed: {r.stderr.strip()}")
    return r.stdout


def sync_issue(body: str, drift: bool) -> None:
    """Keep one open issue in step with the report: create, update or close it."""
    found = json.loads(_gh("issue", "list", "--state", "open", "--label", ISSUE_LABEL,
                           "--json", "number,title") or "[]")
    issue = next((i for i in found if i.get("title") == ISSUE_TITLE), None)
    if drift and issue:
        _gh("issue", "edit", str(issue["number"]), "--body", body)
    elif drift:
        _gh("label", "create", ISSUE_LABEL, "--force", "--description", "pstack files changed upstream")
        _gh("issue", "create", "--title", ISSUE_TITLE, "--label", ISSUE_LABEL, "--body", body)
    elif issue:
        _gh("issue", "close", str(issue["number"]), "--comment", "No drift left: every copied file matches upstream.")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", type=Path, default=REPO)
    src = parser.add_mutually_exclusive_group()
    src.add_argument("--upstream", type=Path)
    src.add_argument("--fetch", action="store_true")
    parser.add_argument("--fail", action="store_true")
    parser.add_argument("--accept")
    parser.add_argument("--gh-issue", action="store_true")
    args = parser.parse_args(argv)
    try:
        upstream = args.upstream or (fetch(_lock(args.repo)["upstream"]["repo"]) if args.fetch else CACHE)
        if args.accept:
            accept(args.repo, upstream, args.accept)
            print(f"accepted {args.accept}")
            return 0
        entries = report(args.repo, upstream)
        text = render(entries, _git(upstream, "rev-parse", "HEAD").strip())
        drift = any(e["status"] != "same" for e in entries)
        print(text)
        if args.gh_issue:
            sync_issue(text, drift)
    except DriftError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 1 if (args.fail and drift) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
