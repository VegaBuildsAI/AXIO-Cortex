"use client";

import {
  FormEvent,
  KeyboardEvent,
  ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

type Mode = "chat" | "cowork" | "code";
type StageModule = "cowork" | "code";
type Message = { id: string; role: "user" | "assistant"; content: string; model?: string };
type Conversation = {
  id: string;
  mode: Mode;
  title: string;
  workspace_id?: string | null;
  messages: Message[];
  updated_at: string;
};
type Workspace = { id: string; name: string; path: string };
type FileItem = { id: string; name: string; relative_path: string; size: number };
type Activity = { id: string; type: string; title: string; detail?: string };
type Approval = {
  approval_id: string;
  action: string;
  detail: { path?: string; command?: string; diff?: string; risk?: string; args?: string };
};
type AgentRosterItem = { name: string; description: string; internet: boolean };
type PlanStep = { id: number; phase: string; agent: string; description: string; depends_on: number[] };
type AgentPlan = { task: string; agents: AgentRosterItem[]; steps: PlanStep[] };
type Health = {
  ollama: boolean;
  claude: boolean;
  postgres: boolean | null;
  searxng: boolean;
};
type Job = {
  id: string;
  pid: number | null;
  script: string;
  workspace: string;
  log_path: string;
  started_at: string;
  status: string;
};

const API = process.env.NEXT_PUBLIC_AXIO_API || "http://127.0.0.1:8765";

const MODEL_LABELS = {
  local: "gemma4:12b",
  code: "claude-opus-4-8",
} as const;

const stageCopy: Record<StageModule, { kicker: string; title: string; subtitle: string; placeholder: string }> = {
  cowork: {
    kicker: "WORKSPACE INTELLIGENCE",
    title: "Work across your files",
    subtitle: "Open a workspace and bring the right documents into context.",
    placeholder: "Ask about your workspace…",
  },
  code: {
    kicker: "AGENTIC CODING",
    title: "Build with AXIO",
    subtitle: "Agentic coding with visible tools, approvals, diffs and verification.",
    placeholder: "Describe the coding task…",
  },
};

const SSE_EVENTS = [
  "run_started", "status", "token", "message", "tool_started", "tool_result",
  "approval_required", "approval_resolved", "diff", "usage", "warning", "error",
  "run_cancelled", "run_completed", "agent_plan", "agent_event",
];

// Normalize orchestrator outcomes into a small status vocabulary for badges.
function stepStatusFrom(kind: string, outcome?: string): string {
  if (kind === "step_start") return "running";
  if (outcome === "OK" || outcome === "FALLBACK" || outcome === "DONE") return "done";
  if (outcome === "SKIPPED") return "skipped";
  return "failed";
}

function err(value: unknown) {
  return value instanceof Error ? value.message : String(value);
}
function dateGroup(value: string) {
  const date = new Date(value);
  return date.toDateString() === new Date().toDateString()
    ? "Today"
    : date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
function fileSize(value: number) {
  return value < 1024 ? `${value} B` : `${(value / 1024).toFixed(1)} KB`;
}
async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options?.headers || {}) },
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      detail = (await response.json()).detail || detail;
    } catch {}
    throw new Error(detail);
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

// ---------------------------------------------------------------------------
// One conversational surface (Chat dock, or the Cowork/Code stage). Owns its
// own conversation, streaming buffer, run + SSE stream, and (for code) the
// activity / approvals / diff state.
// ---------------------------------------------------------------------------
type Surface = ReturnType<typeof useSurface>;

