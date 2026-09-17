import { FormEvent, ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { Bot, Brain, ChevronDown, ChevronRight, FileText, Send, Square, Wrench } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { RESOURCE_ID, ResourceChip } from "../../shared/ui";
import { useHeightDrag } from "../../shared/ui/useHeightDrag";
import { FullscreenButton, FullscreenExit, useFullscreen } from "../../shared/ui";
import { api, SessionExpiredError, streamChat } from "../../shared/api";
import { ToolArguments, ToolRender } from "../../shared/agent-output";
import type { SituationFlows } from "../investigation";
import { agentIdentity, applyReasoning, appendToolArguments, settleToolArguments, finishTool } from "../../shared/api";
import type { AgentIdentity, ChatMessage, ReasoningBlock, Situation, ToolRun } from "../../shared/types";

interface Props {
  situation: Situation | null;
  requestedPrompt: { id: number; text: string } | null;
  //: The two situation workloads, run once by the app and watched here.
  flows: SituationFlows;
  investigator: AgentIdentity | null;
}

/**
 * Two workloads, two tabs, separate states.
 *
 * The Cyber Defender tab carries both the automatic investigation of the selected
 * situation and the analyst's own chat turns, kept as distinct entries so one never
 * appears under the other's heading. Switching tabs is a view change and cancels nothing.
 * Only a change of selected situation supersedes a run, and that is decided in
 * `lib/flows.ts`.
 */
type ChatTab = "defender" | "summary";

const TABS: { id: ChatTab; label: string; icon: typeof Bot }[] = [
  { id: "defender", label: "Cyber Defender", icon: Bot },
  { id: "summary", label: "Situation Summary", icon: FileText },
];

const starters = [
  "Run the purpose-built scanner for 2026-08-13T02:30:00Z to 2026-08-13T03:40:59Z and identify the highest-priority situation.",
  "Reconstruct the selected situation timeline and cite evidence.",
  "Test whether the firewall block is meaningful against baseline.",
];

export function ChatPanel({ situation, requestedPrompt, flows, investigator }: Props) {
  const [tab, setTab] = useState<ChatTab>("defender");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const name = investigator?.name ?? "Investigator";
  const model = investigator?.model ?? "";
  const abort = useRef<AbortController | null>(null);
  const scroll = useRef<HTMLDivElement>(null);
  const handledPrompt = useRef(0);
  const sessionRef = useRef("");
  const sessionAgent = useRef("");
  const busy = useRef(false);

  /** Sessions live in backend memory only, so create on demand rather than once at mount. */
  async function ensureSession(): Promise<string> {
    const identity = `${investigator?.id ?? ""}:${investigator?.version ?? ""}`;
    if (sessionRef.current && sessionAgent.current === identity) return sessionRef.current;
    const value = await api.createSession();
    sessionRef.current = value.session_id;
    sessionAgent.current = identity;
    return value.session_id;
  }

  useEffect(() => { scroll.current?.scrollTo({ top: scroll.current.scrollHeight }); }, [messages]);
  useEffect(() => {
    if (requestedPrompt && requestedPrompt.id !== handledPrompt.current && !running) {
      handledPrompt.current = requestedPrompt.id;
      void send(requestedPrompt.text);
    }
  }, [requestedPrompt, running]);

  function mutate(id: string, update: (message: ChatMessage) => ChatMessage) {
    setMessages((previous) => previous.map((message) => message.id === id ? update(message) : message));
  }

  async function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || busy.current) return;
    busy.current = true;
    const userId = crypto.randomUUID();
    const agentId = crypto.randomUUID();
    setMessages((previous) => [
      ...previous,
      { id: userId, role: "user", text: trimmed },
      { id: agentId, role: "agent", text: "", tools: [], agent: investigator ?? undefined },
    ]);
    setInput(""); setRunning(true); setError("");
    const controller = new AbortController(); abort.current = controller;
    let tokenBuffer = "";
    let tokenFrame = 0;
    const flushTokens = () => {
      tokenFrame = 0;
      if (!tokenBuffer) return;
      const buffered = tokenBuffer;
      tokenBuffer = "";
      mutate(agentId, (message) => ({ ...message, text: message.text + buffered }));
    };
    const turn = (id: string) => streamChat(id, trimmed, situation, {
      token: (token) => {
        tokenBuffer += token;
        if (!tokenFrame) tokenFrame = requestAnimationFrame(flushTokens);
      },
      toolStart: (tool) => mutate(agentId, (message) => ({ ...message, tools: [...(message.tools ?? []), tool] })),
      toolDelta: (id, delta) => mutate(agentId, (message) => ({
        ...message, tools: appendToolArguments(message.tools ?? [], id, delta),
      })),
      toolEnd: (id, args) => mutate(agentId, (message) => ({
        ...message, tools: settleToolArguments(message.tools ?? [], id, args),
      })),
      toolResult: (id, _name, result) => mutate(agentId, (message) => ({
        ...message, tools: finishTool(message.tools ?? [], id, result),
      })),
      reasoning: (id, delta, state) => mutate(agentId, (message) => ({
        ...message, reasoning: applyReasoning(message.reasoning ?? [], id, delta, state),
      })),
      metadata: (data) => mutate(agentId, (message) => ({ ...message, agent: agentIdentity(data) ?? message.agent })),
      status: (activity) => mutate(agentId, (message) => ({ ...message, activity })),
      done: () => setRunning(false),
      error: (message) => { sessionRef.current = ""; setError(message); setRunning(false); },
    }, controller.signal);

    try {
      await turn(await ensureSession());
    } catch (err) {
      sessionRef.current = "";
      if (err instanceof SessionExpiredError) {
        setError("Session expired or agent changed. This turn was not replayed.");
      } else if ((err as Error).name !== "AbortError") setError((err as Error).message);
    } finally {
      if (tokenFrame) cancelAnimationFrame(tokenFrame);
      flushTokens();
      busy.current = false;
      setRunning(false); abort.current = null;
    }
  }

  function submit(event: FormEvent) { event.preventDefault(); void send(input); }

  const chat = useFullscreen("chat");
  const { ref: composer, height: composerHeight, startResize } = useHeightDrag<HTMLTextAreaElement>({
    storageKey: "cybereye.composer", direction: "up", min: 38, max: 420, fallbackHeight: 48,
  });

  const grow = useCallback(() => {
    const box = composer.current;
    if (!box) return;
    box.style.height = "auto";
    box.style.height = `${Math.min(box.scrollHeight, 220)}px`;
  }, []);

  return (
    <section className={`chat-panel panel-column ${chat.active ? "panel-fullscreen" : ""}`} aria-label={`${name} agent chat`}>
      <div className="agent-context">
        <span className="agent-dot" />
        <div><b data-testid="active-investigator" title={investigator ? `Version ${investigator.version}` : undefined}>{name}</b><p>{situation ? `Context: ${situation.host} / ${situation.principal}` : "No situation pinned"}</p></div>
        <span className="live-model">{model}</span>
        <FullscreenButton active={chat.active} onToggle={chat.toggle} label="the chat" />
      </div>
      {chat.active && <FullscreenExit onExit={chat.exit} label="chat" />}
      <nav className="chat-tabs" role="tablist" aria-label="Agent workloads">
        {TABS.map(({ id, label, icon: Icon }) => {
          const flow = id === "summary" ? flows.summary : flows.diagnosis;
          const busy = id === "defender" ? running || flow.state === "running" : flow.state === "running";
          const failed = flow.state === "failed";
          return (
            <button key={id} type="button" role="tab" id={`chat-tab-${id}`}
                    aria-selected={tab === id} aria-controls={`chat-panel-${id}`}
                    data-testid={`chat-tab-${id}`}
                    className={tab === id ? "active" : ""} onClick={() => setTab(id)}>
              <Icon size={13} aria-hidden="true" />
              <span>{id === "defender" && name !== "CyberDefender" ? name : label}</span>
              {/* Off-tab activity is stated, not advertised: a dot for running, a mark for failed. */}
              {busy && <span className="chat-tab-dot" title="running" aria-label="running" />}
              {!busy && failed && <span className="chat-tab-failed" aria-label="failed">!</span>}
            </button>
          );
        })}
      </nav>
      <div id="chat-panel-summary" role="tabpanel" aria-labelledby="chat-tab-summary"
           className="messages workload-stream" hidden={tab !== "summary"}
           data-testid="summary-stream">
        <WorkloadHeader
          situation={situation} state={flows.summary.state} activity={flows.summary.activity}
          idle="Select a situation to summarise it." meta={flows.summary.meta}
        />
        {flows.summary.text && (
          <article className="message agent">
            <span className="message-role">{flows.summary.agent?.name ?? "Investigator"}</span>
            <div className="message-body" data-testid="summary-text">
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={MARKDOWN_COMPONENTS}>
                {flows.summary.text}
              </ReactMarkdown>
            </div>
          </article>
        )}
        {flows.summary.error && <div className="error-box" role="alert">{flows.summary.error}</div>}
      </div>
      <div id="chat-panel-defender" role="tabpanel" aria-labelledby="chat-tab-defender"
           className="messages" ref={scroll} hidden={tab !== "defender"}>
        {/* The investigation is its own run, kept above the conversation so its tool calls
            never read as part of a chat turn. */}
        {flows.diagnosis.state !== "idle" && (
          <article className="message agent investigation-entry" data-testid="investigation-stream">
            <span className="message-role">Investigation of the selected situation</span>
            {flows.diagnosis.agent && <span className="message-agent-version" data-agent-id={flows.diagnosis.agent.id}
              data-agent-version={flows.diagnosis.agent.version}>
              {flows.diagnosis.agent.name} / version {flows.diagnosis.agent.version}
            </span>}
            <WorkloadHeader
              situation={situation} state={flows.diagnosis.state} activity={flows.diagnosis.activity}
              idle="Select a situation to investigate it."
              meta={flows.diagnosis.result
                ? `${flows.diagnosis.result.confidence} confidence · ${flows.diagnosis.result.model}`
                : ""}
            />
            <ReasoningStream blocks={flows.diagnosis.reasoning} />
            {flows.diagnosis.tools.map((tool) => <ToolCard tool={tool} key={tool.id} />)}
            {flows.diagnosis.result && (
              <div className="message-body" data-testid="diagnosis-text">
                <p><b>{flows.diagnosis.result.headline}</b></p>
                <p>{flows.diagnosis.result.narrative}</p>
              </div>
            )}
            {flows.diagnosis.error && <div className="error-box" role="alert">{flows.diagnosis.error}</div>}
          </article>
        )}
        {messages.length === 0 && (
          <div className="chat-empty">
            <Bot size={28} /><b>Evidence-led investigation</b>
            <p>The agent runs real tools against ADX. It cannot contain or change anything.</p>
            <div className="starter-list">{starters.map((starter) => <button key={starter} onClick={() => void send(starter)} disabled={running}>{starter}</button>)}</div>
          </div>
        )}
        {messages.map((message) => (
          <article className={`message ${message.role}`} key={message.id}>
            <span className="message-role" data-agent-id={message.agent?.id} data-agent-version={message.agent?.version}>
              {message.role === "user" ? "Analyst" : message.agent ? `${message.agent.name} / version ${message.agent.version}` : "Investigator"}
            </span>
            {message.notice && <p className="message-notice">{message.notice}</p>}
            <ReasoningStream blocks={message.reasoning ?? []} />
            {message.tools?.map((tool) => <ToolCard tool={tool} key={tool.id} />)}
            {(message.text || (message.role === "agent" && running)) && (
              <div className="message-body">{message.text
                ? <ReactMarkdown remarkPlugins={[remarkGfm]} components={MARKDOWN_COMPONENTS}>{message.text}</ReactMarkdown>
                : <span className="thinking"><i />{message.activity ?? "Starting investigation…"}</span>}</div>
            )}
          </article>
        ))}
        {error && <div className="error-box">{error}</div>}
      </div>
      <form className="chat-input" onSubmit={submit} hidden={tab !== "defender"}>
        <div
          className="composer-grip" role="separator" aria-orientation="horizontal"
          aria-label="Resize the message box" onPointerDown={startResize}
        />
        <textarea
          ref={composer} value={input} placeholder={`Ask ${name} to investigate...`}
          disabled={running} rows={2} style={composerHeight ? { height: composerHeight } : undefined}
          onChange={(event) => { setInput(event.target.value); if (!composerHeight) grow(); }}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void send(input); }
          }}
        />
        {running ? <button type="button" title="Stop" onClick={() => abort.current?.abort()}><Square size={15} fill="currentColor" /></button>
          : <button type="submit" title="Send" disabled={!input.trim()}><Send size={16} /></button>}
      </form>
    </section>
  );
}

