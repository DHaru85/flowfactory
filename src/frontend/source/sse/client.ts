import type { ChatScene } from "@/api/conversations";
import { getAccessToken } from "@/auth/session";
import { consumeSseBuffer } from "@/sse/parse";
import type { SseFrame } from "@/types";

export async function subscribeConversationEvents(
  scene: ChatScene,
  conversationId: string,
  onFrame: (frame: SseFrame) => void,
  signal: AbortSignal,
): Promise<void> {
  const token = getAccessToken();
  const response = await fetch(`/api/v1/conversations/${scene}/${conversationId}/events`, {
    method: "GET",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    signal,
  });
  if (!response.ok || response.body === null) {
    throw new Error(`SSE 连接失败 (${response.status})`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (!signal.aborted) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const consumed = consumeSseBuffer(buffer);
    buffer = consumed.remainder;
    for (const frame of consumed.frames) {
      onFrame(frame);
    }
  }
}