function useSurface(params: {
  mode: Mode;
  workspaceId: string | null;
  fileIds: () => string[];
  onConversationsChanged: () => void;
  onError: (message: string) => void;
}) {
  const { mode, workspaceId, fileIds, onConversationsChanged, onError } = params;
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [streaming, setStreaming] = useState("");
  const [busy, setBusy] = useState(false);
  const [runId, setRunId] = useState<string | null>(null);
  const [activity, setActivity] = useState<Activity[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [diff, setDiff] = useState("");
  const [agentPlan, setAgentPlan] = useState<AgentPlan | null>(null);
  const [stepStatus, setStepStatus] = useState<Record<number, string>>({});
  const sourceRef = useRef<EventSource | null>(null);

  const reset = useCallback(() => {
    sourceRef.current?.close();
    setConversation(null);
    setStreaming("");
    setActivity([]);
    setApprovals([]);
    setDiff("");
    setAgentPlan(null);
    setStepStatus({});
    setRunId(null);
    setBusy(false);
  }, []);

  const open = useCallback((full: Conversation) => {
    sourceRef.current?.close();
    setConversation(full);
    setStreaming("");
    setActivity([]);
    setApprovals([]);
    setDiff("");
    setAgentPlan(null);
    setStepStatus({});
    setRunId(null);
    setBusy(false);
  }, []);

  useEffect(() => () => sourceRef.current?.close(), []);

  function addActivity(item: Omit<Activity, "id">) {
    setActivity((current) => [...current, { ...item, id: crypto.randomUUID() }]);
  }

  function connect(id: string, active: Conversation) {
    sourceRef.current?.close();
    const source = new EventSource(`${API}/api/runs/${id}/events`);
    sourceRef.current = source;
    for (const name of SSE_EVENTS) {
      source.addEventListener(name, async (raw) => {
        const data = JSON.parse((raw as MessageEvent).data).data || {};
        if (name === "token") setStreaming((current) => current + (data.text || ""));
        if (name === "status") addActivity({ type: "status", title: data.label || "Working", detail: data.model });
        if (name === "tool_started")
          addActivity({ type: "tool", title: data.tool, detail: JSON.stringify(data.arguments || {}) });
        if (name === "tool_result") addActivity({ type: "result", title: `${data.tool} →`, detail: data.result });
        if (name === "approval_required") setApprovals((current) => [...current, data]);
        if (name === "approval_resolved")
          setApprovals((current) => current.filter((item) => item.approval_id !== data.approval_id));
        if (name === "diff") setDiff(data.diff || "");
        if (name === "agent_plan") {
          setAgentPlan(data as AgentPlan);
          setStepStatus(Object.fromEntries((data.steps || []).map((s: PlanStep) => [s.id, "pending"])));
        }
        if (name === "agent_event") {
          const status = stepStatusFrom(data.kind, data.outcome);
          setStepStatus((current) => ({ ...current, [data.step]: status }));
          if (data.kind === "step_start")
            addActivity({ type: "tool", title: `${data.agent} · ${data.phase}`, detail: data.description });
          if (data.kind === "step_end")
            addActivity({ type: status === "failed" ? "status" : "result", title: `${data.agent} → ${data.outcome}`, detail: data.output });
        }
        if (name === "usage") addActivity({ type: "status", title: "Usage", detail: data.summary });
        if (name === "warning") addActivity({ type: "status", title: "Warning", detail: data.message });
        if (name === "error") onError(data.message || "AXIO run failed.");
        if (["run_completed", "run_cancelled", "error"].includes(name)) {
          source.close();
          setBusy(false);
          setRunId(null);
          setStreaming("");
          try {
            setConversation(await request<Conversation>(`/api/conversations/${active.id}`));
            onConversationsChanged();
          } catch {}
        }
      });
    }
    source.onerror = () => {
      if (source.readyState !== EventSource.CLOSED) onError("The live AXIO connection was interrupted.");
    };
  }

  async function send(prompt: string, orchestrate = false) {
    const text = prompt.trim();
    if (!text || busy) return;
    setBusy(true);
    setStreaming("");
    if (orchestrate) {
      setAgentPlan(null);
      setStepStatus({});
    }
    try {
      let active = conversation;
      if (!active || active.mode !== mode) {
        active = await request<Conversation>("/api/conversations", {
          method: "POST",
          body: JSON.stringify({ mode, title: "New conversation", workspace_id: workspaceId }),
        });
        setActivity([]);
        setApprovals([]);
        setDiff("");
        onConversationsChanged();
      }
      const optimistic: Message = { id: crypto.randomUUID(), role: "user", content: text };
      setConversation({ ...active, messages: [...(active.messages || []), optimistic] });
      const run = await request<{ id: string }>(`/api/conversations/${active.id}/messages`, {
        method: "POST",
        body: JSON.stringify({ content: text, file_ids: fileIds(), orchestrate }),
      });
      setRunId(run.id);
      connect(run.id, active);
    } catch (reason) {
      setBusy(false);
      onError(err(reason));
    }
  }

  async function cancel() {
    if (runId) await request(`/api/runs/${runId}/cancel`, { method: "POST" }).catch(() => {});
  }

  async function decide(id: string, decision: "approve" | "deny") {
    await request(`/api/approvals/${id}/${decision}`, {
      method: "POST",
      body: JSON.stringify({ note: decision === "deny" ? "Denied in AXIO Console." : "" }),
    });
  }

  return {
    mode, conversation, setConversation, streaming, busy, runId,
    activity, approvals, diff, agentPlan, stepStatus, reset, open, send, cancel, decide,
  };
}

// ---------------------------------------------------------------------------

function buildTree(files: FileItem[]) {
  type Node = { name: string; path: string; file?: FileItem; children: Map<string, Node> };
  const root: Node = { name: "", path: "", children: new Map() };
  for (const file of files) {
    const parts = file.relative_path.split("/");
    let node = root;
    parts.forEach((part, index) => {
      const path = parts.slice(0, index + 1).join("/");
      if (!node.children.has(part))
        node.children.set(part, { name: part, path, children: new Map() });
      node = node.children.get(part)!;
      if (index === parts.length - 1) node.file = file;
    });
  }
  return root;
}

export function ConsoleApp() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [files, setFiles] = useState<FileItem[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [stageModule, setStageModule] = useState<StageModule>("code");
  const [dockOpen, setDockOpen] = useState(true);
  const [health, setHealth] = useState<Health>({ ollama: false, claude: false, postgres: null, searxng: false });
  const [localOnly, setLocalOnly] = useState(false);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [workspaceModal, setWorkspaceModal] = useState(false);
  const [workspacePath, setWorkspacePath] = useState("");
  const [error, setError] = useState("");

  const selectedRef = useRef<string[]>([]);
  selectedRef.current = selected;

  const refreshConversations = useCallback(async () => {
    try {
      setConversations(await request<Conversation[]>("/api/conversations"));
    } catch (reason) {
      setError(err(reason));
    }
  }, []);

  const chat = useSurface({
    mode: "chat",
    workspaceId: null,
    fileIds: () => [],
    onConversationsChanged: refreshConversations,
    onError: setError,
  });
  const stage = useSurface({
    mode: stageModule,
    workspaceId: workspace?.id || null,
    fileIds: () => selectedRef.current,
    onConversationsChanged: refreshConversations,
    onError: setError,
  });

  const loadHealth = useCallback(async (silent = false) => {
    try {
      const value = await request<{
        ollama: { available: boolean };
        claude: { configured: boolean };
        postgres: { available: boolean | null };
        searxng: { available: boolean };
        local_only: boolean;
      }>("/api/health");
      setHealth({
        ollama: value.ollama.available,
        claude: value.claude.configured,
        postgres: value.postgres?.available ?? null,
        searxng: value.searxng?.available ?? false,
      });
      setLocalOnly(value.local_only);
    } catch (reason) {
      if (!silent) setError(`AXIO backend unavailable: ${err(reason)}`);
    }
  }, []);

  useEffect(() => {
    void refreshConversations();
    request<Workspace[]>("/api/workspaces").then(setWorkspaces).catch(() => {});
    void loadHealth();
    const timer = setInterval(() => void loadHealth(true), 15000);
    const loadJobs = () => request<Job[]>("/api/jobs").then(setJobs).catch(() => {});
    void loadJobs();
    const jobTimer = setInterval(loadJobs, 5000);
    return () => {
      clearInterval(timer);
      clearInterval(jobTimer);
    };
  }, [refreshConversations, loadHealth]);

  async function stopJob(id: string) {
    try {
      await request(`/api/jobs/${id}/stop`, { method: "POST" });
    } catch (reason) {
      setError(err(reason));
    }
    request<Job[]>("/api/jobs").then(setJobs).catch(() => {});
  }

  useEffect(() => {
    if (!workspace) {
      setFiles([]);
      return;
    }
    request<FileItem[]>(`/api/workspaces/${workspace.id}/files`)
      .then(setFiles)
      .catch((reason) => setError(err(reason)));
  }, [workspace]);

  const groups = useMemo(() => {
    const result = new Map<string, Conversation[]>();
    for (const item of conversations) {
      const key = dateGroup(item.updated_at);
      result.set(key, [...(result.get(key) || []), item]);
    }
    return [...result.entries()];
  }, [conversations]);

  const tree = useMemo(() => buildTree(files), [files]);

  async function openConversation(item: Conversation) {
    setError("");
    const full = await request<Conversation>(`/api/conversations/${item.id}`);
    if (full.mode === "chat") {
      chat.open(full);
    } else {
      setStageModule(full.mode as StageModule);
      const nextWorkspace = workspaces.find((value) => value.id === full.workspace_id) || null;
      setWorkspace(nextWorkspace);
      setSelected([]);
      stage.open(full);
    }
  }

  async function chooseWorkspace(value: Workspace) {
    setWorkspace(value);
    setSelected([]);
    setWorkspaceModal(false);
    if (stage.conversation) {
      stage.setConversation(
        await request<Conversation>(`/api/conversations/${stage.conversation.id}`, {
          method: "PATCH",
          body: JSON.stringify({ workspace_id: value.id }),
        }),
      );
    }
  }

  async function registerWorkspace(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const value = await request<Workspace>("/api/workspaces/open", {
        method: "POST",
        body: JSON.stringify({ path: workspacePath }),
      });
      setWorkspaces(await request<Workspace[]>("/api/workspaces"));
      await chooseWorkspace(value);
      setWorkspacePath("");
    } catch (reason) {
      setError(err(reason));
    }
  }

  async function toggleBackend(next: boolean) {
    try {
      const result = await request<{ local_only: boolean; warning?: string }>("/api/runtime-mode", {
        method: "POST",
        body: JSON.stringify({ local_only: next }),
      });
      setLocalOnly(result.local_only);
      if (result.warning) setError(result.warning);
      void loadHealth();
    } catch (reason) {
      setError(err(reason));
    }
  }

  function toggleFile(id: string) {
    setSelected((current) =>
      current.includes(id) ? current.filter((value) => value !== id) : [...current, id],
    );
  }

  const stageModelLabel = stageModule === "code" && !localOnly ? MODEL_LABELS.code : MODEL_LABELS.local;

  return (
    <main className={`console ${dockOpen ? "" : "dock-collapsed"}`}>
      <Rail
        groups={groups}
        activeIds={[chat.conversation?.id, stage.conversation?.id]}
        onNewChat={() => chat.reset()}
        onNewStage={() => stage.reset()}
        onOpen={(item) => void openConversation(item)}
        health={health}
        localOnly={localOnly}
        onToggleBackend={(next) => void toggleBackend(next)}
      />

      {dockOpen ? (
        <ChatDock surface={chat} online={health.ollama} onCollapse={() => setDockOpen(false)} />
      ) : (
        <button className="dock-reopen" onClick={() => setDockOpen(true)} aria-label="Open chat panel">
          <span className="mode-glyph glyph-chat" aria-hidden="true" />
          <span className="dock-reopen-label">CHAT</span>
        </button>
      )}

      <Stage
        module={stageModule}
        setModule={(next) => {
          setStageModule(next);
          if (stage.conversation && stage.conversation.mode !== next) stage.reset();
        }}
        surface={stage}
        workspace={workspace}
        tree={tree}
        fileCount={files.length}
        selected={selected}
        toggleFile={toggleFile}
        modelLabel={stageModelLabel}
        online={stageModule === "code" && !localOnly ? health.claude : health.ollama}
        onOpenWorkspace={() => setWorkspaceModal(true)}
        jobs={jobs}
        onStopJob={(id) => void stopJob(id)}
        error={error}
        clearError={() => setError("")}
      />

      {workspaceModal && (
        <div className="modal-backdrop" onMouseDown={() => setWorkspaceModal(false)}>
          <section className="workspace-modal" onMouseDown={(event) => event.stopPropagation()}>
            <header>
              <div>
                <p>LOCAL WORKSPACES</p>
                <h2>Open a folder in AXIO</h2>
              </div>
              <button onClick={() => setWorkspaceModal(false)}>×</button>
            </header>
            <p>AXIO only reads or changes files inside the workspace you select. Protected actions still require approval.</p>
            <form onSubmit={registerWorkspace}>
              <input
                autoFocus
                value={workspacePath}
                onChange={(event) => setWorkspacePath(event.target.value)}
                placeholder={"C:\\Users\\AXIO\\Documents\\my-project"}
              />
              <button>Open</button>
            </form>
            {!!workspaces.length && (
              <div className="recent-workspaces">
                <span>Recent</span>
                {workspaces.map((item) => (
                  <button key={item.id} onClick={() => void chooseWorkspace(item)}>
                    <span className="folder-icon" />
                    <span>
                      <strong>{item.name}</strong>
                      <small>{item.path}</small>
                    </span>
                    <i>→</i>
                  </button>
                ))}
              </div>
            )}
          </section>
        </div>
      )}
    </main>
  );
}

