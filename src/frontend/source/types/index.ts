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
  is_superuser?: boolean;
  status?: string;
}

export type UserAccountStatus = "active" | "disabled" | "banned";

export interface UserAccountOut {
  id: string;
  username: string;
  display_name: string;
  status: UserAccountStatus;
  organization_id: string;
  department_id: string | null;
  is_superuser: boolean;
  last_login_at: string | null;
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

export interface HitlPendingOut {
  id: string;
  run_id: string;
  conversation_id: string | null;
  node_id: string;
  prompt: string;
  form_schema: Record<string, unknown> | null;
  status: string;
  expires_at: string | null;
}

export interface HitlResumeBody {
  decision: "approve" | "reject";
  user_input?: string | null;
}

export interface HitlResumeOut {
  run_id: string;
  resumed: boolean;
}

export interface PublishedFlowCodeOut {
  code: string;
  version: number;
  name: string;
}

export type FlowStatus = "draft" | "published" | "archived";

export type NodeType = "start" | "end" | "llm" | "tool" | "assign" | "hitl" | "subgraph" | "custom";

export type ChannelName = "messages" | "variables" | "metadata";

export interface StateChannelSpec {
  name: ChannelName;
  reducer: "append" | "merge";
  json_schema: Record<string, unknown> | null;
}

export interface GraphStateSpec {
  channels: StateChannelSpec[];
}

export interface FlowNode {
  id: string;
  type: NodeType;
  title: string | null;
  data: Record<string, unknown>;
}

export interface FlowEdge {
  id: string;
  source: string;
  target: string;
  label: string | null;
}

export interface BranchCase {
  key: string;
  target: string;
}

export interface BranchRouter {
  kind: "state_path" | "expr" | "hitl_decision" | "child_status";
  path: string | null;
  expr: string | null;
}

export interface FlowBranch {
  id: string;
  source: string;
  router: BranchRouter;
  cases: BranchCase[];
  default_target: string | null;
  max_visits: number | null;
}

export interface NodeLayout {
  x: number;
  y: number;
  w: number | null;
  h: number | null;
  z: number | null;
}

export interface EdgeLayout {
  waypoints: number[][] | null;
  color: string | null;
}

export interface FlowView {
  nodes: Record<string, NodeLayout>;
  edges: Record<string, EdgeLayout>;
  branches: Record<string, EdgeLayout>;
  groups: Record<string, unknown>[] | null;
  computed_levels: Record<string, number> | null;
}

export interface FlowDefinitionV1 {
  schema_version: 1;
  state: GraphStateSpec;
  nodes: FlowNode[];
  edges: FlowEdge[];
  branches: FlowBranch[];
  view: FlowView | null;
}

export interface FlowOut {
  id: string;
  code: string;
  name: string;
  version: number;
  profile_id: string;
  status: FlowStatus;
  published_at: string | null;
  definition: FlowDefinitionV1;
}

export interface FlowCreateBody {
  name: string;
  profile_id: string;
  definition?: FlowDefinitionV1 | null;
}

export interface FlowPatchBody {
  name?: string | null;
  profile_id?: string | null;
  definition?: FlowDefinitionV1 | null;
}

export interface ProfileCatalogOut {
  id: string;
  code: string;
  name: string;
}

export interface LlmCatalogOut {
  id: string;
  code: string;
  provider: string;
  model_name: string;
}

export interface ToolCatalogOut {
  id: string;
  code: string;
  name: string;
  kind: string;
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
  | "run_failed"
  | "run_interrupted";

export interface SseFrame {
  event: string;
  id: string | null;
  data: Record<string, unknown>;
}
