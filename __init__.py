"""Native Hermes extension. Import and registration never read secrets or call Laya."""
from pathlib import Path

from .adapter import classify


TOOL_SCHEMA = {
    "name": "laya_classify",
    "description": (
        "Classify concise text into predefined categories using a configured Laya service. "
        "Returns a complete probability distribution and distinct confidence fields. "
        "Advisory only; does not verify correctness or authorize execution."
    ),
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "state": {"type": "string", "minLength": 1, "maxLength": 2000,
                      "description": "Concise task, article, or response summary. Exclude secrets."},
            "question_name": {"type": "string", "pattern": "^[A-Za-z][A-Za-z0-9_]{0,63}$",
                              "description": "Stable question identifier, e.g. category or relevance."},
            "question": {"type": "string", "minLength": 1, "maxLength": 300,
                         "description": "The classification instruction."},
            "categories": {
                "type": "object", "minProperties": 2, "maxProperties": 16,
                "additionalProperties": {"type": "string", "minLength": 1, "maxLength": 160},
                "description": "Category labels (1-64 characters) mapped to brief descriptions, in intended order.",
            },
        },
        "required": ["state", "question_name", "question", "categories"],
    },
}


def handler(args, *, credential_path=None, **kwargs):
    """Return Hermes's normal JSON tool-result string; never log exceptions."""
    import json
    return json.dumps(classify(args, credential_path=credential_path), ensure_ascii=True, allow_nan=False)


def register(ctx):
    def configured_handler(args, **kwargs):
        import json
        try:
            credential_path = ctx.get_config("credentials_file", "")
        except Exception:
            return json.dumps({"ok": False, "error": {
                "code": "configuration_error", "message": "The Laya plugin settings could not be read.",
            }})
        return handler(args, credential_path=credential_path)

    ctx.register_tool(
        name="laya_classify", toolset="laya", schema=TOOL_SCHEMA,
        handler=configured_handler, description=TOOL_SCHEMA["description"],
    )
    ctx.register_skill(
        name="decisions", path=Path(__file__).parent / "skills" / "decisions" / "SKILL.md",
        description="Use Laya for explicit advisory classification with predefined categories.",
    )
