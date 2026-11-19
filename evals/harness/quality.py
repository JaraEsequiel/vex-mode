"""Code-quality measures of one run's patch (design §8.2.1), with the stdlib only: ast, tokenize, difflib.

Every measure compares the case's project (before) with the project after the run's patch (after).
Lower is better for all of them; test_lines and docstrings_added are informative only.
"""
import ast
import difflib
import io
import math
import re
import shutil
import subprocess
import sys
import tempfile
import tokenize
from pathlib import Path

DETERMINISTIC = ("prod_lines", "test_lines", "removable_lines", "complexity_delta", "verbosity",
                 "comments_added", "docstrings_added", "security_findings")
UNSAFE_CALLS = {"eval", "exec", "os.system", "os.popen", "pickle.loads", "marshal.loads", "tempfile.mktemp",
                "hashlib.md5", "hashlib.sha1", "ssl._create_unverified_context"}
SECRET_NAME = re.compile(r"key|secret|token|password", re.I)
BRANCHES = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.IfExp, ast.ExceptHandler, ast.With, ast.AsyncWith,
            ast.Assert, ast.match_case)
SKIP = shutil.ignore_patterns("__pycache__", ".git")


class _CheckTimeout(Exception):
    pass


def is_test(rel: str) -> bool:
    parts = Path(rel).parts
    name = parts[-1]
    return "tests" in parts[:-1] or (name.startswith("test_") and name.endswith(".py")) or name.endswith("_test.py")


def apply_diff(project: Path, diff: str, dest: Path) -> str | None:
    """Copy project to dest and apply diff there. Saved diffs lose their final newline, so it is restored."""
    shutil.copytree(project, dest, ignore=SKIP, dirs_exist_ok=True)
    if not diff.strip():
        return None
    r = subprocess.run(["git", "apply", "-p1", "--whitespace=nowarn", "-"], cwd=dest, capture_output=True, text=True,
                       input=diff if diff.endswith("\n") else diff + "\n")
    return None if r.returncode == 0 else f"diff does not apply: {r.stderr.strip()[:300]}"


def measure(project: Path, diff: str, check: Path) -> tuple[dict, dict]:
    with tempfile.TemporaryDirectory(prefix="vex-quality-") as tmp:
        after = Path(tmp) / "after"
        error = apply_diff(project, diff, after)
        if error:
            return dict.fromkeys(DETERMINISTIC), dict.fromkeys(DETERMINISTIC, error)
        return measure_dirs(project, after, check)


def _texts(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): p.read_bytes().decode("utf-8", "replace")
            for p in sorted(root.rglob("*")) if p.is_file() and not {"__pycache__", ".git"} & set(p.parts)}


def _changes(a: list[str], b: list[str]) -> list[tuple]:
    return difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes()


def _added(ops: list[tuple]) -> set[int]:
    return {j + 1 for tag, _, _, j1, j2 in ops if tag in ("insert", "replace") for j in range(j1, j2)}


def measure_dirs(before: Path, after: Path, check: Path | None, timeout_s: int = 30) -> tuple[dict, dict]:
    old, new = _texts(before), _texts(after)
    files = {}
    for rel in sorted(set(old) | set(new)):
        if old.get(rel) != new.get(rel):
            a, b = old.get(rel, "").splitlines(keepends=True), new.get(rel, "").splitlines(keepends=True)
            files[rel] = (a, b, _changes(a, b))
    values = dict.fromkeys(DETERMINISTIC, 0)
    errors: dict[str, str] = {}

    def fail(names, why):
        for name in names:
            errors[name] = f"{errors[name]}; {why}" if name in errors else why

    added_prod = 0
    for rel, (a, b, ops) in files.items():
        count = sum((i2 - i1) + (j2 - j1) for tag, i1, i2, j1, j2 in ops if tag != "equal")
        values["test_lines" if is_test(rel) else "prod_lines"] += count
        if not rel.endswith(".py"):
            continue
        added = _added(ops)
        prod = not is_test(rel)
        try:
            tree_after, tree_before = ast.parse("".join(b)), ast.parse("".join(a)) if a else None
            comments = _comments("".join(b))
        except (SyntaxError, ValueError, tokenize.TokenError) as e:
            fail(("comments_added", "docstrings_added", "security_findings")
                 + (("complexity_delta", "verbosity") if prod else ()), f"{rel}: {type(e).__name__} {e}")
            continue
        values["comments_added"] += len(comments & added)
        values["docstrings_added"] += len(_docstrings(tree_after) & added)
        values["security_findings"] += max(0, _hits(tree_after) - (_hits(tree_before) if tree_before else 0))
        if prod:
            values["complexity_delta"] += _mass(tree_after, b) - (_mass(tree_before, a) if tree_before else 0.0)
            code = {n for n in added if b[n - 1].strip()}
            added_prod += len(code)
            values["verbosity"] += len((_flags(tree_after) | _clones(b, added)) & code)
    values["verbosity"] = values["verbosity"] / added_prod if added_prod else 0.0
    if check is None:
        values["removable_lines"] = None
    else:
        try:
            values["removable_lines"] = _removable(after, {r: f for r, f in files.items() if not is_test(r)}, check,
                                                   timeout_s)
        except _CheckTimeout:
            values["removable_lines"] = None
            fail(("removable_lines",), f"check timed out after {timeout_s}s")
        except ValueError as e:
            values["removable_lines"] = None
            fail(("removable_lines",), str(e))
    return values, errors


