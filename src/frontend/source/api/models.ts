import { http } from "@/api/client";
import type { LlmCreateBody, LlmOut, LlmPatchBody } from "@/types";

export async function listLlms(): Promise<LlmOut[]> {
  const { data } = await http.get<LlmOut[]>("/models/llms", { params: { limit: 100 } });
  return data;
}

export async function createLlm(body: LlmCreateBody): Promise<LlmOut> {
  const { data } = await http.post<LlmOut>("/models/llms", body);
  return data;
}

export async function patchLlm(id: string, body: LlmPatchBody): Promise<LlmOut> {
  const { data } = await http.patch<LlmOut>(`/models/llms/${id}`, body);
  return data;
}

export async function deactivateLlm(id: string): Promise<LlmOut> {
  const { data } = await http.post<LlmOut>(`/models/llms/${id}/deactivate`);
  return data;
}

export async function deleteLlm(id: string): Promise<void> {
  await http.delete(`/models/llms/${id}`);
}