// --- Rail -------------------------------------------------------------------
function StatusChip({ label, state }: { label: string; state: boolean | null }) {
  const cls = state === null ? "off disabled" : state ? "on" : "off";
  return (
    <span className={`status-chip ${cls}`}>
      <i />
      {label}
    </span>
  );
}

function Rail(props: {
  groups: [string, Conversation[]][];
  activeIds: (string | undefined)[];
  onNewChat: () => void;
  onNewStage: () => void;
  onOpen: (item: Conversation) => void;
  health: Health;
  localOnly: boolean;
  onToggleBackend: (next: boolean) => void;
}) {
  const { groups, activeIds, onNewChat, onNewStage, onOpen, health, localOnly, onToggleBackend } = props;
  return (
    <aside className="rail" aria-label="Navigation">
      <div className="brand-row">
        <div className="brand-mark" aria-hidden="true">
          <span />
        </div>
        <div className="brand-copy">
          <strong>AXIO</strong>
          <small>CONSOLE</small>
        </div>
      </div>

      <div className="rail-new">
        <button className="new-thread" onClick={onNewChat}>
          <span className="plus">＋</span>
          <span>New chat</span>
        </button>
        <button className="new-thread ghost" onClick={onNewStage}>
          <span className="plus">＋</span>
          <span>New build</span>
        </button>
      </div>

      <div className="history">
        <div className="history-heading">
          <span>Conversations</span>
        </div>
        {!groups.length && <p className="empty-history">Your conversations will appear here.</p>}
        {groups.map(([label, items]) => (
          <section key={label}>
            <h2>{label}</h2>
            {items.map((item) => (
              <button
                key={item.id}
                className={activeIds.includes(item.id) ? "thread active" : "thread"}
                onClick={() => onOpen(item)}
              >
                <span>{item.title}</span>
                <small>{item.mode}</small>
              </button>
            ))}
          </section>
        ))}
      </div>

      <div className="launch-panel">
        <div className="section-label">
          <span>Backend</span>
        </div>
        <div className="backend-switch" role="tablist">
          <button className={localOnly ? "active" : ""} onClick={() => onToggleBackend(true)}>
            Gemma local
          </button>
          <button className={!localOnly ? "active" : ""} onClick={() => onToggleBackend(false)}>
            Local + API
          </button>
        </div>
        <div className="status-grid">
          <StatusChip label="Ollama" state={health.ollama} />
          <StatusChip label="Claude" state={health.claude} />
          <StatusChip label="Postgres" state={health.postgres} />
          <StatusChip label="SearXNG" state={health.searxng} />
        </div>
      </div>

      <div className="rail-footer">
        <span className="avatar">M</span>
        <span>
          <strong>Michael</strong>
          <small>Local workspace</small>
        </span>
      </div>
    </aside>
  );
}

