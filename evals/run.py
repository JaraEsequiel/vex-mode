"""Run one eval case on the three fixed arms, judge it blind, and write a result (design §8.2).

    python3 evals/run.py <skill> <case> [--base REF] [--variant REF] [--runs N]
    python3 evals/run.py rejudge <result.json>
    python3 evals/run.py restore    (after an eval that was killed before it could restore the plugin)
    python3 evals/run.py verdict <result.json> <promote|reject|inconclusive> "<synthesis>"

Environment (tests override these): VEX_AGY (agy command), VEX_PLUGIN_HOME (default
~/.gemini/config/plugins), VEX_CACHE (default ~/.cache).
"""
import argparse
import contextlib
import datetime as dt
import fcntl
import json
import os
import random
import secrets
import shutil
import signal
import subprocess
import sys
import time
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
JUDGE_TIMEOUT_S = 1800


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
    """Everything the run changed since the project was planted, committed or not."""
    root = _git(work, "rev-list", "--max-parents=0", "HEAD", check=False).splitlines()
    subprocess.run(["git", "-C", str(work), "add", "-A"], capture_output=True)
    text = _git(work, "diff", "--cached", root[-1] if root else "HEAD", "--", ".", ":(exclude)**/__pycache__/**",
                ":(exclude)__pycache__/**", check=False)
    return text if len(text) <= DIFF_LIMIT else text[:DIFF_LIMIT] + "\n[diff truncated]"


def _material(t: transcript.Transcript, diff: str) -> str:
    steps = "\n".join(f"{i}. {s}" for i, s in enumerate(t.steps, 1)) or "(none)"
    return (f"### Final reply\n\n{t.response.strip()}\n\n### Tool calls, in order\n\n{steps}\n\n"
            f"### Diff\n\n```diff\n{diff}\n```")


def _run_candidate(arm, prompt: str, timeout_s: int, work: Path, log: Path) -> tuple[transcript.Transcript, float]:
    cmd = [*build_plugin.agy_command(), "-p", prompt, "--model", arm.model,
           "--output-format", "stream-json", "--print-timeout", f"{timeout_s}s"]
    start = time.monotonic()
    try:
        with open(log, "w") as out:
            subprocess.run(cmd, cwd=work, stdout=out, stderr=subprocess.DEVNULL, timeout=timeout_s + 60)
    except subprocess.TimeoutExpired:
        pass
    return transcript.parse(log.read_text()), time.monotonic() - start


def _outcome(case_dir: Path, work: Path, record: Path) -> int:
    r = subprocess.run([sys.executable, "-I", str(case_dir / "check.py"), str(work)], capture_output=True, text=True)
    record.write_text(f"exit {r.returncode}\n{r.stdout}{r.stderr}")
    return 1 if r.returncode == 0 else 0


JUDGE_INLINE_MAX = 100_000


def _judge(records: dict, materials: dict[int, str], rubric: str, judge_model: str, run_dir: Path,
           rng: random.Random) -> str | None:
    """One blinded pass over every valid run; sets each run's label and compliance. Returns the judge error.
    A run whose grade is missing, duplicated or has the wrong number of criteria gets compliance None."""
    if not materials:
        return None
    order = list(materials)
    rng.shuffle(order)
    labels = {slot: f"R{i}" for i, slot in enumerate(order, 1)}
    prompt = judge.build_prompt(rubric, [(labels[s], materials[s]) for s in order])
    (run_dir / "judge-prompt.md").write_text(prompt)
    (run_dir / "schema.json").write_text(json.dumps(judge.SCHEMA))
    judge_dir = run_dir / "review"
    judge_dir.mkdir(exist_ok=True)
    if len(prompt.encode()) > JUDGE_INLINE_MAX:  # one argv string is capped at 128 KiB on Linux
        prompt = (f"Read the file {run_dir / 'judge-prompt.md'} in full and do exactly what it asks. "
                  "Your answer must follow the JSON schema you were given.")
    launch_error = None
    try:
        out = subprocess.run([*build_plugin.agy_command(), "-p", prompt, "--model", judge_model,
                              "--output-format", "json", "--json-schema", str(run_dir / "schema.json")],
                             cwd=judge_dir, capture_output=True, text=True, timeout=JUDGE_TIMEOUT_S)
        stdout = out.stdout
    except subprocess.TimeoutExpired:
        stdout = ""
    except OSError as e:
        stdout, launch_error = "", f"could not start the judge: {e}"
    (run_dir / "judge.json").write_text(stdout)
    (run_dir / "labels.json").write_text(json.dumps({labels[s]: s for s in order}, indent=2))
    verdict, error = judge.parse_output(stdout) if stdout else (None, launch_error or "judge timed out or printed nothing")
    expected = [labels[s] for s in order]
    n = judge.criteria_count(rubric)
    problems = judge.label_problems(verdict or {"runs": []}, expected, n)
    for rec in records.values():
        for r in rec["runs"]:
            if r["slot"] in labels:
                r["label"] = labels[r["slot"]]
                bad = verdict is None or r["label"] in problems
                r["compliance"] = None if bad else judge.compliance(verdict, r["label"])
    if error is None:
        error = judge.check_verdict(verdict, expected, n)
    return error


