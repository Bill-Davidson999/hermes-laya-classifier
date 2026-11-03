"""One explicit classification via the unmodified, privately bundled upstream SDK."""
import json
import math
from pathlib import Path
import re
import time
import urllib.parse
import urllib.request

from ._vendor.laya_client import (
    LayaAPIError, LayaClient, LayaConnectionError, LayaResponseError,
    LayaTimeoutError, LayaValidationError,
)

ENDPOINT = "/v1/systemone"
TIMEOUT_SECONDS = 30.0


class InputError(ValueError):
    pass


class ConfigError(ValueError):
    pass


def _error(code, message, **extra):
    return {"ok": False, "error": {"code": code, "message": message, **extra}}


def _text(value, maximum):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= maximum


def _questions(args):
    if not isinstance(args, dict) or set(args) != {"state", "question_name", "question", "categories"}:
        raise InputError()
    name = args["question_name"]
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", name):
        raise InputError()
    if not _text(args["state"], 2000) or not _text(args["question"], 300):
        raise InputError()
    categories = args["categories"]
    if not isinstance(categories, dict) or not 2 <= len(categories) <= 16:
        raise InputError()
    if not all(_text(label, 64) and _text(description, 160) for label, description in categories.items()):
        raise InputError()
    # Size caps bound transport, not the model's tokenizer. Keep descriptions much shorter in practice.
    questions = {name: {"type": "choice", "instructions": args["question"], "criteria": categories}}
    try:
        encoded = json.dumps({"state": args["state"], "questions": questions}, allow_nan=False).encode("utf-8")
        if len(encoded) > 8192:
            raise InputError()
    except (ValueError, UnicodeError):
        raise InputError() from None
    return questions


def _config(path):
    # The path comes from trusted plugin settings or the standalone CLI, never tool arguments.
    try:
        if not isinstance(path, (str, Path)) or not str(path).strip():
            raise ConfigError()
        path = Path(path).expanduser()
        if not path.is_absolute():
            raise ConfigError()
        if path.stat().st_size > 16384:
            raise ConfigError()
        config = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        raise ConfigError() from None
    if not isinstance(config, dict):
        raise ConfigError()
    if (config.get("endpoint") != ENDPOINT
            or str(config.get("auth_type", "")).lower() != "bearer"
            or str(config.get("method", "")).upper() != "POST"):
        raise ConfigError()
    base_url = config.get("base_url")
    if not isinstance(base_url, str) or any(ord(c) <= 32 or ord(c) == 127 for c in base_url):
        raise ConfigError()
    try:
        base_url.encode("ascii")
        parsed = urllib.parse.urlsplit(base_url)
        if (parsed.scheme not in ("http", "https") or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.path not in ("", "/") or "?" in base_url or "#" in base_url):
            raise ConfigError()
        parsed.port
    except (ValueError, UnicodeError):
        raise ConfigError() from None
    key = config.get("api_key")
    if not isinstance(key, str) or not key or any(ord(c) < 33 or ord(c) > 126 for c in key):
        raise ConfigError()
    return base_url.rstrip("/"), key


def _probability(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1


def _contains_secret(value, key):
    if isinstance(value, str):
        return key in value
    if isinstance(value, dict):
        return any(_contains_secret(k, key) or _contains_secret(v, key) for k, v in value.items())
    if isinstance(value, list):
        return any(_contains_secret(v, key) for v in value)
    return False


def _result(raw, args):
    try:
        answer = raw["answers"][args["question_name"]]
        probs = answer["probabilities"]
        labels = args["categories"]
        if (answer.get("type") != "choice" or not isinstance(probs, dict)
                or set(probs) != set(labels) or not all(_probability(v) for v in probs.values())
                or abs(sum(probs.values()) - 1.0) > len(labels) * 0.00005 + 0.000001
                or answer.get("choice") not in labels
                or not _probability(answer.get("confidence"))):
            raise LayaResponseError("Invalid classification")
        for field in ("answer_confidence", "x_jev_confidence"):
            if field in answer and not _probability(answer[field]):
                raise LayaResponseError("Invalid confidence")
        if not isinstance(raw.get("model"), str) or len(raw["model"]) > 200:
            raise LayaResponseError("Invalid model")
        usage = raw.get("usage")
        if not isinstance(usage, dict) or any(type(usage.get(k)) is not int or usage[k] < 0
                                              for k in ("input_tokens", "output_tokens")):
            raise LayaResponseError("Invalid usage")
        result = {
            "ok": True, "advisory_only": True, "question_name": args["question_name"],
            "category": answer["choice"], "probabilities": {label: probs[label] for label in labels},
            "confidence": answer["confidence"], "answer_confidence": answer.get("answer_confidence"),
            "model": raw["model"],
            "usage": {k: usage[k] for k in ("input_tokens", "output_tokens")},
        }
        if "x_jev_confidence" in answer:
            result["x_jev_confidence"] = answer["x_jev_confidence"]
        return result
    except (KeyError, TypeError, AttributeError):
        raise LayaResponseError("Invalid classification response") from None


def classify(args, *, credential_path=None, client_factory=None):
    """Return only bounded classification data or a sanitized structured error.

    Keyword injection is a local verification seam, never exposed in the Hermes schema.
    No retries, remote fallback, logging, approvals, hooks, or action execution.
    """
    started = time.perf_counter()
    try:
        questions = _questions(args)
        base_url, key = _config(credential_path)
        # Upstream urllib honors OS/environment proxies. Refuse proxy configuration rather than
        # risk forwarding the local service's bearer elsewhere or modifying global transport state.
        proxies = urllib.request.getproxies()
        if proxies.get(urllib.parse.urlsplit(base_url).scheme) or proxies.get("all"):
            return _error("proxy_configured", "Direct Laya access is required; a proxy for this connection is configured.")
        factory = LayaClient if client_factory is None else client_factory
        client = factory(base_url=base_url, api_key=key, timeout=TIMEOUT_SECONDS)
        raw = client.predict(args["state"], questions)
        result = _result(raw, args)
        if _contains_secret(result, key):
            return _error("invalid_response", "Laya returned an unsafe classification response.")
        result["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
        return result
    except InputError:
        return _error("invalid_input", "Provide concise state, a named question, and 2-16 described categories within documented limits.")
    except ConfigError:
        return _error("configuration_error", "The local Laya credential configuration is unavailable or invalid.")
    except LayaTimeoutError:
        return _error("timeout", "Stopped waiting for Laya; server processing may still finish.")
    except LayaAPIError as exc:
        return _error("http_error", "Laya returned an unsuccessful HTTP response.", status_code=exc.status_code)
    except LayaConnectionError:
        return _error("connection_error", "Could not complete a direct connection to Laya.")
    except LayaResponseError:
        return _error("invalid_response", "Laya returned an invalid classification response.")
    except LayaValidationError:
        return _error("request_error", "The SDK rejected the Laya request or connection settings.")
    except Exception:
        # Never emit exception text, request headers, provider detail, or credential contents.
        return _error("internal_error", "The classification could not be completed.")
