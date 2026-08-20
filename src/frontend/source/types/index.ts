/** 与 docs/design/data_schema_client.md 对齐的传输对象。 */

export interface ErrorBody {
  code: string;
  message: string;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  token_type: "Bearer";
}

export interface LoginBody {
  username: string;
  password: string;
}

export interface RegisterBody {
  username: string;
  password: string;
  display_name?: string | null;
}

export interface MeOut {
  id: string;
  username: string;
  organization_id: string;
  roles: string[];
}

export interface AppVisibilityOut {
  app_key: string;
  name: string;
  can_use: boolean;
  can_control: boolean;
}

export type SubjectType = "organization" | "department" | "role" | "user";

export interface BindingItem {
  subject_type: SubjectType;
  subject_id: string;
  actions: string[];
}

export interface BindingPutBody {
  bindings: BindingItem[];
}

export interface LlmOut {
  id: string;
  code: string;
  provider: string;
  model_name: string;
  is_active: boolean;
  config: Record<string, unknown>;
  has_api_key: boolean;
}

export interface LlmCreateBody {
  code: string;
  provider: string;
  model_name: string;
  config: Record<string, unknown>;
  is_active: boolean;
}

export interface LlmPatchBody {
  provider?: string | null;
  model_name?: string | null;
  config?: Record<string, unknown> | null;
  is_active?: boolean | null;
}

export interface ProfileOut {
  id: string;
  code: string;
  name: string;
  system_prompt: string;
  default_llm_id: string | null;
  skill_ids: string[];
}

export interface SkillOut {
  id: string;
  code: string;
  name: string;
  description: string | null;
  tool_ids: string[];
  prompt_template: string | null;
}

export type ToolKind = "builtin" | "http" | "mcp";

export interface ToolOut {
  id: string;
  code: string;
  name: string;
  kind: ToolKind;
  schema: Record<string, unknown>;
  config: Record<string, unknown>;
  mcp_server_id: string | null;
}

export type McpTransport = "stdio" | "sse";

export interface McpOut {
  id: string;
  code: string;
  name: string;
  transport: McpTransport;
  config: Record<string, unknown>;
  is_active: boolean;
}

export interface BeatOut {
  id: string;
  code: string;
  flow_id: string | null;
  profile_id: string | null;
  cron: string;
  input_payload: Record<string, unknown>;
  is_enabled: boolean;
  last_triggered_at: string | null;
}

export interface ConversationOut {
  id: string;
  user_id: string;
  title: string | null;
  app_key: string;
  flow_id: string | null;
  status: string;
}

export interface ConversationDetailOut extends ConversationOut {
  metadata: Record<string, unknown>;
}

export type MessageRole = "user" | "assistant" | "system" | "tool";

export interface MessageContentBlock {
  type: string;
  text?: string;
  tool_call_id?: string;
  name?: string;
  arguments?: Record<string, unknown>;
  result?: unknown;
  mime_type?: string;
  url?: string;
  metadata?: Record<string, unknown>;
}

export interface MessageOut {
  id: string;
  conversation_id: string;
  role: MessageRole;
  content_blocks: MessageContentBlock[];
  status: string;
}

export interface SendMessageOut {
  conversation_id: string;
  user_message_id: string;
  assistant_message_id: string;
  run_id: string;
}

export interface PublishedFlowCodeOut {
  code: string;
  version: number;
}

export type SseEventName =
  | "connected"
  | "run_submitted"
  | "speaking"
  | "reasoning"
  | "tool_calling"
  | "step_running"
  | "subagent_running"
  | "run_completed"
  | "run_failed";

export interface SseFrame {
  event: string;
  id: string | null;
  data: Record<string, unknown>;
}