def _score(records: dict) -> tuple[dict, dict]:
    metrics = {}
    for label, rec in records.items():
        m = {}
        for name in METRICS:
            values = [r[name] for r in rec["runs"]]
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
                s[name] = stats.signal({"mean": -x["mean"], "spread": x["spread"]},
                                       {"mean": -y["mean"], "spread": y["spread"]})
            else:
                s[name] = stats.signal(x, y)
        signals[pair] = s
    return metrics, signals


def rejudge(path: Path) -> None:
    """Judge an existing result again from its run dir (transcripts and saved diffs), without new runs."""
    result = json.loads(path.read_text())
    repo = path.resolve().parents[3]
    case_dir = repo / "evals" / result["skill"] / "cases" / result["case"]
    cfg = json.loads((case_dir / "case.json").read_text())
    run_dir = Path(result["run_dir"])
    materials = {}
    for rec in result["arms"].values():
        for r in rec["runs"]:
            r.pop("label", None)
            if r["invalid"]:
                continue
            diff = run_dir / "diffs" / f"{r['slot']}.diff"
            if not diff.is_file():
                raise EvalError(f"{diff} is missing; rerun the eval")
            t = transcript.parse((run_dir / "transcripts" / f"{r['slot']}.ndjson").read_text())
            materials[r["slot"]] = _material(t, diff.read_text())
            r["compliance"] = None
    with _locked():
        error = _judge(result["arms"], materials, (case_dir / "rubric.md").read_text(), cfg["judge_model"],
                       run_dir, random.Random())
    result["judge"] = {"model": cfg["judge_model"], "error": error}
    result["metrics"], result["signals"] = _score(result["arms"])
    result["verdict"], result["synthesis"] = None, None
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(f"result: {path}")


def _marker() -> Path:
    return _cache() / "vex-mode" / "restore-pending"


@contextlib.contextmanager
def _locked():
    (_cache() / "vex-mode").mkdir(parents=True, exist_ok=True)
    lock = open(_cache() / "vex-mode" / "eval.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        raise EvalError("another eval is running")
    try:
        yield
    finally:
        lock.close()


def _raise_interrupt(signum, frame):
    raise KeyboardInterrupt(f"signal {signum}")


def restore() -> None:
    """Reinstall the plugin a previous eval backed up, then clear the pending marker."""
    marker = _marker()
    if not marker.exists():
        print("nothing to restore")
        return
    target = marker.read_text().strip()
    saved = {sig: signal.signal(sig, signal.SIG_IGN) for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)}
    try:
        if target == "-":
            build_plugin.uninstall()
        else:
            build_plugin.install(Path(target))
    except Exception:
        print(f"error: restoring the plugin failed; reinstall it by hand from {target}", file=sys.stderr)
        raise
    finally:
        for sig, handler in saved.items():
            signal.signal(sig, handler)
    marker.unlink()


