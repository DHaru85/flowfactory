import type { SseFrame } from "@/types";

/** 将 SSE 文本块解析为帧；不完整尾部返回 remainder。 */
export function consumeSseBuffer(buffer: string): { frames: SseFrame[]; remainder: string } {
  const frames: SseFrame[] = [];
  const parts = buffer.split("\n\n");
  const remainder = parts.pop() ?? "";
  for (const part of parts) {
    const trimmed = part.trim();
    if (trimmed === "" || trimmed.startsWith(":")) {
      continue;
    }
    let event = "message";
    let id: string | null = null;
    const dataLines: string[] = [];
    for (const line of part.split("\n")) {
      if (line.startsWith("event:")) {
        event = line.slice(6).trim();
      } else if (line.startsWith("id:")) {
        id = line.slice(3).trim();
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice(5).trim());
      }
    }
    let data: Record<string, unknown> = {};
    const raw = dataLines.join("\n");
    if (raw) {
      try {
        const parsed: unknown = JSON.parse(raw);
        if (typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)) {
          data = parsed as Record<string, unknown>;
        }
      } catch {
        data = { raw };
      }
    }
    frames.push({ event, id, data });
  }
  return { frames, remainder };
}
