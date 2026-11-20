"""Run one eval case on the three fixed arms, judge it blind, and write a result (design §8.2).

    python3 evals/run.py <skill> <case> [--base REF] [--variant REF] [--runs N] [--harness agy|claude-code]
    python3 evals/run.py calibrate <skill> <case> [--base REF] [--runs N]   (Claude Code: plugin vs no plugin)
    python3 evals/run.py rejudge <result.json>
    python3 evals/run.py restore    (after an eval that was killed before it could restore the plugin)
    python3 evals/run.py verdict <result.json> <promote|reject|inconclusive> "<synthesis>"

Environment (tests override these): VEX_AGY (agy command), VEX_CLAUDE (claude command), VEX_PLUGIN_HOME
(default ~/.gemini/config/plugins), VEX_CACHE (default ~/.cache).

A case runs on agy unless `--harness` or its case.json `"harness"` says `claude-code`. A case that runs on
both keeps its Claude Code models under `"claude_code": {"candidate_model": ..., "upgrade_model": ...}`. On Claude Code each arm loads its
own build with `--plugin-dir` and `--setting-sources project`, so nothing is installed and the user's
plugins, skills, CLAUDE.md and MCP servers stay out (docs/decisions/2026-11-19-claude-code-probes.md).
"""
import argparse
import contextlib
import datetime as dt
import fcntl
import json
import os
import random
import re
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(HERE.parent / "checks"))

import build_plugin  # noqa: E402
from _util import QUALITY_ALL, model_family, plugin_tree_sha256, promote_blockers  # noqa: E402
from harness import arms as arms_mod  # noqa: E402
from harness import isolation, judge, judges, quality, quality_judge, stats, transcript  # noqa: E402

METRICS = ("compliance", "outcome", "tokens", "duration_s")
HARNESSES = ("agy", "claude-code")
# Tools a Claude Code candidate may use without a person; edits are allowed by acceptEdits.
CLAUDE_TOOLS = "Bash,Agent,TodoWrite"
# A candidate that hit its quota makes every later run void too (2026-11-19: agy "Individual quota reached").
# The no-plugin arm gets the prompt a user without the plugin would type.
COMMAND = re.compile(r"^/vex-mode(:vex-mode)?\s+")
DEFAULT_JOBS = 4  # Claude Code candidates at once; agy runs one at a time (one global install)
QUOTA = re.compile(r"quota|usage limit|rate.?limit|\b429\b", re.I)
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
    """Everything the run changed since the project was planted, committed or not."""
    root = _git(work, "rev-list", "--max-parents=0", "HEAD", check=False).splitlines()
    subprocess.run(["git", "-C", str(work), "add", "-A"], capture_output=True)
    return subprocess.run(
        ["git", "-C", str(work), "-c", "core.quotePath=false", "diff", "--cached", "--binary", "--no-color",
         "--no-ext-diff", "--src-prefix=a/", "--dst-prefix=b/", root[-1] if root else "HEAD", "--", ".",
         ":(exclude)**/__pycache__/**", ":(exclude)__pycache__/**"], capture_output=True, text=True).stdout


def _material(t: transcript.Transcript, diff: str) -> str:
    diff = diff if len(diff) <= DIFF_LIMIT else diff[:DIFF_LIMIT] + "\n[diff truncated]"
    steps = "\n".join(f"{i}. {s}" for i, s in enumerate(t.steps, 1)) or "(none)"
    # On Claude Code the Stop gate's follow-up is the last message; the reply to the user came before it.
    reply = f"### Final reply\n\n{t.response.strip()}"
    if t.gate_reply.strip():
        reply = (f"### Final reply\n\n{t.gate_reply.strip()}\n\n"
                 f"### Follow-up after the Stop hook asked for evidence\n\n{t.response.strip()}")
    return (f"{reply}\n\n### Tool calls, in order\n\n{steps}\n\n"
            f"### Diff\n\n```diff\n{diff}\n```")


_LIVE: set[subprocess.Popen] = set()
_LIVE_LOCK = threading.Lock()
_STOP = threading.Event()


class _Stopped(Exception):
    pass


def _call(cmd: list[str], work: Path, out, timeout_s: float, stdin=None) -> None:
    """Run a candidate in its own process group, killable from the main thread while other runs are live."""
    with _LIVE_LOCK:
        if _STOP.is_set():
            raise _Stopped()
        proc = subprocess.Popen(cmd, cwd=work, stdin=stdin, stdout=out, stderr=subprocess.DEVNULL,
                                env=judges.agent_env(), start_new_session=True)
        _LIVE.add(proc)
    try:
        proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        _kill(proc)
    finally:
        with _LIVE_LOCK:
            _LIVE.discard(proc)


