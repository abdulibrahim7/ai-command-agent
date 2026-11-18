"""Strict contract for untrusted action plans."""
import json

from jsonschema import Draft202012Validator

MAX_TEXT = 8192
COMMANDS = ("dir", "ls", "pwd")
PATH = {"type": "string", "minLength": 1, "maxLength": 240}
CONTENT = {"type": "string", "maxLength": MAX_TEXT}
PARAMETERS = {
    "file_read": {"path": PATH},
    "file_write": {"path": PATH, "content": CONTENT},
    "file_append": {"path": PATH, "content": CONTENT},
    "shell_command": {"command": {"enum": list(COMMANDS)}},
    "no_op": {},
}


def object_schema(properties):
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


PLAN_SCHEMA = object_schema({
    "actions": {
        "type": "array", "minItems": 1, "maxItems": 8,
        "items": {"oneOf": [
            object_schema({"type": {"const": kind}, "params": object_schema(params)})
            for kind, params in PARAMETERS.items()
        ]},
    }
})
VALIDATOR = Draft202012Validator(PLAN_SCHEMA)


class PlanError(ValueError):
    """A provider response does not satisfy the action contract."""


def strict_json(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise PlanError("Duplicate JSON key.")
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=unique)


def validate_action_plan(plan):
    """Reject the entire plan if any action is invalid."""
    if not VALIDATOR.is_valid(plan):
        raise PlanError("Invalid action plan.")
    for action in plan["actions"]:
        for value in action["params"].values():
            try:
                if len(value.encode("utf-8")) > MAX_TEXT:
                    raise PlanError("Action field exceeds the UTF-8 size limit.")
            except UnicodeEncodeError:
                raise PlanError("Action field is not valid Unicode.") from None
    return plan["actions"]
