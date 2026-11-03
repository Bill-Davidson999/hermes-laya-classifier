"""Isolated Hermes loader/skill/configuration test. No live Laya or real credential file."""
import argparse
from contextlib import ExitStack
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import socket
import sys
import tempfile
import threading
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent


def verify(scratch=None):
    sys.dont_write_bytecode = True
    with tempfile.TemporaryDirectory(prefix="laya-hermes-check-", dir=scratch) as temporary:
        home = Path(temporary).resolve()
        installed = home / "plugins" / "laya-classifier"
        shutil.copytree(ROOT, installed, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
        bundled = home / "empty-bundled"
        bundled.mkdir()
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {
                "HERMES_HOME": str(home), "HERMES_BUNDLED_PLUGINS": str(bundled),
                "HERMES_ENABLE_PROJECT_PLUGINS": "0", "PYTHONDONTWRITEBYTECODE": "1",
            }))
            # Use Hermes's actual YAML codec, parser, registries and loader in this child process.
            import hermes_yaml
            from hermes_cli.plugin_dev import doctor_plugin
            from hermes_cli.plugins import PluginManager
            from tools.registry import registry

            doctor = doctor_plugin(installed)
            if not doctor.ok or doctor.registered_tools != ("laya_classify",) or doctor.registered_hooks:
                raise RuntimeError("Hermes Plugin Doctor failed")
            received = []

            class Service(BaseHTTPRequestHandler):
                def log_message(self, *args):
                    pass

                def do_POST(self):
                    payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                    received.append((self.path, self.headers.get("Authorization"), payload))
                    response = {
                        "model": "synthetic-model", "answers": {"category": {
                            "type": "choice", "choice": "Technology",
                            "probabilities": {"Technology": .8, "Business": .2},
                            "confidence": .28, "answer_confidence": .8,
                        }}, "usage": {"input_tokens": 10, "output_tokens": 0},
                    }
                    encoded = json.dumps(response).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(encoded)))
                    self.end_headers()
                    self.wfile.write(encoded)

            server = ThreadingHTTPServer(("localhost", 0), Service)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                credential_path = home / "private" / "laya.json"
                credential_path.parent.mkdir()
                credential_path.write_text(json.dumps({
                    "schema_version": 1, "provider": "laya", "api_key": "synthetic-install-test-token",
                    "base_url": f"http://localhost:{server.server_port}", "endpoint": "/v1/systemone",
                    "auth_type": "bearer", "method": "POST",
                }), encoding="utf-8")
                config = {"plugins": {"enabled": ["laya-classifier"], "entries": {
                    "laya-classifier": {"settings": {"credentials_file": str(credential_path)}}}}}
                (home / "config.yaml").write_text(hermes_yaml.safe_dump(config), encoding="utf-8")
                manager = PluginManager()
                # The real per-home scanner and admission gate load only the isolated copy.
                manager.discover_and_load()
                try:
                    loaded = manager._plugins.get("laya-classifier")
                    if not loaded or not loaded.enabled or loaded.error:
                        raise RuntimeError("Isolated plugin did not load")
                    entry = registry.get_entry("laya_classify", scope=manager.scope_key)
                    skill = manager.find_plugin_skill("laya-classifier:decisions")
                    if entry is None or skill is None or not skill.is_file():
                        raise RuntimeError("Tool or bundled skill not discoverable")
                    args = {"state": "A company releases an AI processor.", "question_name": "category",
                            "question": "Choose the primary topic.", "categories": {
                                "Technology": "Computers and processors", "Business": "Corporate finance"}}
                    # No real service/token. Permit socket connections only to this fixture port.
                    original_connect = socket.socket.connect
                    def fixture_only_connect(connection, address):
                        if not isinstance(address, tuple) or address[0] not in ("127.0.0.1", "::1") or address[1] != server.server_port:
                            raise RuntimeError("Network outside the local fixture is disabled")
                        return original_connect(connection, address)
                    with patch("urllib.request.getproxies", return_value={}), patch.object(socket.socket, "connect", fixture_only_connect):
                        result = json.loads(entry.handler(args))
                    if (not result.get("ok") or result.get("category") != "Technology"
                            or result.get("probabilities") != {"Technology": .8, "Business": .2}
                            or result.get("confidence") != .28 or result.get("answer_confidence") != .8
                            or len(received) != 1 or received[0][0] != "/v1/systemone"
                            or received[0][1] != "Bearer synthetic-install-test-token"):
                        raise RuntimeError("Isolated configured classification failed")
                    # Remove only this disposable fixture, then verify a structured configuration error.
                    credential_path.unlink()
                    failure = json.loads(entry.handler(args))
                    if failure.get("ok") or failure.get("error", {}).get("code") != "configuration_error" or "category" in failure:
                        raise RuntimeError("Missing-file failure was not structured")
                    return {"plugin_doctor": "passed", "doctor_findings": len(doctor.findings),
                            "version": doctor.manifest.version, "tools": [entry.name],
                            "skill": "laya-classifier:decisions", "isolated_configured_http_call": "passed",
                            "missing_credentials_error": "passed", "real_credentials_used": False}
                finally:
                    manager.unload()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch-dir", type=Path, help="Existing writable directory for a disposable Hermes home")
    args = parser.parse_args()
    if args.scratch_dir:
        tempfile.tempdir = str(args.scratch_dir.resolve())
    print(json.dumps(verify(args.scratch_dir), indent=2))