// --- Transcript + Composer (shared) ----------------------------------------
function Transcript(props: {
  messages: Message[];
  streaming: string;
  busy: boolean;
  welcome: ReactNode;
  compact?: boolean;
}) {
  const { messages, streaming, busy, welcome, compact } = props;
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streaming, busy]);

  if (!messages.length && !streaming) return <div className="welcome-wrap">{welcome}</div>;
  return (
    <div className={`message-list ${compact ? "compact" : ""}`}>
      {messages.map((message) => (
        <article key={message.id} className={`message ${message.role}`}>
          <div className="message-author">
            {message.role === "assistant" ? (
              <div className="brand-mark mini">
                <span />
              </div>
            ) : (
              <span className="user-avatar">M</span>
            )}
            <strong>{message.role === "assistant" ? "AXIO" : "You"}</strong>
            {message.model && <small>{message.model}</small>}
          </div>
          <div className="message-body">{message.content}</div>
        </article>
      ))}
      {streaming && (
        <article className="message assistant streaming">
          <div className="message-author">
            <div className="brand-mark mini">
              <span />
            </div>
            <strong>AXIO</strong>
            <small>working</small>
          </div>
          <div className="message-body">
            {streaming}
            <span className="cursor" />
          </div>
        </article>
      )}
      {busy && !streaming && (
        <div className="thinking">
          <span />
          <span />
          <span />
          <em>AXIO is working</em>
        </div>
      )}
      <div ref={endRef} />
    </div>
  );
}