/** One line of honest state per workload: what is happening, or what happened. */
function WorkloadHeader({ situation, state, activity, idle, meta }: {
  situation: Situation | null; state: string; activity: string; idle: string; meta: string;
}) {
  if (!situation) return <div className="chat-empty"><p>{idle}</p></div>;
  return (
    <div className="workload-status" role="status">
      {state === "running"
        ? <span className="thinking"><i />{activity || "Working…"}</span>
        : <span className={`workload-state ${state}`}>
            {state === "failed" ? "Failed" : state === "done" ? "Complete" : "Not started"}
          </span>}
      {meta && <span className="fold-meta">{meta}</span>}
    </div>
  );
}

const MARKDOWN_COMPONENTS = {
  code({ children, ...props }: { children?: ReactNode; className?: string }) {
    const value = String(children ?? "");
    if (RESOURCE_ID.test(value)) return <ResourceChip value={value} />;
    return <code {...props}>{children}</code>;
  },
};

function ToolCard({ tool }: { tool: ToolRun }) {
  const [open, setOpen] = useState(false);
  const [elapsed, setElapsed] = useState(Date.now() - tool.startedAt);
  useEffect(() => {
    if (tool.status !== "running") return;
    const timer = window.setInterval(() => setElapsed(Date.now() - tool.startedAt), 100);
    return () => window.clearInterval(timer);
  }, [tool.status, tool.startedAt]);
  const duration = tool.durationMs ?? elapsed;
  return (
    <div className="tool-card">
      <button className="tool-card-head" onClick={() => setOpen(!open)}>
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        <Wrench size={13} /><b>{tool.displayName ?? tool.name}</b>
        {tool.fallback && <span className="tool-fallback">KQL fallback</span>}
        <span className="tool-meta">
          <span className="tool-duration">{(duration / 1000).toFixed(1)}s</span>
          <span className={`tool-state ${tool.status}`}>
            {tool.status === "running" ? "● running" : tool.status === "error" ? "✗ failed" : "✓ complete"}
          </span>
        </span>
      </button>
      {open && <div className="tool-card-body">
        {!tool.args && !tool.pendingArgs && tool.status === "running" && <div className="tool-composing"><i /><i /><i /> Composing input…</div>}
        {(tool.args || tool.pendingArgs) && <ToolArguments args={tool.args} streaming={tool.pendingArgs} />}
        {tool.result !== undefined && <><label>Result</label><ToolRender value={tool.result} /></>}
      </div>}
    </div>
  );
}

