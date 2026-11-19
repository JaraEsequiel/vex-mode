"""Export only the plugin's parts, so an install never carries repo files (docs, evals, .git).

`agy plugin install <dir>` copies the whole folder (design §8.2), so install from this build:
    python3 scripts/build_plugin.py [--ref REF] [--install] <out>
"""
import argparse
import io
import os
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

PLUGIN_PARTS = ("plugin.json", "skills", "agents", "rules", "hooks.json", "hooks", "LICENSES")
EXCLUDED_DIRS = {"__pycache__", "tests"}


def _excluded(rel: Path) -> bool:
    return any(part in EXCLUDED_DIRS for part in rel.parts[:-1])


def _copy_parts(src: Path, out: Path) -> None:
    for part in PLUGIN_PARTS:
        path = src / part
        if path.is_file():
            files = [path]
        elif path.is_dir():
            files = [p for p in path.rglob("*") if p.is_file()]
        else:
            continue
        for f in files:
            rel = f.relative_to(src)
            if _excluded(rel):
                continue
            dest = out / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest)


def build(repo_root: Path, out: Path, ref: str | None = None) -> Path:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    if ref is None:
        _copy_parts(repo_root, out)
        return out
    archive = subprocess.run(
        ["git", "-C", str(repo_root), "archive", "--format=tar", ref],
        check=True, capture_output=True,
    ).stdout
    with tempfile.TemporaryDirectory(prefix="vex-build-") as tmp:
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(tmp, filter="data")
        _copy_parts(Path(tmp), out)
    return out


def agy_command() -> list[str]:
    return shlex.split(os.environ.get("VEX_AGY", "agy"))


def uninstall() -> None:
    subprocess.run([*agy_command(), "plugin", "uninstall", "vex-mode"], capture_output=True)


def install(out: Path) -> None:
    uninstall()
    subprocess.run([*agy_command(), "plugin", "install", str(out)], check=True, capture_output=True)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out", type=Path)
    parser.add_argument("--ref")
    parser.add_argument("--install", action="store_true")
    args = parser.parse_args(argv)
    out = build(Path(__file__).resolve().parents[1], args.out.resolve(), args.ref)
    if args.install:
        install(out)
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