function Composer(props: {
  placeholder: string;
  busy: boolean;
  modelLabel: string;
  cloud?: boolean;
  onSend: (text: string) => void;
  onCancel: () => void;
}) {
  const { placeholder, busy, modelLabel, cloud, onSend, onCancel } = props;
  const [input, setInput] = useState("");
  function submit() {
    if (!input.trim() || busy) return;
    onSend(input);
    setInput("");
  }
  function keyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }
  return (
    <div className="composer">
      <textarea
        value={input}
        onChange={(event) => setInput(event.target.value)}
        onKeyDown={keyDown}
        placeholder={placeholder}
        rows={1}
        aria-label="Message AXIO"
      />
      <div className="composer-tools">
        <button className="model-pill">
          <span className={cloud ? "cloud" : "local"} />
          {modelLabel}
          <small>{cloud ? "cloud" : "local"}</small>
        </button>
        {busy ? (
          <button className="send stop" onClick={onCancel} aria-label="Stop run">
            ■
          </button>
        ) : (
          <button className="send" onClick={submit} disabled={!input.trim()} aria-label="Send message">
            ↑
          </button>
        )}
      </div>
    </div>
  );
}

// --- Chat dock --------------------------------------------------------------
function ChatDock({ surface, online, onCollapse }: { surface: Surface; online: boolean; onCollapse: () => void }) {
  const messages = surface.conversation?.messages || [];
  return (
    <section className="chat-dock" aria-label="Chat">
      <header className="dock-head">
        <span className="mode-glyph glyph-chat" aria-hidden="true" />
        <strong>Chat</strong>
        <span className={`health-dot ${online ? "online" : ""}`} />
        <small>{MODEL_LABELS.local}</small>
        <button className="dock-collapse" onClick={onCollapse} aria-label="Collapse chat panel" title="Collapse">
          ‹
        </button>
      </header>
      <div className="dock-body">
        <Transcript
          messages={messages}
          streaming={surface.streaming}
          busy={surface.busy}
          compact
          welcome={
            <div className="welcome mini">
              <div className="welcome-orbit">
                <div className="brand-mark large">
                  <span />
                </div>
              </div>
              <p className="eyebrow">LOCAL INTELLIGENCE</p>
              <h1>How can AXIO help?</h1>
              <p>Ask questions, search, and review docs while you build — powered locally with persistent memory.</p>
            </div>
          }
        />
      </div>
      <div className="dock-composer">
        <Composer
          placeholder="Message AXIO…"
          busy={surface.busy}
          modelLabel={MODEL_LABELS.local}
          onSend={(text) => void surface.send(text)}
          onCancel={() => void surface.cancel()}
        />
      </div>
    </section>
  );
}