def run_eval(repo: Path, skill: str, case: str, base: str | None = None,
             variant: str = "HEAD", runs: int | None = None) -> Path:
    repo = repo.resolve()
    case_dir = repo / "evals" / skill / "cases" / case
    cfg = json.loads((case_dir / "case.json").read_text())
    runs = runs or cfg["runs"]
    if _marker().exists():
        raise EvalError(f"a previous eval did not restore the plugin; run `python3 evals/run.py restore` first")
    if _git(repo, "status", "--porcelain", "--", "skills/"):
        raise EvalError("skills/ has uncommitted changes; the variant must be a commit")
    if base is None:
        base = _git(repo, "merge-base", "origin/main", "HEAD", check=False)
        if not base:
            raise EvalError("no merge base with origin/main; pass --base")
    arm_list = arms_mod.build_arms(cfg, _commit(repo, base), _commit(repo, variant))
    prompt = (case_dir / "prompt.md").read_text().strip()
    rubric = (case_dir / "rubric.md").read_text()

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    run_dir = _cache() / "vex-mode" / "runs" / stamp
    for sub in ("transcripts", "diffs", "checks"):
        (run_dir / sub).mkdir(parents=True)
    builds = {arm.label: build_plugin.build(repo, run_dir / "build" / arm.label, ref=arm.plugin_ref) for arm in arm_list}
    trees = {label: skill_tree_sha256(b / "skills" / skill) for label, b in builds.items()}
    path = repo / "evals" / skill / "results" / f"{dt.date.today().isoformat()}-{case}-{trees['B'][:12]}.json"
    if path.exists():
        raise EvalError(f"{path} already exists; delete it to run this eval again")

    installed = _plugin_home() / "vex-mode"
    work_root = _cache() / "vex-work"
    rng = random.Random()
    slots = list(range(1, len(arm_list) * runs + 1))
    rng.shuffle(slots)
    records: dict[str, dict] = {}
    materials: dict[int, str] = {}
    with _locked():
        backup = run_dir / "installed-backup"
        if installed.is_dir():
            shutil.copytree(installed, backup)
        _marker().write_text(str(backup) if backup.is_dir() else "-")
        saved = {sig: signal.signal(sig, _raise_interrupt) for sig in (signal.SIGTERM, signal.SIGHUP)}
        try:
            for arm in arm_list:
                build_plugin.install(builds[arm.label])
                if skill_tree_sha256(installed / "skills" / skill) != trees[arm.label]:
                    raise EvalError(f"arm {arm.label}: installed skill does not match the build")
                arm_runs = []
                for _ in range(runs):
                    slot = slots.pop()
                    private = work_root / secrets.token_hex(4)
                    work = private / cfg["workdir"]
                    _fresh_workdir(case_dir / "project", work)
                    try:
                        t, wall = _run_candidate(arm, prompt, cfg["timeout_s"], work,
                                                 run_dir / "transcripts" / f"{slot}.ndjson")
                        bad = isolation.violations(t, plugin_root=installed, forbidden=[_cache() / "vex-mode", repo],
                                                   workdir=work, work_root=work_root, home=Path.home())
                        invalid = "; ".join(bad) or (None if t.status == "SUCCESS" else f"status {t.status}")
                        diff = _diff(work)
                        (run_dir / "diffs" / f"{slot}.diff").write_text(diff)
                        outcome = _outcome(case_dir, work, run_dir / "checks" / f"{slot}.txt")
                        if invalid:
                            outcome = 0
                        else:
                            materials[slot] = _material(t, diff)
                    finally:
                        shutil.rmtree(private, ignore_errors=True)
                    finished = t.status == "SUCCESS"
                    arm_runs.append({"slot": slot, "status": t.status, "invalid": invalid, "outcome": outcome,
                                     "compliance": 0.0 if invalid else None,
                                     "tokens": t.total_tokens if finished else t.step_tokens,
                                     "duration_s": t.duration_s if finished else wall,
                                     "reads": len(t.reads), "commands": len(t.commands)})
                records[arm.label] = {"model": arm.model, "plugin_ref": arm.plugin_ref,
                                      "tree_sha256": trees[arm.label], "runs": arm_runs}
        finally:
            for sig, handler in saved.items():
                signal.signal(sig, handler)
            restore()

        judge_error = _judge(records, materials, rubric, cfg["judge_model"], run_dir, rng)
    metrics, signals = _score(records)
    result = {
        "kind": "eval", "skill": skill, "tree_sha256": trees["B"], "date": dt.date.today().isoformat(),
        "case": case, "run_dir": str(run_dir), "arms": records,
        "judge": {"model": cfg["judge_model"], "error": judge_error},
        "metrics": metrics, "signals": signals, "verdict": None, "synthesis": None,
    }
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
        if argv[:1] == ["restore"]:
            restore()
            return 0
        if argv[:1] == ["rejudge"]:
            if len(argv) != 2:
                raise EvalError("usage: rejudge <result.json>")
            rejudge(Path(argv[1]))
            return 0
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
