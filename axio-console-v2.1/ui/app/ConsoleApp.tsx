"use client";

import { FormEvent, KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";

type Mode = "chat" | "cowork" | "code";
type Message = { id: string; role: "user" | "assistant"; content: string; model?: string };
type Conversation = {
  id: string; mode: Mode; title: string; workspace_id?: string | null;
  messages: Message[]; updated_at: string;
};
type Workspace = { id: string; name: string; path: string };
type FileItem = { id: string; name: string; relative_path: string; size: number };
type Activity = { id: string; type: string; title: string; detail?: string };
type Approval = {
  approval_id: string; action: string;
  detail: { path?: string; command?: string; diff?: string };
};

const API = process.env.NEXT_PUBLIC_AXIO_API || "http://127.0.0.1:8765";
const copy: Record<Mode, { label: string; kicker: string; title: string; subtitle: string }> = {
  chat: {
    label: "Chat", kicker: "LOCAL INTELLIGENCE", title: "How can AXIO help?",
    subtitle: "A private conversation powered by gemma4:12b and your persistent memory.",
  },
  cowork: {
    label: "Cowork", kicker: "WORKSPACE INTELLIGENCE", title: "Work across your files",
    subtitle: "Select a workspace and bring the right documents into context.",
  },
  code: {
    label: "Code", kicker: "CLAUDE CODING AGENT", title: "Build with AXIO",
    subtitle: "Agentic coding on the Claude API with visible tools, approvals, diffs, and verification.",
  },
};
// Per-mode model shown in the UI. Chat + Cowork run locally on gemma4:12b;
// Code boosts to the Claude API (the frontier agentic tier).
const modelByMode: Record<Mode, string> = {
  chat: "gemma4:12b",
  cowork: "gemma4:12b",
  code: "claude-opus-4-8",
};
// Modes whose backend is the Claude cloud tier (vs local Ollama).
const cloudModes: Record<Mode, boolean> = { chat: false, cowork: false, code: true };
const suggestions: Record<Mode, string[]> = {
  chat: ["Plan my priorities for today", "Explain a complex idea simply", "Recall what we decided last time"],
  cowork: ["Summarize the selected files", "Find risks and open decisions", "Draft an implementation brief"],
  code: ["Audit this workspace first", "Fix the failing tests", "Implement the next safe vertical slice"],
};

function err(value: unknown) { return value instanceof Error ? value.message : String(value); }
function dateGroup(value: string) {
  const date = new Date(value);
  return date.toDateString() === new Date().toDateString()
    ? "Today" : date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
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
    try { detail = (await response.json()).detail || detail; } catch {}
    throw new Error(detail);
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

export function ConsoleApp() {
  const [mode, setMode] = useState<Mode>("chat");
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [files, setFiles] = useState<FileItem[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState("");
  const [runId, setRunId] = useState<string | null>(null);
  const [activity, setActivity] = useState<Activity[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [diff, setDiff] = useState("");
  const [panel, setPanel] = useState<"context" | "activity">("context");
  const [sidebar, setSidebar] = useState(true);
  const [right, setRight] = useState(true);
  const [workspaceModal, setWorkspaceModal] = useState(false);
  const [workspacePath, setWorkspacePath] = useState("");
  const [health, setHealth] = useState({ ollama: false, claude: false });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const sourceRef = useRef<EventSource | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  const messages = useMemo(() => conversation?.messages || [], [conversation]);
  const groups = useMemo(() => {
    const result = new Map<string, Conversation[]>();
    for (const item of conversations) {
      const key = dateGroup(item.updated_at);
      result.set(key, [...(result.get(key) || []), item]);
    }
    return [...result.entries()];
  }, [conversations]);

  const refreshConversations = async () =>
    setConversations(await request<Conversation[]>("/api/conversations"));
  const refreshWorkspaces = async () => {
    const values = await request<Workspace[]>("/api/workspaces");
    setWorkspaces(values);
    return values;
  };

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      request<Conversation[]>("/api/conversations"),
      request<Workspace[]>("/api/workspaces"),
      request<{ ollama: { available: boolean }; claude: { configured: boolean } }>("/api/health")
    ]).then(([conversationValues, workspaceValues, healthValue]) => {
      if (cancelled) return;
      setConversations(conversationValues);
      setWorkspaces(workspaceValues);
      setHealth({
        ollama: healthValue.ollama.available,
        claude: healthValue.claude.configured,
      });
    }).catch((reason) => {
      if (!cancelled) setError(`AXIO backend unavailable: ${err(reason)}`);
    });
    return () => {
      cancelled = true;
      sourceRef.current?.close();
    };
  }, []);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); },
    [messages, streaming, activity]);

  useEffect(() => {
    if (!workspace) return;
    request<FileItem[]>(`/api/workspaces/${workspace.id}/files`)
      .then(setFiles).catch((reason) => setError(err(reason)));
  }, [workspace]);

  async function newConversation(nextMode = mode) {
    const value = await request<Conversation>("/api/conversations", {
      method: "POST",
      body: JSON.stringify({
        mode: nextMode, title: "New conversation", workspace_id: workspace?.id || null,
      }),
    });
    setConversation(value); setMode(nextMode); setActivity([]); setApprovals([]);
    setDiff(""); setStreaming(""); await refreshConversations();
    return value;
  }

  async function openConversation(item: Conversation) {
    const full = await request<Conversation>(`/api/conversations/${item.id}`);
    setConversation(full); setMode(full.mode); setActivity([]); setApprovals([]);
    setDiff(""); setError(""); setSelected([]);
    const nextWorkspace = workspaces.find((value) => value.id === full.workspace_id) || null;
    setWorkspace(nextWorkspace);
    if (!nextWorkspace) setFiles([]);
  }

  async function chooseWorkspace(value: Workspace) {
    setWorkspace(value); setSelected([]); setWorkspaceModal(false);
    if (conversation) {
      setConversation(await request<Conversation>(`/api/conversations/${conversation.id}`, {
        method: "PATCH", body: JSON.stringify({ workspace_id: value.id }),
      }));
    }
  }

  async function registerWorkspace(event: FormEvent) {
    event.preventDefault(); setError("");
    try {
      const value = await request<Workspace>("/api/workspaces/open", {
        method: "POST", body: JSON.stringify({ path: workspacePath }),
      });
      await refreshWorkspaces(); await chooseWorkspace(value); setWorkspacePath("");
    } catch (reason) { setError(err(reason)); }
  }

  function addActivity(item: Omit<Activity, "id">) {
    setActivity((current) => [...current, { ...item, id: crypto.randomUUID() }]);
  }

  function connectStream(id: string, active: Conversation) {
    sourceRef.current?.close();
    const source = new EventSource(`${API}/api/runs/${id}/events`);
    sourceRef.current = source;
    const events = ["run_started", "status", "token", "message", "tool_started",
      "tool_result", "approval_required", "approval_resolved", "diff", "warning",
      "error", "run_cancelled", "run_completed"];
    for (const name of events) {
      source.addEventListener(name, async (raw) => {
        const data = JSON.parse((raw as MessageEvent).data).data || {};
        if (name === "token") setStreaming((current) => current + (data.text || ""));
        if (name === "status") addActivity({
          type: "status", title: data.label || "Working", detail: data.model,
        });
        if (name === "tool_started") {
          setPanel("activity"); setRight(true);
          addActivity({ type: "tool", title: data.tool, detail: JSON.stringify(data.arguments || {}) });
        }
        if (name === "tool_result") addActivity({
          type: "result", title: `${data.tool} completed`, detail: data.result,
        });
        if (name === "approval_required") {
          setPanel("activity"); setRight(true);
          setApprovals((current) => [...current, data]);
        }
        if (name === "approval_resolved") setApprovals((current) =>
          current.filter((item) => item.approval_id !== data.approval_id));
        if (name === "diff") {
          setDiff(data.diff || ""); setPanel("activity"); setRight(true);
        }
        if (name === "warning") addActivity({
          type: "status", title: "Warning", detail: data.message,
        });
        if (name === "error") setError(data.message || "AXIO run failed.");
        if (["run_completed", "run_cancelled", "error"].includes(name)) {
          source.close(); setBusy(false); setRunId(null); setStreaming("");
          try {
            setConversation(await request<Conversation>(`/api/conversations/${active.id}`));
            await refreshConversations();
          } catch {}
        }
      });
    }
    source.onerror = () => {
      if (source.readyState !== EventSource.CLOSED)
        setError("The live AXIO connection was interrupted.");
    };
  }

  async function send() {
    const prompt = input.trim();
    if (!prompt || busy) return;
    setError(""); setBusy(true); setInput(""); setStreaming("");
    try {
      let active = conversation;
      if (!active || active.mode !== mode) active = await newConversation(mode);
      const optimistic: Message = {
        id: crypto.randomUUID(), role: "user", content: prompt,
      };
      setConversation({ ...active, messages: [...(active.messages || []), optimistic] });
      const run = await request<{ id: string }>(
        `/api/conversations/${active.id}/messages`,
        { method: "POST", body: JSON.stringify({ content: prompt, file_ids: selected }) },
      );
      setRunId(run.id); connectStream(run.id, active);
    } catch (reason) { setBusy(false); setError(err(reason)); }
  }

  function keyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault(); void send();
    }
  }

  async function decide(id: string, decision: "approve" | "deny") {
    await request(`/api/approvals/${id}/${decision}`, {
      method: "POST",
      body: JSON.stringify({ note: decision === "deny" ? "Denied in AXIO Console." : "" }),
    });
  }

  function changeMode(next: Mode) {
    setMode(next); if (conversation?.mode !== next) setConversation(null);
    setStreaming(""); setError("");
  }

  return (
    <main className={`console mode-${mode} ${sidebar ? "" : "sidebar-collapsed"} ${right ? "" : "right-collapsed"}`}>
      <aside className="sidebar" aria-label="Conversation navigation">
        <div className="brand-row">
          <div className="brand-mark" aria-hidden="true"><span /></div>
          <div className="brand-copy"><strong>AXIO</strong><small>CONSOLE</small></div>
          <button className="icon-button collapse-button" onClick={() => setSidebar(false)} aria-label="Collapse sidebar">‹</button>
        </div>
        <button className="new-thread" onClick={() => void newConversation()}>
          <span className="plus">＋</span><span>New conversation</span><kbd>Ctrl K</kbd>
        </button>
        <nav className="mode-nav" aria-label="AXIO modes">
          {(["chat", "cowork", "code"] as Mode[]).map((item) => (
            <button key={item} className={mode === item ? "active" : ""} onClick={() => changeMode(item)}>
              <span className={`mode-glyph glyph-${item}`} aria-hidden="true" />
              <span>{copy[item].label}</span>{item === "code" && <em>API</em>}
            </button>
          ))}
        </nav>
        <div className="history">
          <div className="history-heading"><span>Conversations</span><button aria-label="Search conversations">⌕</button></div>
          {!groups.length && <p className="empty-history">Your conversations will appear here.</p>}
          {groups.map(([label, items]) => (
            <section key={label}><h2>{label}</h2>
              {items.map((item) => (
                <button key={item.id} className={conversation?.id === item.id ? "thread active" : "thread"} onClick={() => void openConversation(item)}>
                  <span>{item.title}</span><small>{item.mode}</small>
                </button>
              ))}
            </section>
          ))}
        </div>
        <div className="sidebar-footer">
          <button onClick={() => setWorkspaceModal(true)}>
            <span className="avatar">M</span><span><strong>Michael</strong><small>Local workspace</small></span><span className="dots">•••</span>
          </button>
        </div>
      </aside>

      {!sidebar && <button className="rail-toggle" onClick={() => setSidebar(true)} aria-label="Open sidebar">AX</button>}

      <section className="main-column">
        <header className="topbar">
          <div className="crumb">
            <span className={`mode-glyph glyph-${mode}`} /><strong>{copy[mode].label}</strong>
            {workspace && <><i>/</i><button onClick={() => setWorkspaceModal(true)}>{workspace.name}</button></>}
          </div>
          <div className="top-actions">
            <span className={`health-dot ${(cloudModes[mode] ? health.claude : health.ollama) ? "online" : "offline"}`} />
            <span className="backend-label">{`${cloudModes[mode] ? "Cloud" : "Local"} · ${modelByMode[mode]}`}</span>
            <button className="icon-button" onClick={() => setRight(!right)} aria-label="Toggle context panel">◫</button>
          </div>
        </header>

        <div className="conversation">
          {!messages.length && !streaming ? (
            <div className="welcome">
              <div className="welcome-orbit"><div className="brand-mark large"><span /></div></div>
              <p className="eyebrow">{copy[mode].kicker}</p><h1>{copy[mode].title}</h1>
              <p>{copy[mode].subtitle}</p>
              <div className="suggestions">
                {suggestions[mode].map((text) => <button key={text} onClick={() => setInput(text)}>{text}<span>↗</span></button>)}
              </div>
            </div>
          ) : (
            <div className="message-list">
              {messages.map((message) => (
                <article key={message.id} className={`message ${message.role}`}>
                  <div className="message-author">
                    {message.role === "assistant" ? <div className="brand-mark mini"><span /></div> : <span className="user-avatar">M</span>}
                    <strong>{message.role === "assistant" ? "AXIO" : "You"}</strong>
                    {message.model && <small>{message.model}</small>}
                  </div>
                  <div className="message-body">{message.content}</div>
                </article>
              ))}
              {streaming && <article className="message assistant streaming">
                <div className="message-author"><div className="brand-mark mini"><span /></div><strong>AXIO</strong><small>working</small></div>
                <div className="message-body">{streaming}<span className="cursor" /></div>
              </article>}
              {busy && !streaming && <div className="thinking"><span /><span /><span /><em>AXIO is working</em></div>}
              <div ref={endRef} />
            </div>
          )}
        </div>

        <div className="composer-wrap">
          {error && <div className="error-banner"><strong>{/connection|unavailable|interrupted/i.test(error) ? "Connection issue" : "Run issue"}</strong><span>{error}</span><button onClick={() => setError("")}>×</button></div>}
          {!!selected.length && <div className="context-chips">
            {selected.map((id) => <button key={id} onClick={() => setSelected((current) => current.filter((value) => value !== id))}>
              {files.find((file) => file.id === id)?.name || id}<span>×</span>
            </button>)}
          </div>}
          <div className="composer">
            <textarea value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={keyDown}
              placeholder={mode === "code" ? "Describe the coding task…" : mode === "cowork" ? "Ask about your workspace…" : "Message AXIO…"}
              rows={1} disabled={busy} aria-label="Message AXIO" />
            <div className="composer-tools"><div>
              <button className="tool-button" onClick={() => { setRight(true); setPanel("context"); }} aria-label="Attach context">＋</button>
              <button className="model-pill"><span className={cloudModes[mode] ? "cloud" : "local"} />
                {modelByMode[mode]}<small>{cloudModes[mode] ? "cloud" : "local"}</small>
              </button>
            </div>
              {busy ? <button className="send stop" onClick={() => runId && request(`/api/runs/${runId}/cancel`, { method: "POST" })} aria-label="Stop run">■</button>
                : <button className="send" onClick={() => void send()} disabled={!input.trim()} aria-label="Send message">↑</button>}
            </div>
          </div>
          <p className="composer-note">AXIO can make mistakes. Review file changes and commands before approving.</p>
        </div>
      </section>

      <aside className="right-panel" aria-label="Context and activity">
        <header><div className="panel-tabs">
          <button className={panel === "context" ? "active" : ""} onClick={() => setPanel("context")}>Context</button>
          <button className={panel === "activity" ? "active" : ""} onClick={() => setPanel("activity")}>Activity{!!activity.length && <span>{activity.length}</span>}</button>
        </div><button className="icon-button" onClick={() => setRight(false)} aria-label="Close panel">×</button></header>
        {panel === "context" ? <div className="panel-content">
          <section className="workspace-card">
            <div className="section-label"><span>Workspace</span><button onClick={() => setWorkspaceModal(true)}>Change</button></div>
            {workspace ? <div className="workspace-value"><span className="folder-icon" /><div><strong>{workspace.name}</strong><small>{workspace.path}</small></div><i>✓</i></div>
              : <button className="empty-workspace" onClick={() => setWorkspaceModal(true)}><span>＋</span><strong>Open a local workspace</strong><small>Required for Cowork and Code</small></button>}
          </section>
          <section className="files-section">
            <div className="section-label"><span>Files</span><small>{selected.length} selected</small></div>
            <div className="file-filter"><span>⌕</span><input placeholder="Filter files" /></div>
            <div className="file-list">
              {!workspace && <p>Choose a workspace to browse local files.</p>}
              {workspace && !files.length && <p>No supported files found.</p>}
              {files.slice(0, 120).map((file) => <label key={file.id} className={selected.includes(file.id) ? "selected" : ""}>
                <input type="checkbox" checked={selected.includes(file.id)} onChange={() => setSelected((current) =>
                  current.includes(file.id) ? current.filter((id) => id !== file.id) : [...current, file.id])} />
                <span className="file-icon">{file.name.split(".").pop()?.slice(0, 2).toUpperCase()}</span>
                <span><strong>{file.name}</strong><small>{file.relative_path} · {fileSize(file.size)}</small></span>
              </label>)}
            </div>
          </section>
          <section className="memory-card"><div className="section-label"><span>IOAF Memory</span><i>Active</i></div>
            <p>AXIO recalls relevant facts and prior work across Chat, Cowork, and Code.</p>
            <div><span>Session</span><span>Semantic</span><span>Facts</span></div>
          </section>
        </div> : <div className="panel-content activity-panel">
          {approvals.map((item) => <section className="approval-card" key={item.approval_id}>
            <p>Approval required</p><h3>{item.action.replace("_", " ")}</h3>
            <pre>{item.detail.command || item.detail.path || item.detail.diff}</pre>
            <div><button onClick={() => void decide(item.approval_id, "deny")}>Deny</button><button className="approve" onClick={() => void decide(item.approval_id, "approve")}>Approve</button></div>
          </section>)}
          {diff && <section className="diff-card"><div className="section-label"><span>Latest diff</span><small>Review</small></div><pre>{diff}</pre></section>}
          {!activity.length && !approvals.length && <div className="empty-activity"><span>◎</span><strong>No activity yet</strong><p>Tool calls, approvals, and verification will appear here.</p></div>}
          <div className="timeline">{activity.slice().reverse().map((item) => <div className="activity-item" key={item.id}>
            <span className={`activity-dot ${item.type}`} /><div><strong>{item.title}</strong>{item.detail && <pre>{item.detail}</pre>}</div>
          </div>)}</div>
        </div>}
      </aside>

      {workspaceModal && <div className="modal-backdrop" onMouseDown={() => setWorkspaceModal(false)}>
        <section className="workspace-modal" onMouseDown={(event) => event.stopPropagation()}>
          <header><div><p>LOCAL WORKSPACES</p><h2>Open a folder in AXIO</h2></div><button onClick={() => setWorkspaceModal(false)}>×</button></header>
          <p>AXIO only reads or changes files inside the workspace you select. Protected actions still require approval.</p>
          <form onSubmit={registerWorkspace}><input autoFocus value={workspacePath} onChange={(event) => setWorkspacePath(event.target.value)} placeholder={"C:\\Users\\AXIO\\Documents\\my-project"} /><button>Open</button></form>
          {!!workspaces.length && <div className="recent-workspaces"><span>Recent</span>{workspaces.map((item) =>
            <button key={item.id} onClick={() => void chooseWorkspace(item)}><span className="folder-icon" /><span><strong>{item.name}</strong><small>{item.path}</small></span><i>→</i></button>)}
          </div>}
        </section>
      </div>}
    </main>
  );
}