def _comments(source: str) -> set[int]:
    return {t.start[0] for t in tokenize.generate_tokens(io.StringIO(source).readline) if t.type == tokenize.COMMENT}


def _docstrings(tree: ast.AST) -> set[int]:
    owners = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    return {n.body[0].lineno for n in ast.walk(tree) if isinstance(n, owners) and n.body
            and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)
            and isinstance(n.body[0].value.value, str)}


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_dotted(node.value)}.{node.attr}"
    return ""


def _hits(tree: ast.AST) -> int:
    n = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _dotted(node.func)
            kw = {k.arg: k.value for k in node.keywords}
            n += name in UNSAFE_CALLS
            if name == "yaml.load":
                loader = kw.get("Loader", node.args[1] if len(node.args) > 1 else None)
                n += not (loader is not None and _dotted(loader).endswith("SafeLoader"))
            n += any(isinstance(kw.get(k), ast.Constant) and kw[k].value is v for k, v in (("shell", True),
                                                                                         ("verify", False)))
        elif isinstance(node, ast.Attribute) and node.attr == "CERT_NONE":
            n += 1
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            n += any(isinstance(t, ast.Name) and SECRET_NAME.search(t.id) for t in node.targets) and bool(node.value.value)
    return n


def cc(node: ast.AST) -> int:
    """Cyclomatic complexity of one function, radon's rules; nested functions and classes count on their own."""
    n, stack = 1, list(ast.iter_child_nodes(node))
    while stack:
        child = stack.pop()
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(child, BRANCHES):
            n += 1
        elif isinstance(child, ast.comprehension):
            n += 1 + len(child.ifs)
        elif isinstance(child, ast.BoolOp):
            n += len(child.values) - 1
        stack.extend(ast.iter_child_nodes(child))
    return n


def _mass(tree: ast.AST, lines: list[str]) -> float:
    total = 0.0
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            span = lines[fn.lineno - 1:fn.end_lineno]
            sloc = sum(1 for line in span if line.strip() and not line.strip().startswith("#"))
            total += cc(fn) * math.sqrt(sloc)
    return total


def mass(source: str) -> float:
    """SlopCodeBench's complexity mass: the sum over functions of CC(f) * sqrt(SLOC(f))."""
    return _mass(ast.parse(source), source.splitlines(keepends=True))


def _empty(node: ast.AST | None) -> bool:
    return (isinstance(node, (ast.List, ast.Tuple, ast.Dict)) and not getattr(node, "elts", getattr(node, "keys", None))) \
        or (isinstance(node, ast.Constant) and node.value in (None, 0, ""))


