export function parseObjectJson(raw: string, empty: Record<string, unknown>): Record<string, unknown> {
  const text = raw.trim();
  if (text === "") {
    return empty;
  }
  const parsed: unknown = JSON.parse(text);
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new Error("JSON 须为对象");
  }
  return parsed as Record<string, unknown>;
}

export function prettyJson(value: Record<string, unknown>): string {
  return JSON.stringify(value, null, 2);
}