// --- Stage ------------------------------------------------------------------
type TreeNode = { name: string; path: string; file?: FileItem; children: Map<string, TreeNode> };

function FileTree({ node, selected, toggle, depth = 0 }: {
  node: TreeNode;
  selected: string[];
  toggle: (id: string) => void;
  depth?: number;
}) {
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const entries = [...node.children.values()].sort((a, b) => {
    const aDir = a.children.size > 0 ? 0 : 1;
    const bDir = b.children.size > 0 ? 0 : 1;
    return aDir - bDir || a.name.localeCompare(b.name);
  });
  return (
    <div className="tree">
      {entries.map((child) => {
        const isDir = child.children.size > 0;
        const isOpen = !collapsed[child.path];
        if (isDir) {
          return (
            <div key={child.path}>
              <button
                className="tree-row dir"
                style={{ paddingLeft: 8 + depth * 12 }}
                onClick={() => setCollapsed((c) => ({ ...c, [child.path]: isOpen }))}
              >
                <span className="tree-caret">{isOpen ? "▾" : "▸"}</span>
                <span className="tree-name">{child.name}</span>
              </button>
              {isOpen && <FileTree node={child} selected={selected} toggle={toggle} depth={depth + 1} />}
            </div>
          );
        }
        const id = child.file!.id;
        const isSelected = selected.includes(id);
        return (
          <button
            key={child.path}
            className={`tree-row file ${isSelected ? "selected" : ""}`}
            style={{ paddingLeft: 8 + depth * 12 }}
            onClick={() => toggle(id)}
            title={child.file!.relative_path}
          >
            <span className="tree-dot" />
            <span className="tree-name">{child.name}</span>
            <small>{fileSize(child.file!.size)}</small>
          </button>
        );
      })}
    </div>
  );
}

function ActivityLog({ activity }: { activity: Activity[] }) {
  if (!activity.length)
    return (
      <div className="empty-state">
        <strong>Console idle</strong>
        <p>Status, tool calls and results stream here as AXIO works.</p>
      </div>
    );
  return (
    <div className="console-log">
      {activity.map((item) => (
        <div key={item.id} className={`log-line ${item.type}`}>
          <span className="log-glyph">
            {item.type === "tool" ? "▸" : item.type === "result" ? "✓" : "•"}
          </span>
          <div>
            <span className="log-title">{item.title}</span>
            {item.detail && <span className="log-detail">{item.detail}</span>}
          </div>
        </div>
      ))}
    </div>
  );
}

