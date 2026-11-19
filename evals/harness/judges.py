"""The eval judge, called directly over a provider's API (design §8.2). One request per eval.

Config: evals/judge.json {provider, model, effort}; env VEX_JUDGE_PROVIDER / VEX_JUDGE_MODEL /
VEX_JUDGE_EFFORT override it. Keys: OPENAI_API_KEY / ANTHROPIC_API_KEY, else ~/.config/vex-mode/secrets.env
(VEX_SECRETS), which must not be readable by group or others. A key is never returned in an error.
"""
import copy
import json
import os
import shlex
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULTS = {"provider": "openai", "model": "gpt-6.2-sol", "effort": "medium"}
PROVIDERS = ("openai", "anthropic", "agy")
KEY_ENV = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}
TIMEOUT_S = 600
MAX_OUTPUT_TOKENS = 64000
INLINE_MAX = 100_000  # agy only: one argv string is capped at 128 KiB on Linux
ANTHROPIC_VERSION = "2026-10-21"


class JudgeConfigError(Exception):
    pass


def load_config(repo: Path) -> dict:
    path = repo / "evals/judge.json"
    cfg = dict(DEFAULTS, **(json.loads(path.read_text()) if path.is_file() else {}))
    for key in ("provider", "model", "effort"):
        if os.environ.get(f"VEX_JUDGE_{key.upper()}"):
            cfg[key] = os.environ[f"VEX_JUDGE_{key.upper()}"]
    if cfg["provider"] not in PROVIDERS:
        raise JudgeConfigError(f"judge provider {cfg['provider']!r} is not one of {', '.join(PROVIDERS)}")
    return cfg


def _secrets_file() -> Path:
    return Path(os.environ.get("VEX_SECRETS", Path.home() / ".config/vex-mode/secrets.env"))


def api_key(provider: str) -> str | None:
    name = KEY_ENV.get(provider)
    if name is None:
        return None
    if os.environ.get(name):
        return os.environ[name]
    path = _secrets_file()
    if not path.is_file():
        return None
    if path.stat().st_mode & 0o077:
        raise JudgeConfigError(f"{path} is readable by other users; run: chmod 600 {path}")
    for line in path.read_text().splitlines():
        k, sep, v = line.strip().partition("=")
        if sep and k.strip() == name:
            return v.strip().strip("'\"")
    return None


def strict_schema(schema: dict) -> dict:
    """Strict structured outputs: every object closes its properties and requires all of them."""
    out = copy.deepcopy(schema)

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                node["additionalProperties"] = False
                node["required"] = list(node.get("properties", {}))
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(out)
    return out


def _post(url: str, headers: dict, body: dict) -> tuple[int, dict | str]:
    data = json.dumps(body).encode()
    for attempt in (1, 2):
        req = urllib.request.Request(url, data=data, method="POST",
                                     headers={"Content-Type": "application/json", **headers})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                return resp.status, json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as e:
            text = e.read().decode(errors="replace")
            if attempt == 1 and (e.code == 429 or e.code >= 500):
                time.sleep(float(e.headers.get("retry-after") or 30))
                continue
            try:
                return e.code, json.loads(text)
            except ValueError:
                return e.code, text
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            if attempt == 1:
                time.sleep(30)
                continue
            return 0, str(e)
    return 0, "unreachable"


def _http_error(status: int, body) -> str:
    msg = body.get("error", {}).get("message") if isinstance(body, dict) else str(body)[:500]
    return f"judge API returned HTTP {status}: {msg}"


def _verdict(text: str) -> tuple[dict | None, str | None]:
    try:
        data = json.loads(text)
    except (TypeError, ValueError) as e:
        return None, f"judge output is not JSON ({e})"
    if not (isinstance(data, dict) and isinstance(data.get("runs"), list)
            and all(isinstance(r, dict) and isinstance(r.get("criteria"), list) for r in data["runs"])):
        return None, "judge output does not match the verdict schema"
    return data, None


