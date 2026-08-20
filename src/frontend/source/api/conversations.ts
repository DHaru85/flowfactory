import { http } from "@/api/client";
import type {
  ConversationDetailOut,
  ConversationOut,
  HitlPendingOut,
  HitlResumeBody,
  HitlResumeOut,
  MessageOut,
  SendMessageOut,
} from "@/types";

export type ChatScene = "planner" | "workflow";

export async function listConversations(scene: ChatScene): Promise<ConversationOut[]> {
  const { data } = await http.get<ConversationOut[]>(`/conversations/${scene}`, {
    params: { limit: 50 },
  });
  return data;
}

export async function getConversation(
  scene: ChatScene,
  id: string,
): Promise<ConversationDetailOut> {
  const { data } = await http.get<ConversationDetailOut>(`/conversations/${scene}/${id}`);
  return data;
}

export async function createPlannerConversation(body: {
  title: string | null;
  profile_id: string;
}): Promise<ConversationDetailOut> {
  const { data } = await http.post<ConversationDetailOut>("/conversations/planner", body);
  return data;
}

export async function createWorkflowConversation(body: {
  title: string | null;
  flow_id: string | null;
}): Promise<ConversationOut> {
  const { data } = await http.post<ConversationOut>("/conversations/workflow", body);
  return data;
}

export async function listMessages(scene: ChatScene, id: string): Promise<MessageOut[]> {
  const { data } = await http.get<MessageOut[]>(`/conversations/${scene}/${id}/messages`, {
    params: { limit: 200 },
  });
  return data;
}

export async function sendPlannerMessage(body: {
  conversation_id: string | null;
  profile_id: string | null;
  content: string;
}): Promise<SendMessageOut> {
  const { data } = await http.post<SendMessageOut>("/conversations/planner/messages", body);
  return data;
}

export async function sendWorkflowMessage(body: {
  conversation_id: string | null;
  flow_id: string | null;
  content: string;
}): Promise<SendMessageOut> {
  const { data } = await http.post<SendMessageOut>("/conversations/workflow/messages", {
    ...body,
    app_key: "workflow",
  });
  return data;
}

export async function listHitlPendings(runId?: string): Promise<HitlPendingOut[]> {
  const { data } = await http.get<HitlPendingOut[]>("/conversations/workflow/hitl-pendings", {
    params: runId ? { run_id: runId } : {},
  });
  return data;
}

export async function resumeHitl(hitlId: string, body: HitlResumeBody): Promise<HitlResumeOut> {
  const { data } = await http.post<HitlResumeOut>(
    `/conversations/workflow/hitl-pendings/${hitlId}/resume`,
    body,
  );
  return data;
}
