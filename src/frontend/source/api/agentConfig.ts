import { http } from "@/api/client";
import type {
  BeatOut,
  BindingItem,
  BindingPutBody,
  McpOut,
  McpTransport,
  ProfileOut,
  SkillOut,
  ToolKind,
  ToolOut,
} from "@/types";

export async function listProfiles(): Promise<ProfileOut[]> {
  const { data } = await http.get<ProfileOut[]>("/agent-config/profiles", { params: { limit: 100 } });
  return data;
}

export async function createProfile(body: {
  name: string;
  system_prompt: string;
  default_llm_id: string | null;
  skill_ids: string[];
}): Promise<ProfileOut> {
  const { data } = await http.post<ProfileOut>("/agent-config/profiles", body);
  return data;
}

export async function patchProfile(
  id: string,
  body: Partial<Pick<ProfileOut, "name" | "system_prompt" | "default_llm_id" | "skill_ids">>,
): Promise<ProfileOut> {
  const { data } = await http.patch<ProfileOut>(`/agent-config/profiles/${id}`, body);
  return data;
}

export async function listSkills(): Promise<SkillOut[]> {
  const { data } = await http.get<SkillOut[]>("/agent-config/skills", { params: { limit: 100 } });
  return data;
}

export async function createSkill(body: {
  name: string;
  description: string | null;
  tool_ids: string[];
  prompt_template: string | null;
}): Promise<SkillOut> {
  const { data } = await http.post<SkillOut>("/agent-config/skills", body);
  return data;
}

export async function patchSkill(
  id: string,
  body: Partial<Pick<SkillOut, "name" | "description" | "tool_ids" | "prompt_template">>,
): Promise<SkillOut> {
  const { data } = await http.patch<SkillOut>(`/agent-config/skills/${id}`, body);
  return data;
}

export async function listTools(): Promise<ToolOut[]> {
  const { data } = await http.get<ToolOut[]>("/agent-config/tools", { params: { limit: 100 } });
  return data;
}

export async function createTool(body: {
  name: string;
  kind: ToolKind;
  schema: Record<string, unknown>;
  config: Record<string, unknown>;
  mcp_server_id: string | null;
}): Promise<ToolOut> {
  const { data } = await http.post<ToolOut>("/agent-config/tools", body);
  return data;
}

export async function patchTool(
  id: string,
  body: {
    name?: string;
    kind?: ToolKind;
    schema?: Record<string, unknown>;
    config?: Record<string, unknown>;
    mcp_server_id?: string | null;
  },
): Promise<ToolOut> {
  const { data } = await http.patch<ToolOut>(`/agent-config/tools/${id}`, body);
  return data;
}

export async function listMcps(): Promise<McpOut[]> {
  const { data } = await http.get<McpOut[]>("/agent-config/mcp-servers", { params: { limit: 100 } });
  return data;
}

export async function createMcp(body: {
  name: string;
  transport: McpTransport;
  config: Record<string, unknown>;
  is_active: boolean;
}): Promise<McpOut> {
  const { data } = await http.post<McpOut>("/agent-config/mcp-servers", body);
  return data;
}

export async function patchMcp(
  id: string,
  body: Partial<Pick<McpOut, "name" | "transport" | "config" | "is_active">>,
): Promise<McpOut> {
  const { data } = await http.patch<McpOut>(`/agent-config/mcp-servers/${id}`, body);
  return data;
}

export async function listBeats(): Promise<BeatOut[]> {
  const { data } = await http.get<BeatOut[]>("/agent-config/beat-tasks", { params: { limit: 100 } });
  return data;
}

export async function createBeat(body: {
  flow_id: string | null;
  profile_id: string | null;
  cron: string;
  input_payload: Record<string, unknown>;
  is_enabled: boolean;
}): Promise<BeatOut> {
  const { data } = await http.post<BeatOut>("/agent-config/beat-tasks", body);
  return data;
}

export async function patchBeat(
  id: string,
  body: { cron?: string; input_payload?: Record<string, unknown> },
): Promise<BeatOut> {
  const { data } = await http.patch<BeatOut>(`/agent-config/beat-tasks/${id}`, body);
  return data;
}

export async function enableBeat(id: string): Promise<BeatOut> {
  const { data } = await http.post<BeatOut>(`/agent-config/beat-tasks/${id}/enable`);
  return data;
}

export async function disableBeat(id: string): Promise<BeatOut> {
  const { data } = await http.post<BeatOut>(`/agent-config/beat-tasks/${id}/disable`);
  return data;
}

export type ConfigResource = "profiles" | "skills" | "tools" | "mcp-servers";

export async function getBindings(kind: ConfigResource, id: string): Promise<BindingItem[]> {
  const { data } = await http.get<BindingItem[]>(`/agent-config/${kind}/${id}/bindings`);
  return data;
}

export async function putBindings(
  kind: ConfigResource,
  id: string,
  body: BindingPutBody,
): Promise<BindingItem[]> {
  const { data } = await http.put<BindingItem[]>(`/agent-config/${kind}/${id}/bindings`, body);
  return data;
}

export async function deleteProfile(id: string): Promise<void> {
  await http.delete(`/agent-config/profiles/${id}`);
}

export async function deleteSkill(id: string): Promise<void> {
  await http.delete(`/agent-config/skills/${id}`);
}

export async function deleteTool(id: string): Promise<void> {
  await http.delete(`/agent-config/tools/${id}`);
}

export async function deleteMcp(id: string): Promise<void> {
  await http.delete(`/agent-config/mcp-servers/${id}`);
}

export async function deleteBeat(id: string): Promise<void> {
  await http.delete(`/agent-config/beat-tasks/${id}`);
}
