import { Bubble, Conversations, Sender } from "@ant-design/x";
import { Button, Flex, Input, Select, Typography, message } from "antd";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactElement } from "react";

import { listProfiles } from "@/api/agentConfig";
import { errorMessage } from "@/api/client";
import {
  createPlannerConversation,
  createWorkflowConversation,
  listConversations,
  listMessages,
  sendPlannerMessage,
  sendWorkflowMessage,
  type ChatScene,
} from "@/api/conversations";
import { listStudioFlows, listStudioProfiles } from "@/api/studio";
import { findApp, useSession } from "@/auth/context";
import { subscribeConversationEvents } from "@/sse/client";
import type { ConversationOut, MessageContentBlock, MessageOut, SseFrame } from "@/types";

function blocksToText(blocks: MessageContentBlock[]): string {
  return blocks
    .filter((block) => block.type === "text" || block.type === "reasoning")
    .map((block) => block.text ?? "")
    .join("\n");
}

interface Props {
  scene: ChatScene;
}

export function ChatPage({ scene }: Props): ReactElement {
  const { apps } = useSession();
  const canControl = findApp(apps, "conversation")?.can_control === true;
  const canStudio = findApp(apps, "studio")?.can_use === true;
  const canAgentConfig = findApp(apps, "agent_config")?.can_use === true;

  const [convs, setConvs] = useState<ConversationOut[]>([]);
  const [activeId, setActiveId] = useState<string | undefined>();
  const [messages, setMessages] = useState<MessageOut[]>([]);
  const [streamText, setStreamText] = useState<Record<string, string>>({});
  const [input, setInput] = useState("");
  const [profiles, setProfiles] = useState<{ id: string; code: string }[]>([]);
  const [profileId, setProfileId] = useState<string | null>(null);
  const [flowId, setFlowId] = useState<string | null>(null);
  const [flowOptions, setFlowOptions] = useState<{ id: string; label: string }[]>([]);
  const abortRef = useRef<AbortController | null>(null);

  const reloadConvs = useCallback(async () => {
    const rows = await listConversations(scene);
    setConvs(rows);
    setActiveId((cur) => cur ?? rows[0]?.id);
  }, [scene]);

  const reloadMessages = useCallback(async (id: string) => {
    const rows = await listMessages(scene, id);
    setMessages(rows);
    setStreamText({});
  }, [scene]);

  useEffect(() => {
    void reloadConvs().catch((err: unknown) => message.error(errorMessage(err, "加载会话失败")));
  }, [reloadConvs]);

  useEffect(() => {
    if (scene === "planner") {
      const load =
        canAgentConfig ? listProfiles() : canStudio ? listStudioProfiles() : Promise.resolve([]);
      void load
        .then((rows) => {
          setProfiles(rows.map((row) => ({ id: row.id, code: row.code })));
          setProfileId((cur) => cur ?? rows[0]?.id ?? null);
        })
        .catch((err: unknown) => message.error(errorMessage(err, "加载 Profile 失败")));
    }
    if (scene === "workflow" && canStudio) {
      void listStudioFlows()
        .then((rows) => {
          setFlowOptions(rows.map((row) => ({ id: row.id, label: `${row.code}@${row.version}` })));
          setFlowId((cur) => cur ?? rows[0]?.id ?? null);
        })
        .catch(() => undefined);
    }
  }, [scene, canStudio, canAgentConfig]);

  useEffect(() => {
    if (!activeId) {
      setMessages([]);
      return;
    }
    void reloadMessages(activeId).catch((err: unknown) => message.error(errorMessage(err, "加载消息失败")));
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;
    void subscribeConversationEvents(
      scene,
      activeId,
      (frame: SseFrame) => {
        if (frame.event === "speaking" || frame.event === "reasoning") {
          const mid = String(frame.data.message_id ?? "");
          const delta = String(frame.data.delta ?? "");
          if (mid) {
            setStreamText((prev) => ({ ...prev, [mid]: `${prev[mid] ?? ""}${delta}` }));
          }
        }
        if (frame.event === "run_completed" || frame.event === "run_failed") {
          void reloadMessages(activeId);
        }
      },
      ac.signal,
    ).catch((err: unknown) => {
      if (!ac.signal.aborted) {
        message.error(errorMessage(err, "SSE 中断"));
      }
    });
    return () => ac.abort();
  }, [activeId, scene, reloadMessages]);

  const bubbleItems = useMemo(
    () =>
      messages.map((msg) => {
        const extra = streamText[msg.id] ?? "";
        const content = `${blocksToText(msg.content_blocks)}${extra}`;
        return { key: msg.id, role: msg.role, content: content || "…" };
      }),
    [messages, streamText],
  );

  const onSubmit = async (text: string): Promise<void> => {
    const content = text.trim();
    if (content === "" || !canControl) {
      return;
    }
    try {
      const sent =
        scene === "planner"
          ? await sendPlannerMessage({
              conversation_id: activeId ?? null,
              profile_id: profileId,
              content,
            })
          : await sendWorkflowMessage({
              conversation_id: activeId ?? null,
              flow_id: flowId,
              content,
            });
      setInput("");
      if (sent.conversation_id !== activeId) {
        await reloadConvs();
        setActiveId(sent.conversation_id);
      } else {
        await reloadMessages(sent.conversation_id);
      }
    } catch (err) {
      message.error(errorMessage(err, "发送失败"));
    }
  };

  return (
    <Flex style={{ height: "calc(100vh - 112px)", background: "#fff", borderRadius: 8 }} gap={0}>
      <Flex vertical style={{ width: 280, borderRight: "1px solid #f0f0f0", padding: 12 }} gap={8}>
        <Typography.Text strong>{scene === "planner" ? "规划会话" : "工作流会话"}</Typography.Text>
        {scene === "planner" ? (
          <Select
            placeholder="Profile"
            value={profileId}
            onChange={setProfileId}
            options={profiles.map((item) => ({ value: item.id, label: item.code }))}
          />
        ) : canStudio && flowOptions.length > 0 ? (
          <Select
            placeholder="Flow"
            value={flowId}
            onChange={setFlowId}
            options={flowOptions.map((item) => ({ value: item.id, label: item.label }))}
          />
        ) : (
          <Input placeholder="flow_id UUID" value={flowId ?? ""} onChange={(e) => setFlowId(e.target.value || null)} />
        )}
        {canControl ? (
          <Button
            onClick={() => {
              void (scene === "planner"
                ? createPlannerConversation({
                    title: "新规划",
                    profile_id: profileId ?? "",
                  })
                : createWorkflowConversation({ title: "新工作流", flow_id: flowId })
              )
                .then((row) => {
                  setActiveId(row.id);
                  return reloadConvs();
                })
                .catch((err: unknown) => message.error(errorMessage(err, "创建失败")));
            }}
          >
            新建会话
          </Button>
        ) : null}
        <Conversations
          style={{ flex: 1, overflow: "auto" }}
          activeKey={activeId}
          items={convs.map((item) => ({
            key: item.id,
            label: item.title || item.id.slice(0, 8),
          }))}
          onActiveChange={(key) => setActiveId(key)}
        />
      </Flex>
      <Flex vertical style={{ flex: 1, padding: 16 }} gap={12}>
        <Bubble.List
          style={{ flex: 1, overflow: "auto" }}
          roles={{
            user: { placement: "end" },
            assistant: { placement: "start" },
            system: { placement: "start" },
            tool: { placement: "start" },
          }}
          items={bubbleItems}
        />
        <Sender
          value={input}
          onChange={setInput}
          onSubmit={(v) => {
            void onSubmit(v);
          }}
          disabled={!canControl}
          placeholder={canControl ? "输入消息" : "当前为只读（需要完全控制才能发送）"}
        />
      </Flex>
    </Flex>
  );
}