def _kill(proc: subprocess.Popen) -> None:
    with contextlib.suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGKILL)
    proc.wait()


def _stop_all() -> None:
    with _LIVE_LOCK:
        _STOP.set()
        live = list(_LIVE)
    for proc in live:
        _kill(proc)


def _parallel(tasks: list, fn, jobs: int) -> dict:
    """fn(*task) for every task, `jobs` at a time, keyed by task. The first error (a quota stop, a signal) kills
    the runs in flight and starts no new one."""
    _STOP.clear()
    done = {}
    pool = ThreadPoolExecutor(max_workers=jobs)
    futures = {pool.submit(fn, *task): task for task in tasks}
    try:
        for future in as_completed(futures):
            done[futures[future]] = future.result()
    except BaseException:
        _stop_all()
        raise
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
        _STOP.clear()
    return done


def _run_candidate(arm, prompt: str, timeout_s: int, work: Path, log: Path) -> tuple[transcript.Transcript, float]:
    cmd = [*build_plugin.agy_command(), "-p", prompt, "--model", arm.model,
           "--output-format", "stream-json", "--print-timeout", f"{timeout_s}s"]
    start = time.monotonic()
    with open(log, "w") as out:
        _call(cmd, work, out, timeout_s + 60)
    return transcript.parse(log.read_text()), time.monotonic() - start


def _run_claude(arm, prompt: str, timeout_s: int, work: Path, log: Path, tree: Path | None) -> tuple[transcript.Transcript, float]:
    plugin = ["--plugin-dir", str(tree), "--add-dir", str(tree)] if tree is not None else []
    if tree is None:
        prompt = COMMAND.sub("", prompt)
    cmd = [*build_plugin.claude_command(), "--model", arm.model, *plugin, "--setting-sources", "project", "--permission-mode", "acceptEdits", "--allowedTools", CLAUDE_TOOLS,
           "--output-format", "stream-json", "--verbose", "-p", prompt]
    start = time.monotonic()
    with open(log, "w") as out:
        _call(cmd, work, out, timeout_s, stdin=subprocess.DEVNULL)
    return transcript.parse_claude(log.read_text()), time.monotonic() - start


def _outcome(case_dir: Path, work: Path, record: Path) -> int:
    r = subprocess.run([sys.executable, "-I", str(case_dir / "check.py"), str(work)], capture_output=True, text=True)
    record.write_text(f"exit {r.returncode}\n{r.stdout}{r.stderr}")
    return 1 if r.returncode == 0 else 0


def _judge(records: dict, materials: dict[int, str], rubric: str, judge_cfg: dict, run_dir: Path,
           rng: random.Random) -> tuple[str | None, dict]:
    """One blinded pass over every valid run; sets each run's label and compliance. Returns (error, usage).
    A run whose grade is missing, duplicated or has the wrong number of criteria gets compliance None."""
    if not materials:
        return None, {}
    order = list(materials)
    rng.shuffle(order)
    labels = {slot: f"R{i}" for i, slot in enumerate(order, 1)}
    prompt = judge.build_prompt(rubric, [(labels[s], materials[s]) for s in order])
    (run_dir / "judge-prompt.md").write_text(prompt)
    verdict, error, usage = judges.judge(prompt, judge.SCHEMA, judge_cfg, run_dir / "review")
    (run_dir / "verdict.json").write_text(json.dumps(verdict, indent=2) if verdict else "null")
    (run_dir / "labels.json").write_text(json.dumps({labels[s]: s for s in order}, indent=2))
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
    return error, usage


def _judge_config(repo: Path) -> dict:
    """The configured judge, checked before any candidate runs: a missing key fails now, not after the runs."""
    try:
        cfg = judges.load_config(repo)
        key = judges.api_key(cfg["provider"])
        if cfg["provider"] != "agy":
            judges.base_url(cfg["provider"])  # a secrets file it cannot read fails now, not after the runs
    except judges.JudgeConfigError as e:
        raise EvalError(str(e))
    if cfg["provider"] != "agy" and not key:
        raise EvalError(f"no API key for the {cfg['provider']} judge: set {judges.KEY_ENV[cfg['provider']]} "
                        f"or put it in ~/.config/vex-mode/secrets.env (chmod 600)")
    return cfg


