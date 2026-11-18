"""PreToolUse (run_command): force a human confirmation before irreversible commands.

Returns None (print nothing) when it has no opinion: agy treats `{}` as deny.
"""
import os
import re
import shlex

from vexio import read_payload, safe_main

OPERATORS = {"&&", "||", ";", "|", "&", "(", ")", "$", "$(", "`"}
GIT_PUSH_FLAGS = {"--force", "--mirror", "--delete", "--force-if-includes", "--prune"}
SHELLS = {"bash", "sh", "zsh", "dash"}
WRAPPERS = {"command", "nohup", "time", "exec", "builtin"}
# wrapper -> options that take a separate argument
WRAPPER_ARGS = {"sudo": {"-u", "-g", "-C", "-h", "-p", "-U"}, "env": {"-u", "-C", "-S"}, "xargs": {"-I", "-n", "-P", "-d", "-L", "-s", "-E", "-a"}}
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
    if cmd == "git" and "push" in args:
        return _git_push(args[args.index("push") + 1:])
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
    call = payload.get("toolCall") or {}
    args = call.get("args") or {}
    command = args.get("CommandLine") if isinstance(args, dict) else None
    if not isinstance(command, str):
        return None
    reason = classify(command)
    if reason is None:
        return None
    return {
        "decision": "force_ask",
        "reason": f"vex-mode: irreversible action ({reason}). Always pause: confirm before it runs.",
    }


if __name__ == "__main__":
    safe_main(lambda: handle(read_payload()), None)
