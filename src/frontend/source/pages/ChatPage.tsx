import { Bubble, Conversations, Sender } from "@ant-design/x";
import { Button, Flex, Input, Select, Space, Typography, message } from "antd";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactElement } from "react";

import { listProfiles } from "@/api/agentConfig";
import { errorMessage } from "@/api/client";
import { ConfirmDelete } from "@/components/ConfirmDelete";
import {
  createPlannerConversation,
  createWorkflowConversation,
  listConversations,
  listHitlPendings,
  listMessages,
  resumeHitl,
  sendPlannerMessage,
  sendWorkflowMessage,
  deleteConversation,
  type ChatScene,
} from "@/api/conversations";
import { listStudioFlows, listStudioProfiles } from "@/api/studio";
import { findApp, useSession } from "@/auth/context";
import { subscribeConversationEvents } from "@/sse/client";
import type { ConversationOut, HitlPendingOut, MessageContentBlock, MessageOut, SseFrame } from "@/types";

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
  const [profiles, setProfiles] = useState<{ id: string; name: string }[]>([]);
  const [profileId, setProfileId] = useState<string | null>(null);
  const [flowId, setFlowId] = useState<string | null>(null);
  const [flowOptions, setFlowOptions] = useState<{ id: string; label: string }[]>([]);
  const [hitl, setHitl] = useState<HitlPendingOut | null>(null);
  const [hitlInput, setHitlInput] = useState("");
  const abortRef = useRef<AbortController | null>(null);

  const reloadConvs = useCallback(async () => {
    const rows = await listConversations(scene);
    setConvs(rows);
    setActiveId((cur) => cur ?? rows[0]?.id);
  }, [scene]);

  const reloadMessages = useCallback(async (id: string) => {
    const rows = await listMessages(scene, id);
    setMessages(rows);
    setStreamText((prev) => {
      const next: Record<string, string> = { ...prev };
      for (const row of rows) {
        const text = blocksToText(row.content_blocks);
        if (row.status === "completed" && text !== "") {
          delete next[row.id];
        }
      }
      return next;
    });
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
          setProfiles(rows.map((row) => ({ id: row.id, name: row.name })));
          setProfileId((cur) => cur ?? rows[0]?.id ?? null);
        })
        .catch((err: unknown) => message.error(errorMessage(err, "加载 Profile 失败")));
    }
    if (scene === "workflow" && canStudio) {
      void listStudioFlows("published")
        .then((rows) => {
          setFlowOptions(rows.map((row) => ({ id: row.id, label: `${row.name} v${row.version}` })));
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
    if (scene === "workflow") {
      void listHitlPendings()
        .then((rows) => setHitl(rows.find((row) => row.conversation_id === activeId) ?? null))
        .catch(() => setHitl(null));
    } else {
      setHitl(null);
    }
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
          setHitl(null);
        }
        if (frame.event === "run_interrupted" && scene === "workflow") {
          const hid = String(frame.data.hitl_id ?? "");
          void listHitlPendings()
            .then((rows) => {
              const found = hid ? rows.find((row) => row.id === hid) : rows.find((row) => row.conversation_id === activeId);
              setHitl(found ?? null);
            })
            .catch(() => undefined);
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
    const convId = activeId;
    const tempUserId = `tmp-user-${Date.now()}`;
    const tempAsstId = `tmp-asst-${Date.now()}`;
    if (convId) {
      setMessages((prev) => [
        ...prev,
        {
          id: tempUserId,
          conversation_id: convId,
          role: "user",
          content_blocks: [{ type: "text", text: content }],
          status: "completed",
        },
        {
          id: tempAsstId,
          conversation_id: convId,
          role: "assistant",
          content_blocks: [],
          status: "streaming",
        },
      ]);
    }
    setInput("");
    try {
      const sent =
        scene === "planner"
          ? await sendPlannerMessage({
              conversation_id: convId ?? null,
              profile_id: profileId,
              content,
            })
          : await sendWorkflowMessage({
              conversation_id: convId ?? null,
              flow_id: flowId,
              content,
            });
      setMessages((prev) =>
        prev.map((row) => {
          if (row.id === tempUserId) {
            return { ...row, id: sent.user_message_id };
          }
          if (row.id === tempAsstId) {
            return { ...row, id: sent.assistant_message_id };
          }
          return row;
        }),
      );
      setStreamText((prev) => {
        const streamed = prev[tempAsstId];
        if (!streamed) {
          return prev;
        }
        const { [tempAsstId]: _drop, ...rest } = prev;
        return { ...rest, [sent.assistant_message_id]: streamed };
      });
      if (sent.conversation_id !== convId) {
        await reloadConvs();
        setActiveId(sent.conversation_id);
      } else {
        await reloadMessages(sent.conversation_id);
      }
    } catch (err) {
      message.error(errorMessage(err, "发送失败"));
      if (convId) {
        setMessages((prev) => prev.filter((row) => row.id !== tempUserId && row.id !== tempAsstId));
      }
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
            options={profiles.map((item) => ({ value: item.id, label: item.name }))}
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
            label: (
              <Flex justify="space-between" align="center" gap={8} style={{ width: "100%" }}>
                <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>
                  {item.title || item.id.slice(0, 8)}
                </span>
                {canControl ? (
                  <ConfirmDelete
                    onConfirm={async () => {
                      await deleteConversation(scene, item.id);
                      if (activeId === item.id) {
                        setActiveId(undefined);
                      }
                      await reloadConvs();
                    }}
                  />
                ) : null}
              </Flex>
            ),
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
        {scene === "workflow" && hitl !== null ? (
          <Flex vertical gap={8} style={{ border: "1px solid #ffe58f", background: "#fffbe6", padding: 12, borderRadius: 8 }}>
            <Typography.Text strong>人工待办 · {hitl.node_id}</Typography.Text>
            <Typography.Paragraph style={{ marginBottom: 0 }}>{hitl.prompt}</Typography.Paragraph>
            <Input.TextArea
              rows={3}
              value={hitlInput}
              onChange={(ev) => setHitlInput(ev.target.value)}
              placeholder="可选说明或表单 JSON"
            />
            <Space>
              <Button
                type="primary"
                onClick={() => {
                  void resumeHitl(hitl.id, {
                    decision: "approve",
                    user_input: hitlInput.trim() === "" ? null : hitlInput.trim(),
                  })
                    .then(() => {
                      setHitl(null);
                      setHitlInput("");
                      message.success("已批准");
                    })
                    .catch((err: unknown) => message.error(errorMessage(err, "恢复失败")));
                }}
              >
                批准
              </Button>
              <Button
                danger
                onClick={() => {
                  void resumeHitl(hitl.id, {
                    decision: "reject",
                    user_input: hitlInput.trim() === "" ? null : hitlInput.trim(),
                  })
                    .then(() => {
                      setHitl(null);
                      setHitlInput("");
                      message.success("已拒绝");
                    })
                    .catch((err: unknown) => message.error(errorMessage(err, "恢复失败")));
                }}
              >
                拒绝
              </Button>
            </Space>
          </Flex>
        ) : null}
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