def _flags(tree: ast.AST) -> set[int]:
    """Lines that match a verbose pattern (SlopCodeBench's examples, design §8.2.1)."""
    out = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.For) and len(node.body) == 1 and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Call) and isinstance(node.body[0].value.func, ast.Attribute)
                and node.body[0].value.func.attr == "append"):
            out.add(node.lineno)
        elif isinstance(node, ast.Compare):
            left_len = isinstance(node.left, ast.Call) and _dotted(node.left.func) == "len"
            for op, right in zip(node.ops, node.comparators):
                if not isinstance(right, ast.Constant):
                    continue
                if (left_len and right.value == 0) or (isinstance(op, (ast.Eq, ast.NotEq)) and right.value in (True, False)
                                                       and isinstance(right.value, bool)):
                    out.add(node.lineno)
        elif isinstance(node, ast.If):
            if node.orelse and isinstance(node.body[-1], (ast.Return, ast.Raise)):
                out.add(node.lineno)
            if (isinstance(node.test, ast.UnaryOp) and isinstance(node.test.op, ast.Not) and len(node.body) == 1
                    and isinstance(node.body[0], ast.Return) and _empty(node.body[0].value)):
                out.add(node.lineno)
        elif isinstance(node, ast.ExceptHandler) and all(isinstance(s, ast.Pass) for s in node.body):
            out.add(node.lineno)
        for field in ("body", "orelse", "finalbody"):
            stmts = getattr(node, field, None)
            if not isinstance(stmts, list):
                continue
            for first, second in zip(stmts, stmts[1:]):
                if (isinstance(first, ast.Assign) and len(first.targets) == 1 and isinstance(first.targets[0], ast.Name)
                        and isinstance(second, ast.Return) and isinstance(second.value, ast.Name)
                        and second.value.id == first.targets[0].id):
                    out.add(first.lineno)
    return out


def _clones(lines: list[str], added: set[int]) -> set[int]:
    """Added lines inside a window of 3 non-blank normalized lines that occurs more than once in the file."""
    code = [(i + 1, line.strip()) for i, line in enumerate(lines) if line.strip()]
    windows: dict[tuple, list[list[int]]] = {}
    for k in range(len(code) - 2):
        window = code[k:k + 3]
        windows.setdefault(tuple(t for _, t in window), []).append([n for n, _ in window])
    return {n for spots in windows.values() if len(spots) > 1 for spot in spots for n in spot if n in added}


def _run_check(check: Path, root: Path, timeout_s: int) -> bool:
    try:
        r = subprocess.run([sys.executable, "-I", "-B", str(check), str(root)], capture_output=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        raise _CheckTimeout
    return r.returncode == 0


def _removable(after: Path, files: dict, check: Path, timeout_s: int) -> int:
    """TRIM-NG (arXiv 2607.18161) with the hidden check as oracle: revert whole change blocks, then single lines of
    pure insertions and deletions, last to first; keep a revert only if the check still passes. Blank-only units and
    replaced lines stay atomic, so the count is never inflated by whitespace or by half-reverted edits."""
    if not _run_check(check, after, timeout_s):
        raise ValueError("check fails on the patch itself")
    with tempfile.TemporaryDirectory(prefix="vex-trim-") as tmp:
        scratch = Path(tmp) / "w"
        shutil.copytree(after, scratch, ignore=SKIP)
        state = {rel: {"blocks": set(), "lines": set()} for rel in files}

        def render(rel: str) -> str:
            a, b, ops = files[rel]
            out = []
            for k, (tag, i1, i2, j1, j2) in enumerate(ops):
                if tag == "equal" or k in state[rel]["blocks"]:
                    out += a[i1:i2]
                elif tag == "delete":
                    out += [a[i] for i in range(i1, i2) if ("a", i) in state[rel]["lines"]]
                else:
                    out += [b[j] for j in range(j1, j2) if ("b", j) not in state[rel]["lines"]]
            return "".join(out)

        def attempt(rel: str, key: str, unit, size: int) -> int:
            state[rel][key].add(unit)
            (scratch / rel).parent.mkdir(parents=True, exist_ok=True)
            (scratch / rel).write_text(render(rel))
            if _run_check(check, scratch, timeout_s):
                return size
            state[rel][key].discard(unit)
            (scratch / rel).write_text(render(rel))
            return 0

        removed = 0
        for rel, (a, b, ops) in files.items():
            for k in reversed(range(len(ops))):
                tag, i1, i2, j1, j2 = ops[k]
                if tag != "equal" and any(line.strip() for line in a[i1:i2] + b[j1:j2]):
                    removed += attempt(rel, "blocks", k, (i2 - i1) + (j2 - j1))
        for rel, (a, b, ops) in files.items():
            for k in reversed(range(len(ops))):
                tag, i1, i2, j1, j2 = ops[k]
                if k in state[rel]["blocks"] or tag not in ("insert", "delete"):
                    continue
                side, lines, lo, hi = ("b", b, j1, j2) if tag == "insert" else ("a", a, i1, i2)
                for n in reversed(range(lo, hi)):
                    if lines[n].strip():
                        removed += attempt(rel, "lines", (side, n), 1)
        return removed
