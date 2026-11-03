"""Focused standalone checks. Default is offline; --live makes exactly one real request."""
import argparse
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("laya_verification_plugin", ROOT / "__init__.py",
                                            submodule_search_locations=[str(ROOT)])
PLUGIN = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PLUGIN
SPEC.loader.exec_module(PLUGIN)
ADAPTER = sys.modules[SPEC.name + ".adapter"]

EXAMPLE = {
    "state": "A technology company has released a new artificial intelligence processor designed to accelerate AI training and inference in data centers.",
    "question_name": "category",
    "question": "Choose the primary news category for this summary.",
    "categories": {
        "Technology": "Computing, artificial intelligence, processors, and technology products",
        "Business": "Corporate finances, markets, acquisitions, and general business activity",
        "Politics": "Government, elections, public policy, and political affairs",
        "Sports": "Athletic competitions, teams, players, and sporting events",
    },
}

# Explicitly synthetic credential and output fixture; offline tests never read the real file.
FIXTURE_KEY = "synthetic-local-test-token"
FIXTURE_BASE_URL = "https://laya.example.invalid:8000"
FIXTURE = {
    "model": "fixture-model",
    "answers": {"category": {
        "type": "choice", "choice": "Technology",
        "probabilities": {"Technology": .8049, "Business": .1314, "Politics": .0348, "Sports": .0289},
        "confidence": .5234, "answer_confidence": .8049,
    }},
    "usage": {"input_tokens": 90, "output_tokens": 0},
}


class FakeOpener:
    def __init__(self, test, raw, error=None):
        self.test, self.raw, self.error = test, raw, error

    def open(self, request, timeout):
        self.test.assertEqual(request.full_url, FIXTURE_BASE_URL + ADAPTER.ENDPOINT)
        self.test.assertEqual(request.get_method(), "POST")
        self.test.assertEqual(request.get_header("Authorization"), "Bearer " + FIXTURE_KEY)
        self.test.assertEqual(timeout, 30.0)
        payload = json.loads(request.data)
        self.test.assertEqual(payload, {
            "state": EXAMPLE["state"], "questions": {"category": {
                "type": "choice", "instructions": EXAMPLE["question"], "criteria": EXAMPLE["categories"],
            }},
        })
        if self.error:
            raise self.error
        return io.BytesIO(self.raw)


class FocusedTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.config_path = Path(self.directory.name) / "laya.json"
        self.config_path.write_text(json.dumps({
            "schema_version": 1, "provider": "laya",
            "base_url": FIXTURE_BASE_URL, "endpoint": ADAPTER.ENDPOINT,
            "auth_type": "bearer", "method": "POST", "api_key": FIXTURE_KEY,
        }), encoding="utf-8")
        self.proxies = patch.object(ADAPTER.urllib.request, "getproxies", return_value={})
        self.proxies.start()
        self.addCleanup(self.proxies.stop)

    def call(self, fixture=None, error=None, raw=None):
        raw = json.dumps(FIXTURE if fixture is None else fixture).encode() if raw is None else raw
        def build(*handlers):
            self.assertEqual(len(handlers), 1)
            self.assertIsNone(handlers[0].redirect_request(None, None, 302, "redirect", {}, "http://elsewhere/"))
            return FakeOpener(self, raw, error)
        with patch.object(ADAPTER.urllib.request, "build_opener", side_effect=build) as opener:
            result = ADAPTER.classify(deepcopy(EXAMPLE), credential_path=self.config_path)
            self.assertEqual(opener.call_count, 1, "No automatic retry")
        self.assertNotIn(FIXTURE_KEY, json.dumps(result))
        return result

    def assert_error(self, result, code):
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], code)
        self.assertNotIn("category", result)
        self.assertNotIn("probabilities", result)

    def test_sdk_request_and_complete_response(self):
        result = self.call()
        self.assertTrue(result["ok"])
        self.assertEqual(result["category"], "Technology")
        self.assertEqual(result["probabilities"], FIXTURE["answers"]["category"]["probabilities"])
        self.assertEqual(result["confidence"], .5234)
        self.assertEqual(result["answer_confidence"], .8049)

    def test_missing_optional_answer_confidence_stays_null(self):
        fixture = deepcopy(FIXTURE)
        del fixture["answers"]["category"]["answer_confidence"]
        self.assertIsNone(self.call(fixture)["answer_confidence"])

    def test_invalid_distributions_and_answers_are_rejected(self):
        for change in ("missing_label", "extra_label", "bad_sum", "nan", "unknown_choice", "bad_confidence"):
            with self.subTest(change=change):
                fixture = deepcopy(FIXTURE)
                answer = fixture["answers"]["category"]
                if change == "missing_label": del answer["probabilities"]["Sports"]
                elif change == "extra_label": answer["probabilities"]["Other"] = 0
                elif change == "bad_sum": answer["probabilities"]["Sports"] = .5
                elif change == "nan": answer["probabilities"]["Sports"] = float("nan")
                elif change == "unknown_choice": answer["choice"] = "Other"
                else: answer["confidence"] = 2
                self.assert_error(self.call(fixture), "invalid_response")

    def test_non_json_response_is_structured_error(self):
        self.assert_error(self.call(raw=b"not-json"), "invalid_response")

    def test_secret_echo_and_json_escaped_secret_are_withheld(self):
        fixture = deepcopy(FIXTURE)
        fixture["model"] = FIXTURE_KEY
        self.assert_error(self.call(fixture), "invalid_response")
        self.assertTrue(ADAPTER._contains_secret({"model": 'prefix-key"quoted-suffix'}, 'key"quoted'))

    def test_http_errors_do_not_echo_provider_body(self):
        for status in (401, 422, 503, 302):
            with self.subTest(status=status):
                error = urllib.error.HTTPError(FIXTURE_BASE_URL, status, "fixture", {},
                                               io.BytesIO(json.dumps({"detail": FIXTURE_KEY}).encode()))
                result = self.call(error=error)
                self.assert_error(result, "http_error")
                self.assertEqual(result["error"]["status_code"], status)

    def test_timeout_and_connection_errors(self):
        self.assert_error(self.call(error=TimeoutError(FIXTURE_KEY)), "timeout")
        self.assert_error(self.call(error=urllib.error.URLError(FIXTURE_KEY)), "connection_error")

    def test_invalid_input_never_calls_service(self):
        for args in ({}, {**EXAMPLE, "state": "x" * 2001}, {**EXAMPLE, "categories": {"Only": "one"}},
                     {**EXAMPLE, "endpoint": "http://elsewhere"}):
            with self.subTest(args_keys=list(args)):
                with patch.object(ADAPTER, "LayaClient") as client:
                    self.assert_error(ADAPTER.classify(args, credential_path=self.config_path), "invalid_input")
                    client.assert_not_called()

    def test_bad_credentials_file_is_sanitized_and_no_network(self):
        self.config_path.write_text(FIXTURE_KEY, encoding="utf-8")
        with patch.object(ADAPTER, "LayaClient") as client:
            result = ADAPTER.classify(EXAMPLE, credential_path=self.config_path)
            self.assert_error(result, "configuration_error")
            self.assertNotIn(FIXTURE_KEY, json.dumps(result))
            client.assert_not_called()

    def test_configured_origin_and_existing_json_shape(self):
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        for origin in ("http://localhost:8000", "https://laya.example.invalid:8443/"):
            with self.subTest(origin=origin):
                config["base_url"] = origin
                self.config_path.write_text(json.dumps(config), encoding="utf-8")
                self.assertEqual(ADAPTER._config(self.config_path), (origin.rstrip("/"), FIXTURE_KEY))

    def test_unsafe_urls_and_wrong_protocol_are_rejected(self):
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        for origin in ("file:///etc/passwd", "https://user:password@example.invalid", "https://example.invalid?token=x",
                       "https://example.invalid/#fragment", "https://example.invalid/v1/systemone", "https://example.invalid:bad"):
            with self.subTest(origin=origin):
                config["base_url"] = origin
                self.config_path.write_text(json.dumps(config), encoding="utf-8")
                with patch.object(ADAPTER, "LayaClient") as client:
                    self.assert_error(ADAPTER.classify(EXAMPLE, credential_path=self.config_path), "configuration_error")
                    client.assert_not_called()
        config["base_url"] = FIXTURE_BASE_URL
        config["endpoint"] = "/wrong-route"
        self.config_path.write_text(json.dumps(config), encoding="utf-8")
        self.assert_error(ADAPTER.classify(EXAMPLE, credential_path=self.config_path), "configuration_error")

    def test_no_implicit_credential_path(self):
        self.assert_error(ADAPTER.classify(EXAMPLE), "configuration_error")
        self.assert_error(ADAPTER.classify(EXAMPLE, credential_path="relative/laya.json"), "configuration_error")

    def test_example_config_schema_is_accepted_without_network(self):
        template = json.loads((ROOT / "laya.example.json").read_text(encoding="utf-8"))
        self.config_path.write_text(json.dumps(template), encoding="utf-8")
        base_url, key = ADAPTER._config(self.config_path)
        self.assertEqual(base_url, template["base_url"].rstrip("/"))
        self.assertEqual(key, template["api_key"])

    def test_registered_handler_reads_credentials_from_settings(self):
        test = self
        class Context:
            def get_config(self, key, default=None):
                test.assertEqual(key, "credentials_file")
                return str(test.config_path)
            def register_tool(self, **kwargs):
                self.handler = kwargs["handler"]
            def register_skill(self, **kwargs):
                pass
        context = Context()
        PLUGIN.register(context)
        with patch.object(PLUGIN, "classify", return_value={"ok": False, "error": {"code": "fixture"}}) as classify:
            context.handler(deepcopy(EXAMPLE))
            classify.assert_called_once_with(EXAMPLE, credential_path=str(self.config_path))

    def test_proxy_configuration_prevents_credential_transmission(self):
        with patch.object(ADAPTER.urllib.request, "getproxies", return_value={"https": "http://proxy.example.invalid"}):
            with patch.object(ADAPTER, "LayaClient") as client:
                self.assert_error(ADAPTER.classify(EXAMPLE, credential_path=self.config_path), "proxy_configured")
                client.assert_not_called()

    def test_unexpected_exception_is_sanitized(self):
        def broken(**kwargs):
            raise RuntimeError(FIXTURE_KEY)
        result = ADAPTER.classify(EXAMPLE, credential_path=self.config_path, client_factory=broken)
        self.assert_error(result, "internal_error")
        self.assertNotIn(FIXTURE_KEY, json.dumps(result))

    def test_registration_contract_without_loading_hermes(self):
        class Context:
            def get_config(self, key, default=None):
                return default
            def register_tool(self, name, toolset, schema, handler, check_fn=None, requires_env=None,
                              is_async=False, description="", emoji="", override=False):
                self.tool = (name, toolset, schema, handler, override)
            def register_skill(self, name, path, description="", frontmatter=None):
                self.skill = (name, path)
        context = Context()
        with patch.object(ADAPTER, "LayaClient") as client, patch.object(ADAPTER, "_config") as config:
            PLUGIN.register(context)
            client.assert_not_called()
            config.assert_not_called()
        self.assertEqual(context.tool[0:2], ("laya_classify", "laya"))
        self.assertFalse(context.tool[4])
        self.assertEqual(context.skill[0], "decisions")
        self.assertTrue(context.skill[1].is_file())
        self.assert_error(json.loads(context.tool[3]({})), "invalid_input")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="One authorized request with the real local credential")
    parser.add_argument("--credentials", type=Path, help="Absolute path to a private JSON file; required for --live")
    parser.add_argument("--scratch-dir", type=Path, help="Existing writable directory for temporary synthetic offline fixtures")
    args = parser.parse_args()
    if args.live:
        if not args.credentials or not args.credentials.is_absolute():
            parser.error("--live requires --credentials with an absolute path")
        # Exercise the actual Hermes handler, not a separate HTTP implementation.
        result = json.loads(PLUGIN.handler(deepcopy(EXAMPLE), credential_path=args.credentials))
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0 if result.get("ok") else 1
    if args.scratch_dir:
        if not args.scratch_dir.is_dir():
            parser.error("--scratch-dir must be an existing directory")
        tempfile.tempdir = str(args.scratch_dir.resolve())
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(FocusedTests)
    return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
