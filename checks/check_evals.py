"""Eval cases are blinded, results are well-formed, and every changed skill has a result for its tree hash.

Design §8.2. The base for "changed" is $VEX_BASE_REF (default origin/main).
"""
import json
import os
import re
import subprocess
from pathlib import Path

from _util import banned_hits, model_family, skill_tree_sha256

NOT_SKILLS = {"harness", "tests", "__pycache__"}
CASE_FILES = ("prompt.md", "rubric.md", "check.py", "case.json")
ARMS = ("A", "B", "C")
METRICS = ("compliance", "outcome", "tokens", "duration_s")
VERDICTS = ("promote", "reject", "inconclusive")
SHA = re.compile(r"^[0-9a-f]{64}$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SLUG = re.compile(r"^[a-z0-9-]+$")


def _skill_dirs(root: Path) -> list[Path]:
    evals = root / "evals"
    if not evals.is_dir():
        return []
    return sorted(d for d in evals.iterdir() if d.is_dir() and d.name not in NOT_SKILLS)


def _case_errors(case: Path, rel: str) -> list[str]:
    errors = [f"{rel}: missing {name}" for name in CASE_FILES if not (case / name).is_file()]
    if not (case / "project").is_dir():
        errors.append(f"{rel}: missing project/")
    prompt = case / "prompt.md"
    if prompt.is_file() and (hits := banned_hits(prompt.read_text())):
        errors.append(f"{rel}/prompt.md: words a blinded agent must not see: {hits}")
    project = case / "project"
    if project.is_dir():
        for p in sorted(project.rglob("*")):
            prel = p.relative_to(project).as_posix()
            if hits := banned_hits(prel):
                errors.append(f"{rel}/project/{prel}: banned word in path: {hits}")
            if p.is_file() and (hits := banned_hits(p.read_text(errors="replace"))):
                errors.append(f"{rel}/project/{prel}: banned word in content: {hits}")
    cfg_path = case / "case.json"
    if cfg_path.is_file():
        try:
            cfg = json.loads(cfg_path.read_text())
        except json.JSONDecodeError as e:
            return errors + [f"{rel}/case.json: invalid JSON ({e})"]
        if not (isinstance(cfg.get("runs"), int) and cfg["runs"] >= 1):
            errors.append(f"{rel}/case.json: runs must be an integer >= 1")
        if not (isinstance(cfg.get("timeout_s"), int) and cfg["timeout_s"] > 0):
            errors.append(f"{rel}/case.json: timeout_s must be a positive integer")
        for key in ("candidate_model", "upgrade_model", "judge_model"):
            if not (isinstance(cfg.get(key), str) and cfg[key]):
                errors.append(f"{rel}/case.json: {key} is required")
        workdir = cfg.get("workdir")
        if not (isinstance(workdir, str) and SLUG.match(workdir)):
            errors.append(f"{rel}/case.json: workdir must match {SLUG.pattern}")
        elif hits := banned_hits(workdir):
            errors.append(f"{rel}/case.json: workdir has banned words {hits}")
        models = [cfg.get(k) for k in ("candidate_model", "upgrade_model", "judge_model")]
        if all(isinstance(m, str) and m for m in models):
            judge = model_family(models[2])
            if judge in {model_family(models[0]), model_family(models[1])}:
                errors.append(f"{rel}/case.json: judge family '{judge}' must differ from every candidate's family")
    return errors


def _result_errors(result: dict, skill: str, rel: str) -> list[str]:
    errors = []
    kind = result.get("kind")
    if kind not in ("eval", "waiver"):
        return [f"{rel}: kind must be 'eval' or 'waiver'"]
    if result.get("skill") != skill:
        errors.append(f"{rel}: skill must be '{skill}'")
    if not SHA.match(str(result.get("tree_sha256", ""))):
        errors.append(f"{rel}: tree_sha256 must be 64 hex chars")
    if not DATE.match(str(result.get("date", ""))):
        errors.append(f"{rel}: date must be YYYY-MM-DD")
    if kind == "waiver":
        if not (isinstance(result.get("reason"), str) and result["reason"].strip()):
            errors.append(f"{rel}: a waiver needs a reason")
        return errors
    arms = result.get("arms")
    if not (isinstance(arms, dict) and sorted(arms) == list(ARMS)):
        errors.append(f"{rel}: arms must be exactly {list(ARMS)}")
    judge = result.get("judge") or {}
    if judge.get("error"):
        errors.append(f"{rel}: judge failed ({judge['error']}); rerun the eval or add a waiver")
    metrics = result.get("metrics") or {}
    for arm in ARMS:
        for m in METRICS:
            value = (metrics.get(arm) or {}).get(m)
            if not (isinstance(value, dict) and all(k in value for k in ("mean", "min", "max", "spread"))):
                errors.append(f"{rel}: metrics.{arm}.{m} is missing")
    if result.get("verdict") not in VERDICTS:
        errors.append(f"{rel}: no verdict; read every output, then run `python3 evals/run.py verdict`")
    if not (isinstance(result.get("synthesis"), str) and result["synthesis"].strip()):
        errors.append(f"{rel}: synthesis is required")
    return errors


def _load_results(skill_dir: Path) -> list[tuple[Path, dict | None]]:
    out = []
    for p in sorted((skill_dir / "results").glob("*.json")):
        try:
            out.append((p, json.loads(p.read_text())))
        except json.JSONDecodeError:
            out.append((p, None))
    return out


def layout_errors(root: Path) -> list[str]:
    errors = []
    for d in _skill_dirs(root):
        rel = d.relative_to(root).as_posix()
        if not (root / "skills" / d.name).is_dir():
            errors.append(f"{rel}: no matching skills/{d.name}")
        for case in sorted(p for p in (d / "cases").glob("*") if p.is_dir()):
            errors += _case_errors(case, case.relative_to(root).as_posix())
        for path, result in _load_results(d):
            prel = path.relative_to(root).as_posix()
            if result is None:
                errors.append(f"{prel}: invalid JSON")
            else:
                errors += _result_errors(result, d.name, prel)
    return errors


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)


def changed_skills(root: Path, base: str) -> set[str]:
    merge_base = _git(root, "merge-base", base, "HEAD").stdout.strip()
    diff = _git(root, "diff", "--name-only", merge_base, "--", "skills/").stdout.split()
    untracked = _git(root, "ls-files", "--others", "--exclude-standard", "--", "skills/").stdout.split()
    names = {p.split("/")[1] for p in diff + untracked if p.count("/") >= 2}
    return {n for n in names if (root / "skills" / n).is_dir()}


def policy_errors(root: Path, base: str) -> list[str]:
    if _git(root, "rev-parse", "--verify", "--quiet", base + "^{commit}").returncode != 0:
        return [f"cannot resolve base ref '{base}'; fetch it or set VEX_BASE_REF"]
    errors = []
    for skill in sorted(changed_skills(root, base)):
        sha = skill_tree_sha256(root / "skills" / skill)
        ok = [
            p for p, r in _load_results(root / "evals" / skill)
            if r is not None and r.get("tree_sha256") == sha and not _result_errors(r, skill, "")
        ]
        if not ok:
            errors.append(
                f"skills/{skill} changed but evals/{skill}/results/ has no valid result for tree {sha[:12]}; "
                f"run `python3 evals/run.py {skill} <case>` or add a waiver"
            )
    return errors


def run(root: Path) -> list[str]:
    base = os.environ.get("VEX_BASE_REF", "origin/main")
    return layout_errors(root) + policy_errors(root, base)
