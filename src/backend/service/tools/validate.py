"""JSON Schema 参数校验。"""

from __future__ import annotations

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError


def validate_tool_arguments(
    schema: dict[str, object],
    arguments: dict[str, object],
) -> str | None:
    """通过返回 None；失败返回错误信息。"""
    if not schema:
        return None
    try:
        validator = Draft202012Validator(schema)
        validator.validate(arguments)
    except SchemaError as exc:
        return f"工具 schema 非法: {exc.message}"
    except ValidationError as exc:
        path = ".".join(str(part) for part in exc.absolute_path)
        if path:
            return f"参数校验失败 ({path}): {exc.message}"
        return f"参数校验失败: {exc.message}"
    return None