/**
 * The model's reasoning summaries for one run.
 *
 * A turn the model reasons through silently produces no parts, and this renders nothing at
 * all rather than an empty frame or a spinner waiting on text that is never coming.
 */
function ReasoningStream({ blocks }: { blocks: ReasoningBlock[] }) {
  if (blocks.length === 0) return null;
  return <>{blocks.map((block, index) => (
    <ReasoningCard block={block} key={block.id} index={index + 1} />
  ))}</>;
}

function ReasoningCard({ block, index }: { block: ReasoningBlock; index: number }) {
  const [open, setOpen] = useState(!block.done);
  const touched = useRef(false);
  useEffect(() => {
    // Follows the stream while it writes, then folds away so the tool flow stays primary.
    if (!touched.current) setOpen(!block.done);
  }, [block.done]);
  return (
    <div className={`reasoning-card${block.done ? "" : " streaming"}`} data-testid="reasoning-block">
      <button type="button" className="reasoning-head" aria-expanded={open}
              onClick={() => { touched.current = true; setOpen(!open); }}>
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        <Brain size={13} aria-hidden="true" />
        <b>Model reasoning</b>
        <span className="reasoning-tag">summary of its own thinking · not evidence</span>
        <span className="reasoning-index">#{index}</span>
      </button>
      {open && (
        <div className="reasoning-body" data-testid="reasoning-text">
          {/* No resource chips here: the model's narration must not read as retrieved evidence. */}
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{block.text}</ReactMarkdown>
        </div>
      )}
    </div>
  );
}
