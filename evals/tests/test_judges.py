import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from harness import judge as judge_mod  # noqa: E402
from harness import judges  # noqa: E402

VERDICT = {"runs": [{"label": "R1", "criteria": [{"name": "c1", "pass": True, "note": "ok"}]}]}


class FakeAPI:
    """A local HTTP server that records each request and answers from a queue of (status, headers, body)."""

    def __init__(self):
        self.requests, self.replies, self.handler = [], [], None
        api = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                api.requests.append({"path": self.path, "headers": dict(self.headers), "body": body})
                item = api.handler(api.requests[-1]) if api.handler else api.replies.pop(0)
                if item is None:  # drop the connection without answering
                    self.close_connection = True
                    return
                status, headers, reply = item
                data = reply if isinstance(reply, bytes) else json.dumps(reply).encode()
                self.send_response(status)
                for k, v in headers.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/v1"

    def close(self):
        self.server.shutdown()


def openai_reply(text=None, status="completed", refusal=None, incomplete=None):
    part = {"type": "refusal", "refusal": refusal} if refusal else {"type": "output_text", "text": text}
    body = {"status": status, "output": [{"type": "reasoning"}, {"type": "message", "content": [part]}],
            "usage": {"input_tokens": 100, "output_tokens": 20, "output_tokens_details": {"reasoning_tokens": 5}}}
    if incomplete:
        body["incomplete_details"] = {"reason": incomplete}
    return body


