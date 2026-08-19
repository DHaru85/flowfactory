"""三槽路径读写：messages / variables.* / metadata.*。"""

from __future__ import annotations


def parse_path(path: str) -> tuple[str, list[str]]:
    raw = path.strip()
    if not raw:
        raise ValueError("路径不能为空")
    parts = raw.split(".")
    channel = parts[0]
    if channel not in {"messages", "variables", "metadata"}:
        raise ValueError(f"非法通道: {channel}")
    if channel == "messages" and len(parts) > 1:
        raise ValueError("messages 不可带内层键")
    return channel, parts[1:]


def get_path(state: dict[str, object], path: str) -> object:
    channel, keys = parse_path(path)
    current: object = state.get(channel)
    if not keys:
        return current
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def set_path(state: dict[str, object], path: str, value: object) -> dict[str, object]:
    channel, keys = parse_path(path)
    result = {
        "messages": list(state.get("messages") or [])
        if isinstance(state.get("messages"), list)
        else [],
        "variables": dict(state.get("variables") or {})
        if isinstance(state.get("variables"), dict)
        else {},
        "metadata": dict(state.get("metadata") or {})
        if isinstance(state.get("metadata"), dict)
        else {},
    }
    if not keys:
        result[channel] = value  # type: ignore[assignment]
        return result
    if channel == "messages":
        raise ValueError("messages 不可按内层键写入")
    cursor: dict[str, object] = result[channel]  # type: ignore[assignment]
    for key in keys[:-1]:
        nested = cursor.get(key)
        if not isinstance(nested, dict):
            nested = {}
            cursor[key] = nested
        cursor = nested
    cursor[keys[-1]] = value
    return result


def map_state(
    source: dict[str, object],
    entries: list[tuple[str, str]],
    *,
    target: dict[str, object] | None = None,
) -> dict[str, object]:
    acc = target or {"messages": [], "variables": {}, "metadata": {}}
    for from_path, to_path in entries:
        acc = set_path(acc, to_path, get_path(source, from_path))
    return acc
