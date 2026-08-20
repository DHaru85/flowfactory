import { http } from "@/api/client";
import type {
  FlowCreateBody,
  FlowOut,
  FlowPatchBody,
  LlmCatalogOut,
  ProfileCatalogOut,
  PublishedFlowCodeOut,
  ToolCatalogOut,
} from "@/types";

export async function listStudioProfiles(): Promise<ProfileCatalogOut[]> {
  const { data } = await http.get<ProfileCatalogOut[]>("/studio/profiles", {
    params: { limit: 50 },
  });
  return data;
}

export async function listStudioLlms(): Promise<LlmCatalogOut[]> {
  const { data } = await http.get<LlmCatalogOut[]>("/studio/llms", { params: { limit: 50 } });
  return data;
}

export async function listStudioTools(): Promise<ToolCatalogOut[]> {
  const { data } = await http.get<ToolCatalogOut[]>("/studio/tools", { params: { limit: 50 } });
  return data;
}

export async function listPublishedFlowCodes(): Promise<PublishedFlowCodeOut[]> {
  const { data } = await http.get<PublishedFlowCodeOut[]>("/studio/flows/published-codes");
  return data;
}

export async function listStudioFlows(status?: string): Promise<FlowOut[]> {
  const { data } = await http.get<FlowOut[]>("/studio/flows", {
    params: { limit: 50, ...(status ? { status } : {}) },
  });
  return data;
}

export async function createStudioFlow(body: FlowCreateBody): Promise<FlowOut> {
  const { data } = await http.post<FlowOut>("/studio/flows", body);
  return data;
}

export async function getStudioFlow(flowId: string): Promise<FlowOut> {
  const { data } = await http.get<FlowOut>(`/studio/flows/${flowId}`);
  return data;
}

export async function patchStudioFlow(flowId: string, body: FlowPatchBody): Promise<FlowOut> {
  const { data } = await http.patch<FlowOut>(`/studio/flows/${flowId}`, body);
  return data;
}

export async function publishStudioFlow(flowId: string): Promise<FlowOut> {
  const { data } = await http.post<FlowOut>(`/studio/flows/${flowId}/publish`);
  return data;
}

export async function newStudioDraft(flowId: string): Promise<FlowOut> {
  const { data } = await http.post<FlowOut>(`/studio/flows/${flowId}/new-draft`);
  return data;
}