def _judge_record(cfg: dict, error: str | None, usage: dict) -> dict:
    return {"provider": cfg["provider"], "model": cfg["model"], "effort": cfg["effort"], "error": error, "usage": usage}


def _touched(diff: str) -> set[str]:
    return set(re.findall(r"^diff --git \S+?/(\S+) ", diff, re.M))


def _quality(records: dict, case_dir: Path, cfg: dict, prompt: str, judge_cfg: dict, run_dir: Path,
             rng: random.Random) -> dict:
    """Code quality of every valid passing run (design §8.2.1): deterministic measures, then the quality judge."""
    if not cfg.get("quality"):
        return {"enabled": False, "errors": [], "judge_usage": {}}
    errors, patches, runs = [], {}, {}
    for rec in records.values():
        for r in rec["runs"]:
            r.pop("quality", None)
            r.pop("quality_errors", None)
            if r["invalid"] or r["outcome"] != 1:
                continue
            diff = (run_dir / "diffs" / f"{r['slot']}.diff").read_text()
            try:
                r["quality"], r["quality_errors"] = quality.measure(case_dir / "project", diff, case_dir / "check.py")
            except Exception as e:  # noqa: BLE001 - a crash here would lose every candidate run already made
                why = f"measure crashed: {type(e).__name__}: {e}"
                r["quality"], r["quality_errors"] = dict.fromkeys(quality.DETERMINISTIC), dict.fromkeys(quality.DETERMINISTIC, why)
            errors += [f"slot {r['slot']} {name}: {why}" for name, why in r["quality_errors"].items()]
            patches[r["slot"]], runs[r["slot"]] = diff, r
    usage = {}
    if patches:
        project = case_dir / "project"
        files = sorted(rel for diff in patches.values() for rel in _touched(diff) if (project / rel).is_file())
        context = f"## Request\n\n{prompt}\n\n## Original files\n" + "".join(
            f"\n### {rel}\n\n```\n{(project / rel).read_text(errors='replace')}\n```\n" for rel in dict.fromkeys(files))
        values, judge_errors, usage = quality_judge.grade(patches, context, judge_cfg, run_dir, rng)
        failed = {e.split(" ", 1)[0] for e in judge_errors}
        for slot, r in runs.items():
            r["quality"].update(values[slot])
            r["quality_errors"].update({name: "quality judge vote failed" for name in failed})
        errors += judge_errors
    return {"enabled": True, "errors": errors, "judge_usage": usage}


def _quality_metric(rec: dict, name: str) -> tuple[list[float], bool]:
    runs = [r for r in rec["runs"] if "quality" in r]
    values = [float(r["quality"][name]) for r in runs if r["quality"].get(name) is not None]
    return values, any(name in r.get("quality_errors", {}) for r in runs)


PAIRS = {"B_vs_A": ("A", "B"), "C_vs_A": ("A", "C")}
CALIBRATION_PAIRS = {"A_vs_N": ("N", "A")}


def _score(records: dict, with_quality: bool = False, pairs: dict = PAIRS) -> tuple[dict, dict]:
    metrics = {}
    for label, rec in records.items():
        m = {}
        for name in METRICS:
            values = [r[name] for r in rec["runs"]]
            m[name] = None if any(v is None for v in values) else stats.summarize([float(v) for v in values])
        for name in QUALITY_ALL if with_quality else ():
            values, _ = _quality_metric(rec, name)
            m[name] = stats.summarize(values) if values else None
        metrics[label] = m
    signals = {}
    for pair, (a, b) in pairs.items():
        s = {}
        for name in METRICS:
            x, y = metrics[a][name], metrics[b][name]
            if x is None or y is None:
                s[name] = None
            elif name == "outcome":
                s[name], s["outcome_p"] = stats.outcome_signal([r["outcome"] for r in records[a]["runs"]],
                                                               [r["outcome"] for r in records[b]["runs"]])
            else:
                s[name], s[f"{name}_p"] = stats.rank_signal(
                    [float(r[name]) for r in records[a]["runs"]], [float(r[name]) for r in records[b]["runs"]],
                    lower_is_better=name in ("tokens", "duration_s"))
        for name in QUALITY_ALL if with_quality else ():
            (xs, x_err), (ys, y_err) = _quality_metric(records[a], name), _quality_metric(records[b], name)
            if x_err or y_err:
                s[name] = "error"
            elif min(len(xs), len(ys)) < 2:
                s[name] = "few"
            else:
                s[name], s[f"{name}_p"] = stats.rank_signal(xs, ys, lower_is_better=name in quality.DETERMINISTIC)
        signals[pair] = s
    return metrics, signals