function AgentFlow({ plan, stepStatus }: { plan: AgentPlan | null; stepStatus: Record<number, string> }) {
  if (!plan)
    return (
      <div className="empty-state">
        <strong>Agent flow</strong>
        <p>Turn on ⚡ Multi-agent and send a Code task. The plan, agent roster and live per-step flow (dispatch → done / fallback / skip) stream here.</p>
      </div>
    );
  return (
    <div className="agent-flow">
      <div className="agent-roster">
        {plan.agents.map((agent) => (
          <span key={agent.name} className="agent-chip" title={agent.description}>
            {agent.name}
            {agent.internet && <i title="internet access">🌐</i>}
          </span>
        ))}
      </div>
      <div className="plan-steps">
        {plan.steps.map((step) => {
          const status = stepStatus[step.id] || "pending";
          return (
            <div key={step.id} className={`plan-step ${status}`}>
              <span className={`step-badge ${status}`}>{status}</span>
              <div className="step-body">
                <div className="step-head">
                  <span className="step-phase">{step.phase}</span>
                  <span className="step-agent">{step.agent}</span>
                  {!!step.depends_on.length && <span className="step-deps">after {step.depends_on.join(", ")}</span>}
                </div>
                <span className="step-desc">{step.description}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Stage(props: {
  module: StageModule;
  setModule: (next: StageModule) => void;
  surface: Surface;
  workspace: Workspace | null;
  tree: TreeNode;
  fileCount: number;
  selected: string[];
  toggleFile: (id: string) => void;
  modelLabel: string;
  online: boolean;
  onOpenWorkspace: () => void;
  jobs: Job[];
  onStopJob: (id: string) => void;
  error: string;
  clearError: () => void;
}) {
  const {
    module, setModule, surface, workspace, tree, fileCount, selected, toggleFile,
    modelLabel, online, onOpenWorkspace, jobs, onStopJob, error, clearError,
  } = props;
  const [tab, setTab] = useState<"console" | "agents" | "changes">("console");
  const [orchestrate, setOrchestrate] = useState(false);
  const messages = surface.conversation?.messages || [];
  const copy = stageCopy[module];
  const cloud = module === "code" && modelLabel === MODEL_LABELS.code;

  const transcript = (
    <Transcript
      messages={messages}
      streaming={surface.streaming}
      busy={surface.busy}
      welcome={
        <div className="welcome">
          <p className="eyebrow">{copy.kicker}</p>
          <h1>{copy.title}</h1>
          <p>{copy.subtitle}</p>
        </div>
      }
    />
  );
  const composer = (
    <Composer
      placeholder={copy.placeholder}
      busy={surface.busy}
      modelLabel={modelLabel}
      cloud={cloud}
      onSend={(text) => void surface.send(text, module === "code" && orchestrate)}
      onCancel={() => void surface.cancel()}
    />
  );

  return (
    <section className="stage" aria-label="Build stage">
      <header className="stage-top">
        <div className="module-switch" role="tablist">
          {(["cowork", "code"] as StageModule[]).map((item) => (
            <button key={item} className={module === item ? "active" : ""} onClick={() => setModule(item)}>
              <span className={`mode-glyph glyph-${item}`} aria-hidden="true" />
              {item === "cowork" ? "Cowork" : "Code"}
            </button>
          ))}
        </div>
        <button className="stage-workspace" onClick={onOpenWorkspace}>
          <span className="folder-icon" />
          {workspace ? workspace.name : "Open workspace"}
        </button>
        <div className="stage-actions">
          {module === "code" && (
            <button
              className={`orchestrate-toggle ${orchestrate ? "active" : ""}`}
              onClick={() => setOrchestrate((v) => !v)}
              title="Run the multi-agent orchestrator instead of a single agent"
            >
              ⚡ Multi-agent
            </button>
          )}
          <span className={`health-dot ${online ? "online" : ""}`} />
          <span className="backend-label">
            {cloud ? "Cloud" : "Local"} · {modelLabel}
          </span>
        </div>
      </header>

      {error && (
        <div className="error-banner">
          <strong>{/connection|unavailable|interrupted/i.test(error) ? "Connection issue" : "Run issue"}</strong>
          <span>{error}</span>
          <button onClick={clearError}>×</button>
        </div>
      )}

      {module === "code" ? (
        <div className="code-grid">
          <aside className="code-files">
            <div className="panel-label">
              <span>Files</span>
              <small>{selected.length ? `${selected.length} in context` : `${fileCount}`}</small>
            </div>
            {workspace ? (
              fileCount ? (
                <div className="tree-scroll">
                  <FileTree node={tree} selected={selected} toggle={toggleFile} />
                </div>
              ) : (
                <p className="hint">No supported files found.</p>
              )
            ) : (
              <button className="open-ws" onClick={onOpenWorkspace}>
                Open a workspace to browse files
              </button>
            )}
            <div className="panel-label spaced">
              <span>Background jobs</span>
              {!!jobs.length && <small>{jobs.length}</small>}
            </div>
            {jobs.length ? (
              <div className="jobs-list">
                {jobs.map((job) => (
                  <div key={job.id} className="job-row">
                    <span className={`job-dot ${job.status}`} />
                    <div className="job-meta">
                      <strong>{job.script}</strong>
                      <small>PID {job.pid ?? "—"} · {job.status}</small>
                    </div>
                    {job.status === "running" && (
                      <button className="job-stop" onClick={() => onStopJob(job.id)} title="Stop job">
                        ■
                      </button>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty-state small">
                <strong>No jobs</strong>
                <p>Long-running dev servers (npm dev/watch) launched by the agent appear here.</p>
              </div>
            )}
          </aside>

          <div className="code-main">
            <div className="stage-convo">{transcript}</div>
            <div className="stage-composer-wrap">{composer}</div>
          </div>

          <aside className="code-activity">
            <div className="panel-tabs">
              <button className={tab === "console" ? "active" : ""} onClick={() => setTab("console")}>
                Console{!!surface.activity.length && <span>{surface.activity.length}</span>}
              </button>
              <button className={tab === "agents" ? "active" : ""} onClick={() => setTab("agents")}>
                Agents{surface.agentPlan && <span>{surface.agentPlan.steps.length}</span>}
              </button>
              <button className={tab === "changes" ? "active" : ""} onClick={() => setTab("changes")}>
                Changes{!!surface.approvals.length && <span>{surface.approvals.length}</span>}
              </button>
            </div>
            <div className="panel-scroll">
              {tab === "console" && <ActivityLog activity={surface.activity} />}
              {tab === "agents" && <AgentFlow plan={surface.agentPlan} stepStatus={surface.stepStatus} />}
              {tab === "changes" && (
                <>
                  {surface.approvals.map((item) => (
                    <section className="approval-card" key={item.approval_id}>
                      <p>Approval required</p>
                      <h3>{item.action.replace("_", " ")}</h3>
                      <pre>{item.detail.command || item.detail.path || item.detail.diff}</pre>
                      <div>
                        <button onClick={() => void surface.decide(item.approval_id, "deny")}>Deny</button>
                        <button className="approve" onClick={() => void surface.decide(item.approval_id, "approve")}>
                          Approve
                        </button>
                      </div>
                    </section>
                  ))}
                  {surface.diff && (
                    <section className="diff-card">
                      <div className="panel-label">
                        <span>Latest diff</span>
                      </div>
                      <pre>{surface.diff}</pre>
                    </section>
                  )}
                  {!surface.approvals.length && !surface.diff && (
                    <div className="empty-state">
                      <strong>No changes yet</strong>
                      <p>File diffs and approvals appear here before anything is written.</p>
                    </div>
                  )}
                </>
              )}
            </div>
          </aside>
        </div>
      ) : (
        <div className="cowork-grid">
          <div className="code-main">
            <div className="stage-convo">{transcript}</div>
            <div className="stage-composer-wrap">{composer}</div>
          </div>
          <aside className="cowork-context">
            <div className="panel-label">
              <span>Workspace</span>
              <small onClick={onOpenWorkspace} className="link">
                Change
              </small>
            </div>
            {workspace ? (
              <div className="workspace-value">
                <span className="folder-icon" />
                <div>
                  <strong>{workspace.name}</strong>
                  <small>{workspace.path}</small>
                </div>
              </div>
            ) : (
              <button className="open-ws" onClick={onOpenWorkspace}>
                Open a workspace for file-aware work
              </button>
            )}
            <div className="panel-label spaced">
              <span>Context files</span>
              <small>{selected.length} selected</small>
            </div>
            {workspace && fileCount ? (
              <div className="tree-scroll">
                <FileTree node={tree} selected={selected} toggle={toggleFile} />
              </div>
            ) : (
              <p className="hint">Select files to bring into context.</p>
            )}
          </aside>
        </div>
      )}
    </section>
  );
}