class JudgesTest(unittest.TestCase):
    def setUp(self):
        self.api = FakeAPI()
        self.addCleanup(self.api.close)
        self.tmp = Path(tempfile.mkdtemp(prefix="judges-"))
        self.env = {"VEX_OPENAI_BASE_URL": self.api.url, "VEX_ANTHROPIC_BASE_URL": self.api.url,
                    "OPENAI_API_KEY": "sk-test-openai", "ANTHROPIC_API_KEY": "sk-ant-test",
                    "VEX_SECRETS": str(self.tmp / "none.env")}
        self.old = {k: os.environ.get(k) for k in [*self.env, "VEX_JUDGE_PROVIDER", "VEX_JUDGE_MODEL", "VEX_JUDGE_EFFORT"]}
        os.environ.update(self.env)
        for k in ("VEX_JUDGE_PROVIDER", "VEX_JUDGE_MODEL", "VEX_JUDGE_EFFORT"):
            os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def call(self, provider="openai", model="gpt-6.2-sol"):
        cfg = {"provider": provider, "model": model, "effort": "medium"}
        return judges.judge("grade these runs", judge_mod.SCHEMA, cfg, self.tmp)

    def test_openai_request_shape(self):
        self.api.replies.append((200, {}, openai_reply(json.dumps(VERDICT))))
        self.call()
        req = self.api.requests[0]
        self.assertEqual(req["path"], "/v1/responses")
        self.assertEqual(req["headers"]["Authorization"], "Bearer sk-test-openai")
        body = req["body"]
        self.assertEqual(body["model"], "gpt-6.2-sol")
        self.assertEqual(body["reasoning"], {"effort": "medium"})
        self.assertEqual(body["text"]["format"]["type"], "json_schema")
        self.assertTrue(body["text"]["format"]["strict"])
        self.assertIn("grade these runs", json.dumps(body["input"]))

    def test_openai_parses_output_text(self):
        self.api.replies.append((200, {}, openai_reply(json.dumps(VERDICT))))
        verdict, error, usage = self.call()
        self.assertIsNone(error)
        self.assertEqual(verdict, VERDICT)
        self.assertEqual(usage, {"input": 100, "output": 20, "reasoning": 5})

    def test_anthropic_request_shape_and_parse(self):
        self.api.replies.append((200, {}, {"stop_reason": "end_turn", "content": [
            {"type": "thinking", "thinking": ""}, {"type": "text", "text": json.dumps(VERDICT)}],
            "usage": {"input_tokens": 80, "output_tokens": 30}}))
        verdict, error, usage = self.call("anthropic", "claude-opus-5-5")
        self.assertIsNone(error)
        self.assertEqual(verdict, VERDICT)
        req = self.api.requests[0]
        self.assertEqual(req["path"], "/v1/messages")
        self.assertEqual(req["headers"]["X-Api-Key"], "sk-ant-test")
        self.assertIn("Anthropic-Version", req["headers"])
        self.assertEqual(req["body"]["output_config"]["format"]["type"], "json_schema")
        self.assertEqual(req["body"]["output_config"]["effort"], "medium")

    def test_refusal_incomplete_and_garbage_are_errors(self):
        cases = [
            openai_reply(refusal="I can't help with that"),
            openai_reply(json.dumps(VERDICT), status="incomplete", incomplete="max_output_tokens"),
            openai_reply("not json"),
            openai_reply(json.dumps({"runs": "nope"})),
        ]
        for reply in cases:
            self.api.replies.append((200, {}, reply))
            verdict, error, _ = self.call()
            self.assertIsNone(verdict, reply)
            self.assertTrue(error, reply)
        self.api.replies.append((400, {}, {"error": {"message": "bad model"}}))
        verdict, error, _ = self.call()
        self.assertIsNone(verdict)
        self.assertIn("bad model", error)

    def test_retry_once_on_429(self):
        self.api.replies += [(429, {"retry-after": "0"}, {"error": {"message": "slow down"}}),
                             (200, {}, openai_reply(json.dumps(VERDICT)))]
        verdict, error, _ = self.call()
        self.assertIsNone(error)
        self.assertEqual(len(self.api.requests), 2)

    def test_connection_reset_is_a_judge_error(self):
        self.api.replies += [None, None]
        verdict, error, _ = self.call()
        self.assertIsNone(verdict)
        self.assertIn("judge call failed", error)

    def test_http_date_retry_after_and_string_error_body(self):
        judges.RETRY_FALLBACK_S = 0
        self.addCleanup(setattr, judges, "RETRY_FALLBACK_S", 30)
        self.api.replies += [(429, {"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT"}, {"error": "bad"}),
                             (200, {}, openai_reply(json.dumps(VERDICT)))]
        verdict, error, _ = self.call()
        self.assertIsNone(error)
        self.api.replies.append((400, {}, {"error": "plain string"}))
        verdict, error, _ = self.call()
        self.assertIn("plain string", error)

    def test_no_retry_after_the_work_may_be_done(self):
        self.api.replies.append((200, {}, b"not json"))
        verdict, error, _ = self.call()
        self.assertIsNone(verdict)
        self.assertEqual(len(self.api.requests), 1)
        self.api.replies.append((502, {}, {"error": {"message": "bad gateway"}}))
        verdict, error, _ = self.call()
        self.assertEqual(len(self.api.requests), 2)

    def test_retry_wait_is_capped(self):
        self.assertEqual(judges._retry_wait("100000"), judges.MAX_RETRY_WAIT_S)
        self.assertEqual(judges._retry_wait("2"), 2)

    def test_partial_key_is_scrubbed(self):
        self.api.replies.append((401, {}, {"error": {"message": "Incorrect API key provided: sk-tes*******5678."}}))
        verdict, error, _ = self.call()
        self.assertNotIn("sk-", error)
        self.assertNotIn("5678", error)

    def test_openai_schema_is_strict(self):
        def check(node):
            if isinstance(node, dict):
                if node.get("type") == "object":
                    self.assertIs(node.get("additionalProperties"), False)
                    self.assertEqual(sorted(node.get("required", [])), sorted(node.get("properties", {})))
                for v in node.values():
                    check(v)
            elif isinstance(node, list):
                for v in node:
                    check(v)
        check(judges.strict_schema(judge_mod.SCHEMA))

    def test_env_overrides_config(self):
        repo = self.tmp / "repo"
        (repo / "evals").mkdir(parents=True)
        (repo / "evals/judge.json").write_text(json.dumps({"provider": "openai", "model": "gpt-6.2-sol", "effort": "medium"}))
        self.assertEqual(judges.load_config(repo)["model"], "gpt-6.2-sol")
        os.environ["VEX_JUDGE_PROVIDER"], os.environ["VEX_JUDGE_MODEL"] = "anthropic", "claude-opus-5-5"
        cfg = judges.load_config(repo)
        self.assertEqual((cfg["provider"], cfg["model"], cfg["effort"]), ("anthropic", "claude-opus-5-5", "medium"))

    def test_secrets_file_permissions(self):
        os.environ.pop("OPENAI_API_KEY")
        secrets = self.tmp / "secrets.env"
        secrets.write_text("# comment\nOPENAI_API_KEY=sk-from-file\n")
        os.environ["VEX_SECRETS"] = str(secrets)
        secrets.chmod(0o644)
        with self.assertRaises(judges.JudgeConfigError):
            judges.api_key("openai")
        secrets.chmod(0o600)
        self.assertEqual(judges.api_key("openai"), "sk-from-file")
        os.environ.pop("ANTHROPIC_API_KEY")
        self.assertIsNone(judges.api_key("anthropic"))

    def test_agy_provider_uses_existing_path(self):
        fake = self.tmp / "agy.py"
        fake.write_text("import json,sys\nprint(json.dumps({'status':'SUCCESS','structured_output':%r}))\n" % VERDICT)
        os.environ["VEX_AGY"] = f"{sys.executable} {fake}"
        try:
            verdict, error, _ = self.call("agy", "claude-opus-5-5-high")
        finally:
            os.environ.pop("VEX_AGY")
        self.assertIsNone(error)
        self.assertEqual(verdict, VERDICT)


if __name__ == "__main__":
    unittest.main()