def _openai(prompt: str, schema: dict, cfg: dict, key: str) -> tuple[dict | None, str | None, dict]:
    base = os.environ.get("VEX_OPENAI_BASE_URL", "https://api.openai.com/v1")
    body = {"model": cfg["model"], "input": [{"role": "user", "content": prompt}],
            "reasoning": {"effort": cfg["effort"]}, "max_output_tokens": MAX_OUTPUT_TOKENS,
            "text": {"format": {"type": "json_schema", "name": "verdict", "schema": strict_schema(schema),
                                "strict": True}}}
    status, data = _post(f"{base}/responses", {"Authorization": f"Bearer {key}"}, body)
    if status != 200 or not isinstance(data, dict):
        return None, _http_error(status, data), {}
    u = data.get("usage") or {}
    usage = {"input": u.get("input_tokens"), "output": u.get("output_tokens"),
             "reasoning": (u.get("output_tokens_details") or {}).get("reasoning_tokens")}
    if data.get("status") != "completed":
        reason = (data.get("incomplete_details") or {}).get("reason")
        return None, f"judge response status {data.get('status')} ({reason})", usage
    parts = [p for item in data.get("output", []) if item.get("type") == "message" for p in item.get("content", [])]
    for p in parts:
        if p.get("type") == "refusal":
            return None, f"judge refused: {p.get('refusal')}", usage
    text = "".join(p.get("text", "") for p in parts if p.get("type") == "output_text")
    return (*_verdict(text), usage)


def _anthropic(prompt: str, schema: dict, cfg: dict, key: str) -> tuple[dict | None, str | None, dict]:
    base = os.environ.get("VEX_ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1")
    body = {"model": cfg["model"], "max_tokens": MAX_OUTPUT_TOKENS,
            "messages": [{"role": "user", "content": prompt}],
            "output_config": {"effort": cfg["effort"], "format": {"type": "json_schema", "schema": strict_schema(schema)}}}
    status, data = _post(f"{base}/messages", {"x-api-key": key, "anthropic-version": ANTHROPIC_VERSION}, body)
    if status != 200 or not isinstance(data, dict):
        return None, _http_error(status, data), {}
    u = data.get("usage") or {}
    usage = {"input": u.get("input_tokens"), "output": u.get("output_tokens"), "reasoning": None}
    if data.get("stop_reason") == "refusal":
        return None, "judge refused", usage
    if data.get("stop_reason") == "max_tokens":
        return None, "judge response hit max_tokens", usage
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    return (*_verdict(text), usage)


def _agy(prompt: str, schema: dict, cfg: dict, cwd: Path) -> tuple[dict | None, str | None, dict]:
    from . import judge as judge_mod
    cwd.mkdir(parents=True, exist_ok=True)
    (cwd / "schema.json").write_text(json.dumps(schema))
    if len(prompt.encode()) > INLINE_MAX:
        (cwd / "judge-prompt.md").write_text(prompt)  # agy -p denies reads outside its workspace (cwd)
        prompt = (f"Read the file {cwd / 'judge-prompt.md'} in full and do exactly what it asks. "
                  "Your answer must follow the JSON schema you were given.")
    cmd = [*shlex.split(os.environ.get("VEX_AGY", "agy")), "-p", prompt, "--model", cfg["model"],
           "--output-format", "json", "--json-schema", str(cwd / "schema.json")]
    try:
        out = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=1800).stdout
    except subprocess.TimeoutExpired:
        return None, "judge timed out", {}
    except OSError as e:
        return None, f"could not start the judge: {e}", {}
    (cwd / "judge.json").write_text(out)
    if not out:
        return None, "judge printed nothing", {}
    verdict, error = judge_mod.parse_output(out)
    return verdict, error, {}


def judge(prompt: str, schema: dict, cfg: dict, cwd: Path) -> tuple[dict | None, str | None, dict]:
    """Returns (verdict, error, usage). Exactly one of verdict and error is set."""
    if cfg["provider"] == "agy":
        return _agy(prompt, schema, cfg, cwd)
    key = api_key(cfg["provider"])
    if not key:
        return None, f"no API key for {cfg['provider']}: set {KEY_ENV[cfg['provider']]} or {_secrets_file()}", {}
    call = _openai if cfg["provider"] == "openai" else _anthropic
    verdict, error, usage = call(prompt, schema, cfg, key)
    if error and key in error:
        error = error.replace(key, "***")
    return verdict, error, usage