def rejudge(path: Path) -> None:
    """Judge an existing result again from its run dir (transcripts and saved diffs), without new runs."""
    result = json.loads(path.read_text())
    repo = path.resolve().parents[3]
    case_dir = repo / "evals" / result["skill"] / "cases" / result["case"]
    cfg = json.loads((case_dir / "case.json").read_text())
    run_dir = Path(result["run_dir"])
    claude = result.get("harness") == "claude-code"
    parse = transcript.parse_claude if claude else transcript.parse
    materials = {}
    for label, rec in result["arms"].items():
        for r in rec["runs"]:
            r.pop("label", None)
            t = parse((run_dir / "transcripts" / f"{r['slot']}.ndjson").read_text())
            # Isolation is checked again, so a false positive fixed since the eval no longer voids a run.
            # Without the run's working directory relative paths cannot be resolved: keep the stored reason.
            if t.cwd:
                r["invalid"] = _invalid(t, _plugin_root(claude, run_dir, label, bool(rec.get("plugin_ref"))),
                                        repo, Path(t.cwd))
            if r["invalid"]:
                r["outcome"], r["compliance"] = 0, 0.0
                continue
            diff, check = run_dir / "diffs" / f"{r['slot']}.diff", run_dir / "checks" / f"{r['slot']}.txt"
            for f in (diff, check):
                if not f.is_file():
                    raise EvalError(f"{f} is missing; rerun the eval")
            r["outcome"] = 1 if check.read_text().startswith("exit 0\n") else 0
            materials[r["slot"]] = _material(t, diff.read_text())
            r["compliance"] = None
    if empty := [label for label, rec in result["arms"].items() if not any(r["invalid"] is None for r in rec["runs"])]:
        raise EvalError(f"arm {empty[0]} has no valid run, so nothing can be compared; result left as it was")
    judge_cfg = _judge_config(repo)
    families = {model_family(rec["model"]) for rec in result["arms"].values()}
    if model_family(judge_cfg["model"]) in families:
        raise EvalError(f"judge {judge_cfg['model']} shares a model family with a candidate ({sorted(families)})")
    rng = random.Random()
    with _locked():
        error, usage = _judge(result["arms"], materials, (case_dir / "rubric.md").read_text(), judge_cfg,
                              run_dir, rng)
        result["quality"] = _quality(result["arms"], case_dir, cfg, (case_dir / "prompt.md").read_text().strip(),
                                     judge_cfg, run_dir, rng)
    result["judge"] = _judge_record(judge_cfg, error, usage)
    pairs = CALIBRATION_PAIRS if result.get("kind") == "calibration" else PAIRS
    result["metrics"], result["signals"] = _score(result["arms"], result["quality"]["enabled"], pairs)
    result["verdict"], result["synthesis"] = None, None
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(f"result: {path}")


def _plugin_root(claude: bool, run_dir: Path, label: str, has_plugin: bool) -> Path:
    """Where an arm's own plugin files live during its runs; reads there are allowed."""
    if not has_plugin:
        return run_dir / "no-plugin" if claude else _plugin_home() / "vex-mode"
    # The Claude Code build sits outside the eval cache (a forbidden root) so an arm may read its own plugin files.
    return _cache() / "vex-cc" / run_dir.name / label if claude else _plugin_home() / "vex-mode"


