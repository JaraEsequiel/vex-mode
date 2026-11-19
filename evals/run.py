"""Run one eval case on the three fixed arms, judge it blind, and write a result (design §8.2).

    python3 evals/run.py <skill> <case> [--base REF] [--variant REF] [--runs N]
    python3 evals/run.py verdict <result.json> <promote|reject|inconclusive> "<synthesis>"

Environment (tests override these): VEX_AGY (agy command), VEX_PLUGIN_HOME (default
~/.gemini/config/plugins), VEX_CACHE (default ~/.cache).
"""
import argparse
import datetime as dt
import fcntl
import json
import os
import random
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(HERE.parent / "checks"))

import build_plugin  # noqa: E402
from _util import skill_tree_sha256  # noqa: E402
from harness import arms as arms_mod  # noqa: E402
from harness import isolation, judge, stats, transcript  # noqa: E402

METRICS = ("compliance", "outcome", "tokens", "duration_s")
VERDICTS = ("promote", "reject", "inconclusive")
DIFF_LIMIT = 20000


class EvalError(Exception):
    pass


def _plugin_home() -> Path:
    return Path(os.environ.get("VEX_PLUGIN_HOME", Path.home() / ".gemini/config/plugins"))


def _cache() -> Path:
    return Path(os.environ.get("VEX_CACHE", Path.home() / ".cache"))


def _git(repo: Path, *args: str, check: bool = True) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=check, capture_output=True, text=True).stdout.strip()


def _commit(repo: Path, ref: str) -> str:
    out = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", ref + "^{commit}"], capture_output=True, text=True)
    if out.returncode != 0:
        raise EvalError(f"cannot resolve ref '{ref}'")
    return out.stdout.strip()


def _fresh_workdir(project: Path, work: Path) -> None:
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(project, work)
    env = dict(os.environ, GIT_AUTHOR_NAME="dev", GIT_AUTHOR_EMAIL="dev@localhost",
               GIT_COMMITTER_NAME="dev", GIT_COMMITTER_EMAIL="dev@localhost")
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "initial"]):
        subprocess.run(["git", "-C", str(work), *args], check=True, capture_output=True, env=env)


def _diff(work: Path) -> str:
    subprocess.run(["git", "-C", str(work), "add", "-A"], capture_output=True)
    text = _git(work, "diff", "--cached", "HEAD", check=False)
    return text if len(text) <= DIFF_LIMIT else text[:DIFF_LIMIT] + "\n[diff truncated]"


def _material(t: transcript.Transcript, diff: str) -> str:
    steps = "\n".join(f"{i}. {s}" for i, s in enumerate(t.steps, 1)) or "(none)"
    return (f"### Final reply\n\n{t.response.strip()}\n\n### Tool calls, in order\n\n{steps}\n\n"
            f"### Diff\n\n```diff\n{diff}\n```")


def _run_candidate(arm, prompt: str, timeout_s: int, work: Path, log: Path) -> transcript.Transcript:
    cmd = [*build_plugin.agy_command(), "-p", prompt, "--model", arm.model,
           "--output-format", "stream-json", "--print-timeout", f"{timeout_s}s"]
    try:
        with open(log, "w") as out:
            subprocess.run(cmd, cwd=work, stdout=out, stderr=subprocess.DEVNULL, timeout=timeout_s + 60)
    except subprocess.TimeoutExpired:
        pass
    return transcript.parse(log.read_text())


def _outcome(case_dir: Path, work: Path) -> int:
    r = subprocess.run([sys.executable, "-I", str(case_dir / "check.py"), str(work)], capture_output=True)
    return 1 if r.returncode == 0 else 0


