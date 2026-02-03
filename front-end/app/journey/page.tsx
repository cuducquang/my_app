"use client";

import { useMemo, useRef, useState } from "react";

type AgentState = "idle" | "thinking" | "done";

type AgentStatus = {
  name: string;
  state: AgentState;
  detail?: string;
};

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
};

type AgentResponse = {
  recommendations?: Array<{
    destination: string;
    region: string;
    estimated_cost: number;
    tags: string[];
    notes: string[];
  }>;
  llm_notes?: Array<{ agent: string; note: string }>;
  workflow?: Array<{ agent: string; duration_ms: number }>;
};

const defaultAgents = ["intake", "research", "recommend"];

function formatResponse(result: AgentResponse): string {
  if (!result.recommendations?.length) {
    return "Mình chưa tìm được gợi ý phù hợp. Bạn thử tăng ngân sách hoặc số ngày nhé.";
  }
  const lines = result.recommendations.map((item, index) => {
    const tags = item.tags?.length ? `Tags: ${item.tags.join(", ")}` : "";
    return `${index + 1}. ${item.destination} (${item.region}) - Ước tính: $${item.estimated_cost}. ${tags}`;
  });
  return `Mình gợi ý các điểm sau:\n${lines.join("\n")}`;
}

export default function JourneyPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [agentStatuses, setAgentStatuses] = useState<AgentStatus[]>(
    defaultAgents.map((name) => ({ name, state: "idle" }))
  );
  const [agentNotes, setAgentNotes] = useState<Record<string, string>>({});
  const [toolCalls, setToolCalls] = useState<string[]>([]);
  const [formState, setFormState] = useState({
    days: "3",
    budget: "400",
    people: "2",
    groupType: "family",
    interests: "beach,food",
  });

  const streamingMessageId = useRef<string | null>(null);

  const assistantMessage = useMemo(
    () => messages.findLast((msg) => msg.role === "assistant"),
    [messages]
  );


  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    const content = input.trim();
    if (!content) return;

    const message: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content,
    };
    setMessages((prev) => [...prev, message]);
    setInput("");
    setIsLoading(true);
    setAgentNotes({});
    setToolCalls([]);
    setAgentStatuses((prev) =>
      prev.map((agent, index) => ({
        ...agent,
        state: index === 0 ? "thinking" : "idle",
        detail: undefined,
      }))
    );

    const payload = {
      days: Number(formState.days),
      budget: Number(formState.budget),
      people: Number(formState.people),
      group_type: formState.groupType,
      interests: formState.interests.split(",").map((item) => item.trim()),
      query: content,
    };

    try {
      const response = await fetch("/api/agent/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok || !response.body) {
        throw new Error(`Request failed: ${response.status}`);
      }

      const assistantId = crypto.randomUUID();
      streamingMessageId.current = assistantId;
      setMessages((prev) => [
        ...prev,
        {
          id: assistantId,
          role: "assistant",
          content: "",
        },
      ]);

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      const updateAssistant = (text: string) => {
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === streamingMessageId.current
              ? { ...msg, content: msg.content + text }
              : msg
          )
        );
      };

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? "";
        for (const part of parts) {
          const lines = part.split("\n");
          let eventName = "message";
          let dataPayload = "";
          for (const line of lines) {
            if (line.startsWith("event:")) {
              eventName = line.replace("event:", "").trim();
            } else if (line.startsWith("data:")) {
              dataPayload += line.replace("data:", "").trim();
            }
          }

          if (!dataPayload) continue;
          let data: any = {};
          try {
            data = JSON.parse(dataPayload);
          } catch {
            data = { text: dataPayload };
          }

          if (eventName === "token" && data.text) {
            updateAssistant(data.text);
          }

          if (eventName === "agent_start") {
            setAgentStatuses((prev) =>
              prev.map((agent) =>
                agent.name === data.agent ? { ...agent, state: "thinking" } : agent
              )
            );
          }

          if (eventName === "agent_done") {
            setAgentStatuses((prev) =>
              prev.map((agent) =>
                agent.name === data.agent
                  ? { ...agent, state: "done", detail: `${data.duration_ms}ms` }
                  : agent
              )
            );
          }

          if (eventName === "tool_call" && data.tool) {
            setToolCalls((prev) => [...prev, `${data.tool}`]);
          }

          if (eventName === "agent_note" && data.agent && data.note) {
            setAgentNotes((prev) => ({ ...prev, [data.agent]: data.note }));
          }

          if (eventName === "final") {
            const formatted = formatResponse(data as AgentResponse);
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === streamingMessageId.current ? { ...msg, content: formatted } : msg
              )
            );
          }
        }
      }
    } catch (err) {
      const message = "Không thể gọi API Gateway. Kiểm tra API_GATEWAY_URL và backend nhé.";
      setError(message);
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: message,
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-50">
      <div className="mx-auto flex max-w-6xl flex-col gap-10 px-6 py-10 lg:flex-row">
        <aside className="w-full space-y-6 lg:w-1/3">
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-zinc-500">
              Trip Inputs
            </p>
            <h1 className="mt-2 text-3xl font-semibold">Journey Chat</h1>
            <p className="mt-2 text-sm text-zinc-400">
              Nhập dữ liệu cơ bản, rồi chat để agent hiểu thêm mong muốn của bạn.
            </p>
          </div>

          <div className="rounded-2xl border border-zinc-800 bg-zinc-900/60 p-4">
            <div className="grid grid-cols-2 gap-4 text-sm">
              <label className="space-y-2">
                <span className="text-zinc-400">Số ngày</span>
                <input
                  className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2"
                  value={formState.days}
                  onChange={(event) =>
                    setFormState((prev) => ({ ...prev, days: event.target.value }))
                  }
                />
              </label>
              <label className="space-y-2">
                <span className="text-zinc-400">Ngân sách (USD)</span>
                <input
                  className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2"
                  value={formState.budget}
                  onChange={(event) =>
                    setFormState((prev) => ({ ...prev, budget: event.target.value }))
                  }
                />
              </label>
              <label className="space-y-2">
                <span className="text-zinc-400">Số người</span>
                <input
                  className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2"
                  value={formState.people}
                  onChange={(event) =>
                    setFormState((prev) => ({ ...prev, people: event.target.value }))
                  }
                />
              </label>
              <label className="space-y-2">
                <span className="text-zinc-400">Nhóm</span>
                <select
                  className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2"
                  value={formState.groupType}
                  onChange={(event) =>
                    setFormState((prev) => ({ ...prev, groupType: event.target.value }))
                  }
                >
                  <option value="family">Gia đình</option>
                  <option value="group">Nhóm bạn</option>
                  <option value="couple">Cặp đôi</option>
                  <option value="solo">Một mình</option>
                </select>
              </label>
            </div>
            <label className="mt-4 flex flex-col gap-2 text-sm">
              <span className="text-zinc-400">Sở thích</span>
              <input
                className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2"
                value={formState.interests}
                onChange={(event) =>
                  setFormState((prev) => ({ ...prev, interests: event.target.value }))
                }
              />
            </label>
          </div>

          <div className="rounded-2xl border border-zinc-800 bg-zinc-900/60 p-4">
            <p className="text-xs uppercase tracking-[0.2em] text-zinc-500">
              Agent Status
            </p>
            <div className="mt-3 space-y-3">
              {agentStatuses.map((agent) => (
                <div
                  key={agent.name}
                  className="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm"
                >
                  <span className="capitalize">{agent.name}</span>
                  <span className="text-xs text-zinc-400">
                    {agent.state === "thinking" && "thinking..."}
                    {agent.state === "done" && agent.detail ? `done · ${agent.detail}` : ""}
                    {agent.state === "done" && !agent.detail ? "done" : ""}
                    {agent.state === "idle" && !isLoading ? "idle" : ""}
                    {agent.state === "idle" && isLoading ? "queued" : ""}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {Object.keys(agentNotes).length > 0 && (
            <div className="rounded-2xl border border-zinc-800 bg-zinc-900/60 p-4 text-sm">
              <p className="text-xs uppercase tracking-[0.2em] text-zinc-500">
                Agent Reasoning
              </p>
              <div className="mt-3 space-y-3">
                {Object.entries(agentNotes).map(([agent, note]) => (
                  <div key={agent} className="rounded-lg border border-zinc-800 bg-zinc-950 p-3">
                    <p className="text-xs uppercase text-zinc-500">{agent}</p>
                    <p className="mt-2 text-sm text-zinc-200">{note}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </aside>

        <section className="flex w-full flex-1 flex-col rounded-3xl border border-zinc-800 bg-zinc-900/40 p-4">
          <div className="flex-1 space-y-4 overflow-y-auto rounded-2xl bg-zinc-950/60 p-4">
            {messages.length === 0 && (
              <div className="rounded-xl border border-dashed border-zinc-800 p-6 text-sm text-zinc-400">
                Hãy mô tả kỳ nghỉ của bạn. Ví dụ: “Mình có 4 ngày, đi gia đình 3
                người, muốn biển và đồ ăn ngon.”
              </div>
            )}
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm ${
                  msg.role === "user"
                    ? "ml-auto bg-white text-zinc-900"
                    : "bg-zinc-900 text-zinc-200"
                }`}
              >
                <pre className="whitespace-pre-wrap font-sans">{msg.content}</pre>
              </div>
            ))}
            {error && (
              <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">
                {error}
              </div>
            )}
            {isLoading && (
              <div className="flex items-center gap-2 text-sm text-zinc-400">
                <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-400" />
                Agents are thinking...
              </div>
            )}
          </div>

          <form
            onSubmit={handleSubmit}
            className="mt-4 flex flex-col gap-3 rounded-2xl border border-zinc-800 bg-zinc-950 px-4 py-3"
          >
            <textarea
              className="min-h-[90px] resize-none rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 focus:outline-none"
              placeholder="Nhập câu hỏi hoặc yêu cầu của bạn..."
              value={input}
              onChange={(event) => setInput(event.target.value)}
            />
            <div className="flex flex-col items-stretch gap-3 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-xs text-zinc-500">
                {isLoading ? "Đang xử lý... hãy đợi chút nhé." : "Enter để gửi."}
              </p>
              <button
                className="rounded-full bg-emerald-400 px-5 py-2 text-sm font-semibold text-zinc-900 transition hover:bg-emerald-300 disabled:cursor-not-allowed disabled:bg-zinc-700 disabled:text-zinc-400"
                type="submit"
                disabled={isLoading}
              >
                {isLoading ? "Thinking..." : "Send"}
              </button>
            </div>
          </form>
          {toolCalls.length > 0 && (
            <div className="mt-4 rounded-2xl border border-zinc-800 bg-zinc-950 p-4 text-sm text-zinc-300">
              <p className="text-xs uppercase tracking-[0.2em] text-zinc-500">
                Tool Calls
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                {toolCalls.map((tool, index) => (
                  <span
                    key={`${tool}-${index}`}
                    className="rounded-full border border-zinc-800 bg-zinc-900 px-3 py-1 text-xs"
                  >
                    {tool}
                  </span>
                ))}
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