def _invalid(t: transcript.Transcript, plugin_root: Path, repo: Path, workdir: Path | None) -> str | None:
    bad = isolation.violations(t, plugin_root=plugin_root, forbidden=[_cache() / "vex-mode", repo, judges._secrets_file()],
                               workdir=workdir, work_root=_cache() / "vex-work", home=Path.home())
    return "; ".join(bad) or (None if t.status == "SUCCESS" else f"status {t.status}")


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
             variant: str = "HEAD", runs: int | None = None, harness: str | None = None,
             calibrate: bool = False, jobs: int | None = None) -> Path:
    repo = repo.resolve()
    case_dir = repo / "evals" / skill / "cases" / case
    cfg = json.loads((case_dir / "case.json").read_text())
    runs = runs or cfg["runs"]
    harness = harness or cfg.get("harness", "agy")
    if harness not in HARNESSES:
        raise EvalError(f"harness must be one of {', '.join(HARNESSES)}")
    claude = harness == "claude-code"
    jobs = jobs or (DEFAULT_JOBS if claude else 1)
    if jobs > 1 and not claude:
        raise EvalError("agy runs one candidate at a time (one global plugin install); --jobs needs Claude Code")
    if jobs < 1:
        raise EvalError("--jobs must be at least 1")
    if calibrate and not claude:
        raise EvalError("calibrate runs on Claude Code only: agy cannot run without its global plugin")
    if claude:
        cfg = {**cfg, **cfg.get("claude_code", {})}
        if model_family(cfg["candidate_model"]) != "claude" or model_family(cfg["upgrade_model"]) != "claude":
            raise EvalError(f"case {case} has no Claude Code models; add \"claude_code\" to its case.json")
    if _marker().exists() and not claude:
        raise EvalError(f"a previous eval did not restore the plugin; run `python3 evals/run.py restore` first")
    if _git(repo, "status", "--porcelain", "--", "skills/"):
        raise EvalError("skills/ has uncommitted changes; the variant must be a commit")
    if base is None and calibrate:
        base = "origin/main"
    if base is None:
        base = _git(repo, "merge-base", "origin/main", "HEAD", check=False)
        if not base:
            raise EvalError("no merge base with origin/main; pass --base")
    judge_cfg = _judge_config(repo)
    if calibrate:
        arm_list = arms_mod.calibration_arms(cfg, _commit(repo, base), judge_cfg["model"])
    else:
        arm_list = arms_mod.build_arms(cfg, _commit(repo, base), _commit(repo, variant), judge_cfg["model"])

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    run_dir = _cache() / "vex-mode" / "runs" / stamp
    for sub in ("transcripts", "diffs", "checks"):
        (run_dir / sub).mkdir(parents=True)
    # Every run reads the case from this snapshot, so a branch change during the eval cannot reach it.
    shutil.copytree(case_dir, run_dir / "case", ignore=shutil.ignore_patterns("__pycache__"))
    case_dir = run_dir / "case"
    prompt = (case_dir / "prompt.md").read_text().strip()
    rubric = (case_dir / "rubric.md").read_text()
    builds = {arm.label: build_plugin.build(repo, run_dir / "build" / arm.label, ref=arm.plugin_ref)
              for arm in arm_list if arm.plugin_ref}
    trees = {arm.label: plugin_tree_sha256(builds[arm.label], skill) if arm.plugin_ref else None
             for arm in arm_list}
    if not calibrate and trees["A"] == trees["B"]:
        raise EvalError(f"base {base} and variant {variant} have the same skill tree for {skill}, so there is nothing "
                        f"to measure; pass --base with a commit from before the change")
    # Outside the eval cache (a forbidden root) so an arm may read its own plugin files.
    cc_trees = {arm.label: build_plugin.build_claude(repo, _cache() / "vex-cc" / stamp / arm.label, arm.plugin_ref)
                for arm in arm_list if arm.plugin_ref} if claude else {}
    name = f"{case}-claude-code" if claude else case
    folder, tree = ("calibration", trees["A"]) if calibrate else ("results", trees["B"])
    # A case can be calibrated again after it changes (same tree), so calibrations also carry the time.
    suffix = f"-{stamp[9:15]}" if calibrate else ""
    path = repo / "evals" / skill / folder / f"{dt.date.today().isoformat()}-{name}-{tree[:12]}{suffix}.json"
    if path.exists():
        raise EvalError(f"{path} already exists; delete it to run this eval again")

    installed = _plugin_home() / "vex-mode"
    work_root = _cache() / "vex-work"
    rng = random.Random()
    slots = list(range(1, len(arm_list) * runs + 1))
    rng.shuffle(slots)
    records: dict[str, dict] = {}
    materials: dict[int, str] = {}
    def one(arm, slot: int) -> tuple[dict, str | None]:
        """One candidate run in a fresh private copy of the project; returns its record and the judge's material."""
        private = work_root / secrets.token_hex(4)
        work = private / cfg["workdir"]
        _fresh_workdir(case_dir / "project", work)
        material = None
        try:
            log = run_dir / "transcripts" / f"{slot}.ndjson"
            if claude:
                t, wall = _run_claude(arm, prompt, cfg["timeout_s"], work, log, cc_trees.get(arm.label))
            else:
                t, wall = _run_candidate(arm, prompt, cfg["timeout_s"], work, log)
            if QUOTA.search(t.error):
                raise EvalError(f"arm {arm.label}: the candidate model's quota ran out ({t.error[:200]}); "
                                f"stopped, no result written; run dir: {run_dir}")
            invalid = _invalid(t, _plugin_root(claude, run_dir, arm.label, bool(arm.plugin_ref)), repo, work)
            diff = _diff(work)
            (run_dir / "diffs" / f"{slot}.diff").write_text(diff)
            outcome = _outcome(case_dir, work, run_dir / "checks" / f"{slot}.txt")
            if invalid:
                outcome = 0
            else:
                material = _material(t, diff)
        finally:
            shutil.rmtree(private, ignore_errors=True)
        finished = t.status == "SUCCESS"
        return {"slot": slot, "status": t.status, "invalid": invalid, "outcome": outcome,
                "compliance": 0.0 if invalid else None,
                "tokens": t.total_tokens if finished else t.step_tokens,
                "duration_s": t.duration_s if finished else wall,
                "reads": len(t.reads), "commands": len(t.commands),
                **({"cost_usd": t.cost_usd} if claude else {})}, material

    with _locked():
        backup = run_dir / "installed-backup"
        if not claude:
            if installed.is_dir():
                shutil.copytree(installed, backup)
            _marker().write_text(str(backup) if backup.is_dir() else "-")
        saved = {sig: signal.signal(sig, _raise_interrupt) for sig in (signal.SIGTERM, signal.SIGHUP)}
        try:
            plan = {arm.label: [slots.pop() for _ in range(runs)] for arm in arm_list}
            if claude:
                done = _parallel([(arm, slot) for arm in arm_list for slot in plan[arm.label]], one, jobs)
            else:
                done = {}
                for arm in arm_list:
                    build_plugin.install(builds[arm.label])
                    if plugin_tree_sha256(installed, skill) != trees[arm.label]:
                        raise EvalError(f"arm {arm.label}: installed skill does not match the build")
                    done.update({(arm, slot): one(arm, slot) for slot in plan[arm.label]})
            for arm in arm_list:
                arm_runs = []
                for slot in plan[arm.label]:
                    run_record, material = done[(arm, slot)]
                    arm_runs.append(run_record)
                    if material is not None:
                        materials[slot] = material
                records[arm.label] = {"model": arm.model, "plugin_ref": arm.plugin_ref,
                                      "tree_sha256": trees[arm.label], "runs": arm_runs}
        finally:
            for sig, handler in saved.items():
                signal.signal(sig, handler)
            if not claude:
                restore()

        empty = [label for label, rec in records.items() if not any(r["invalid"] is None for r in rec["runs"])]
        if empty:
            raise EvalError(f"arm {empty[0]} has no valid run, so nothing can be compared; no result written; "
                            f"run dir: {run_dir}")
        judge_error, judge_usage = _judge(records, materials, rubric, judge_cfg, run_dir, rng)
        quality_record = _quality(records, case_dir, cfg, prompt, judge_cfg, run_dir, rng)
    metrics, signals = _score(records, quality_record["enabled"], CALIBRATION_PAIRS if calibrate else PAIRS)
    result = {
        "kind": "calibration" if calibrate else "eval", "skill": skill, "tree_sha256": tree,
        "date": dt.date.today().isoformat(),
        "case": case, "harness": harness, "jobs": jobs, "run_dir": str(run_dir), "arms": records,
        "judge": _judge_record(judge_cfg, judge_error, judge_usage), "quality": quality_record,
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
    blockers = promote_blockers(result) if verdict == "promote" else []
    if blockers:
        raise EvalError("promote refused: " + "; ".join(blockers))
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
        if argv[:1] == ["calibrate"]:
            parser = argparse.ArgumentParser(description="Plugin against no plugin on Claude Code, same model.")
            parser.add_argument("skill")
            parser.add_argument("case")
            parser.add_argument("--base")
            parser.add_argument("--runs", type=int)
            parser.add_argument("--jobs", type=int, help=f"candidates at once (default {DEFAULT_JOBS})")
            args = parser.parse_args(argv[1:])
            run_eval(HERE.parent, args.skill, args.case, args.base, runs=args.runs, harness="claude-code", calibrate=True,
                     jobs=args.jobs)
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
        parser.add_argument("--harness", choices=HARNESSES)
        parser.add_argument("--jobs", type=int, help=f"candidates at once on Claude Code (default {DEFAULT_JOBS}; agy: 1)")
        args = parser.parse_args(argv)
        run_eval(HERE.parent, args.skill, args.case, args.base, args.variant, args.runs, args.harness, jobs=args.jobs)
        return 0
    except (EvalError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
