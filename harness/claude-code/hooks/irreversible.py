"""PreToolUse (agy run_command, Claude Code Bash): force a human confirmation before irreversible commands.

Returns None (print nothing) when it has no opinion: agy treats `{}` as deny.
"""
import os
import re
import shlex

from vexio import is_claude_code, read_payload, safe_main

OPERATORS = {"&&", "||", ";", "|", "&", "(", ")", "$", "$(", "`"}
GIT_PUSH_FLAGS = {"--force", "--mirror", "--delete", "--force-if-includes", "--prune", "--all"}
SHELLS = {"bash", "sh", "zsh", "dash"}
WRAPPERS = {"command", "nohup", "time", "exec", "builtin"}
# wrapper -> options that take a separate argument
WRAPPER_ARGS = {"sudo": {"-u", "-g", "-C", "-h", "-p", "-U"}, "env": {"-u", "-C", "-S"}, "xargs": {"-I", "-n", "-P", "-d", "-L", "-s", "-E", "-a"}}
PROTECTED_BRANCHES = {"main", "master"}
SQL = re.compile(r"\b(drop\s+(table|database|schema)|truncate\b)", re.IGNORECASE)


def _segments(command: str) -> list[list[str]]:
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        tokens = command.split()
    segments, current = [], []
    for tok in tokens:
        if tok in OPERATORS:
            segments.append(current)
            current = []
        else:
            current.append(tok)
    segments.append(current)
    cleaned = []
    for seg in segments:
        seg = _strip_wrappers(seg)
        if seg:
            cleaned.append(seg)
    return cleaned


def _strip_wrappers(seg: list[str]) -> list[str]:
    """Drop env assignments and wrapper commands so the real command comes first."""
    while seg:
        head = os.path.basename(seg[0])
        if "=" in seg[0] and not seg[0].startswith("-"):
            seg = seg[1:]
        elif head in WRAPPERS:
            seg = seg[1:]
        elif head in WRAPPER_ARGS:
            takes_arg = WRAPPER_ARGS[head]
            seg = seg[1:]
            while seg and (seg[0].startswith("-") or (head == "env" and "=" in seg[0])):
                seg = seg[2:] if seg[0] in takes_arg else seg[1:]
        else:
            break
    return seg


def _git_push(args: list[str]) -> str | None:
    for a in args:
        if a in GIT_PUSH_FLAGS or a.startswith("--force-with-lease"):
            return f"git push {a}"
        if re.fullmatch(r"-[a-zA-Z]*[fd][a-zA-Z]*", a):
            return f"git push {a}"
        if a.startswith("+"):
            return f"git push with force refspec {a}"
        if a.startswith(":") and len(a) > 1:
            return f"git push deleting remote ref {a}"
    refspecs = [a for a in args if not a.startswith("-")][1:]
    for spec in refspecs:
        dest = spec.split(":")[-1].removeprefix("refs/").removeprefix("heads/")
        if dest in PROTECTED_BRANCHES:
            return f"git push to {dest} (only the user merges)"
    return None


GH_FLAGS_WITH_VALUE = {"-R", "--repo"}
GH_API_MERGE = re.compile(
    r"/merges?/?(\?|$)|mergePullRequest|enablePullRequestAutoMerge|git/refs/heads/(main|master)\b")


def _positional(args: list[str], with_value: set[str]) -> list[str]:
    out, skip = [], False
    for a in args:
        if skip:
            skip = False
        elif a in with_value:
            skip = True
        elif not a.startswith("-"):
            out.append(a)
    return out


def _gh(args: list[str]) -> str | None:
    if _positional(args, GH_FLAGS_WITH_VALUE)[:2] == ["pr", "merge"]:
        return "gh pr merge (only the user merges)"
    if args[:1] == ["api"] and any(GH_API_MERGE.search(a) for a in args[1:]):
        return "gh api merge or main ref update (only the user merges)"
    return None


def _git(args: list[str]) -> str | None:
    for i, a in enumerate(args[:-1]):
        if a == "-c" and re.match(r"(remote\.[^=]*\.push|push\.default)=", args[i + 1]):
            return f"git -c {args[i + 1]} (changes where a push goes)"
    if "branch" in args:
        rest = args[args.index("branch") + 1:]
        targets = [rest[i + 1] for i, a in enumerate(rest[:-1]) if a == "-u"]
        targets += [a.split("=", 1)[1] for a in rest if a.startswith("--set-upstream-to=")]
        if any(t.split("/")[-1] in PROTECTED_BRANCHES for t in targets):
            return "git branch tracking main (a bare push would go there)"
    if "push" in args:
        return _git_push(args[args.index("push") + 1:])
    return None


def _rm(args: list[str]) -> str | None:
    flags = "".join(a.lstrip("-") for a in args if re.fullmatch(r"-[a-zA-Z]+", a))
    recursive = "r" in flags.lower() or "--recursive" in args
    force = "f" in flags or "--force" in args
    targets = [a for a in args if not a.startswith("-")]
    if recursive and force and any(t.startswith(("/", "~", "$", "..")) for t in targets):
        return "rm -rf on an absolute, home, variable or parent path"
    return None


def _segment(tokens: list[str]) -> str | None:
    cmd, args = os.path.basename(tokens[0]), tokens[1:]
    if cmd in SHELLS:
        for i, a in enumerate(args[:-1]):
            if re.fullmatch(r"-[a-zA-Z]*c[a-zA-Z]*", a):
                return classify(args[i + 1])
        return None
    if cmd == "git":
        return _git(args)
    if cmd == "eval":
        return classify(" ".join(args))
    if cmd == "gh":
        return _gh(args)
    if cmd == "rm":
        return _rm(args)
    if cmd == "terraform" and args[:1] in (["destroy"], ["apply"]):
        return f"terraform {args[0]}"
    if cmd == "kubectl" and args[:1] == ["delete"]:
        return "kubectl delete"
    if cmd in ("firebase", "fly", "flyctl") and "deploy" in args:
        return f"{cmd} deploy"
    if cmd == "vercel" and "--prod" in args:
        return "vercel --prod"
    if cmd in ("psql", "mysql", "sqlite3") and any(SQL.search(a) for a in args):
        return "destructive SQL"
    return None


def classify(command: str) -> str | None:
    for tokens in _segments(command):
        reason = _segment(tokens)
        if reason:
            return reason
    return None


def handle(payload: dict) -> dict | None:
    if is_claude_code(payload):
        args = payload.get("tool_input") if payload.get("tool_name") == "Bash" else None
        command = args.get("command") if isinstance(args, dict) else None
    else:
        call = payload.get("toolCall") or {}
        args = call.get("args") or {}
        command = args.get("CommandLine") if isinstance(args, dict) else None
    if not isinstance(command, str):
        return None
    reason = classify(command)
    if reason is None:
        return None
    if is_claude_code(payload):
        # In `claude -p`, "ask" denies the call and the agent reads the reason (probe, finding 4).
        return {"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": f"vex-mode: irreversible action ({reason}). Always pause: confirm before it runs.",
        }}
    return {
        "decision": "force_ask",
        "reason": f"vex-mode: irreversible action ({reason}). Always pause: confirm before it runs.",
    }


if __name__ == "__main__":
    safe_main(lambda: handle(read_payload()), None)