def run_eval(repo: Path, skill: str, case: str, base: str | None = None,
             variant: str = "HEAD", runs: int | None = None) -> Path:
    repo = repo.resolve()
    case_dir = repo / "evals" / skill / "cases" / case
    cfg = json.loads((case_dir / "case.json").read_text())
    runs = runs or cfg["runs"]
    if _git(repo, "status", "--porcelain", "--", "skills/"):
        raise EvalError("skills/ has uncommitted changes; the variant must be a commit")
    base_sha = _commit(repo, base or _git(repo, "merge-base", "origin/main", "HEAD"))
    variant_sha = _commit(repo, variant)
    arm_list = arms_mod.build_arms(cfg, base_sha, variant_sha)
    prompt = (case_dir / "prompt.md").read_text().strip()
    rubric = (case_dir / "rubric.md").read_text()

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    run_dir = _cache() / "vex-mode" / "runs" / stamp
    (run_dir / "transcripts").mkdir(parents=True)
    lock = open(_cache() / "vex-mode" / "eval.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise EvalError("another eval is running")

    installed = _plugin_home() / "vex-mode"
    backup = run_dir / "installed-backup"
    if installed.is_dir():
        shutil.copytree(installed, backup)
    rng = random.Random()
    slots = list(range(1, len(arm_list) * runs + 1))
    rng.shuffle(slots)
    records: dict[str, dict] = {}
    materials: dict[int, str] = {}
    try:
        for arm in arm_list:
            build = build_plugin.build(repo, run_dir / "build" / arm.label, ref=arm.plugin_ref)
            build_plugin.install(build)
            tree = skill_tree_sha256(build / "skills" / skill)
            if skill_tree_sha256(installed / "skills" / skill) != tree:
                raise EvalError(f"arm {arm.label}: installed skill does not match the build")
            arm_runs = []
            for _ in range(runs):
                slot = slots.pop()
                work = _cache() / "vex-work" / f"{cfg['workdir']}-{slot}"
                _fresh_workdir(case_dir / "project", work)
                log = run_dir / "transcripts" / f"{slot}.ndjson"
                t = _run_candidate(arm, prompt, cfg["timeout_s"], work, log)
                bad = isolation.violations(t, plugin_root=installed, forbidden=[run_dir, repo])
                invalid = "; ".join(bad) or (None if t.status == "SUCCESS" else f"status {t.status}")
                outcome = 0 if invalid else _outcome(case_dir, work)
                if not invalid:
                    materials[slot] = _material(t, _diff(work))
                arm_runs.append({"slot": slot, "status": t.status, "invalid": invalid, "outcome": outcome,
                                 "compliance": 0.0 if invalid else None, "tokens": t.total_tokens,
                                 "duration_s": t.duration_s, "reads": len(t.reads), "commands": len(t.commands)})
            records[arm.label] = {"model": arm.model, "plugin_ref": arm.plugin_ref, "tree_sha256": tree, "runs": arm_runs}
    finally:
        if backup.is_dir():
            build_plugin.install(backup)
        else:
            build_plugin.uninstall()
        lock.close()

    judge_error = None
    if materials:
        order = list(materials)
        rng.shuffle(order)
        labels = {slot: f"R{i}" for i, slot in enumerate(order, 1)}
        (run_dir / "labels.json").write_text(json.dumps({labels[s]: s for s in order}, indent=2))
        prompt_j = judge.build_prompt(rubric, [(labels[s], materials[s]) for s in order])
        (run_dir / "schema.json").write_text(json.dumps(judge.SCHEMA))
        judge_dir = run_dir / "review"
        judge_dir.mkdir()
        out = subprocess.run([*build_plugin.agy_command(), "-p", prompt_j, "--model", cfg["judge_model"],
                              "--output-format", "json", "--json-schema", str(run_dir / "schema.json")],
                             cwd=judge_dir, capture_output=True, text=True)
        (run_dir / "judge.json").write_text(out.stdout)
        verdict, judge_error = judge.parse_output(out.stdout)
        missing = []
        for arm_rec in records.values():
            for r in arm_rec["runs"]:
                if r["slot"] in labels:
                    r["label"] = labels[r["slot"]]
                    r["compliance"] = judge.compliance(verdict or {}, r["label"])
                    if r["compliance"] is None:
                        missing.append(r["label"])
        if missing and not judge_error:
            judge_error = f"judge gave no grade for {', '.join(sorted(missing, key=lambda l: int(l[1:])))}"

    metrics = {}
    for label, rec in records.items():
        m = {}
        for name in METRICS:
            values = [r["tokens" if name == "tokens" else name] for r in rec["runs"]]
            m[name] = None if any(v is None for v in values) else stats.summarize([float(v) for v in values])
        metrics[label] = m
    signals = {}
    for pair, (a, b) in {"B_vs_A": ("A", "B"), "C_vs_A": ("A", "C")}.items():
        s = {}
        for name in METRICS:
            x, y = metrics[a][name], metrics[b][name]
            if x is None or y is None:
                s[name] = None
            elif name in ("tokens", "duration_s"):
                neg = lambda d: {"mean": -d["mean"], "spread": d["spread"]}
                s[name] = stats.signal(neg(x), neg(y))
            else:
                s[name] = stats.signal(x, y)
        signals[pair] = s

    tree = records["B"]["tree_sha256"]
    result = {
        "kind": "eval", "skill": skill, "tree_sha256": tree, "date": dt.date.today().isoformat(),
        "case": case, "run_dir": str(run_dir), "arms": records,
        "judge": {"model": cfg["judge_model"], "error": judge_error},
        "metrics": metrics, "signals": signals, "verdict": None, "synthesis": None,
    }
    path = repo / "evals" / skill / "results" / f"{result['date']}-{tree[:12]}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(f"run dir: {run_dir}\nresult: {path}")
    return path


def set_verdict(path: Path, verdict: str, synthesis: str) -> None:
    if verdict not in VERDICTS:
        raise EvalError(f"verdict must be one of {VERDICTS}")
    if not synthesis.strip():
        raise EvalError("synthesis is required")
    result = json.loads(path.read_text())
    result["verdict"], result["synthesis"] = verdict, synthesis
    path.write_text(json.dumps(result, indent=2) + "\n")


def main(argv: list[str]) -> int:
    try:
        if argv[:1] == ["verdict"]:
            if len(argv) != 4:
                raise EvalError('usage: verdict <result.json> <promote|reject|inconclusive> "<synthesis>"')
            set_verdict(Path(argv[1]), argv[2], argv[3])
            return 0
        parser = argparse.ArgumentParser(description="Run one eval case on the three fixed arms.")
        parser.add_argument("skill")
        parser.add_argument("case")
        parser.add_argument("--base")
        parser.add_argument("--variant", default="HEAD")
        parser.add_argument("--runs", type=int)
        args = parser.parse_args(argv)
        run_eval(HERE.parent, args.skill, args.case, args.base, args.variant, args.runs)
        return 0
    except (EvalError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
