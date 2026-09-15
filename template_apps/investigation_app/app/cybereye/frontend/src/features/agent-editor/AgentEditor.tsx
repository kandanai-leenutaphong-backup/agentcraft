import { useEffect, useRef, useState } from "react";
import { ArrowLeft, Bot, Check, LockKeyhole, LockKeyholeOpen, Pencil, Plus, RefreshCw } from "lucide-react";
import { AgentToolDetail, ExplorerLayout } from "@components/resource_explorer/frontend";
import { AgentForm } from "./AgentForm";
import { agentEditorApi, definitionOf, versionLabel } from "./api";
import type { AgentCatalogue, AgentDefinition, SavedAgent } from "./api";
import "./editor.css";

interface Props {
  active: boolean;
  onAssigned: (agent: SavedAgent) => void;
}

export function AgentEditor({ active, onAssigned }: Props) {
  const [catalogue, setCatalogue] = useState<AgentCatalogue | null>(null);
  const [catalogueError, setCatalogueError] = useState("");
  const [loading, setLoading] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [saved, setSaved] = useState<SavedAgent | null>(null);
  const [draft, setDraft] = useState<AgentDefinition | null>(null);
  const [baseline, setBaseline] = useState("");
  const [newVersion, setNewVersion] = useState(false);
  const [editing, setEditing] = useState(false);
  const [viewer, setViewer] = useState<"agent" | "tool">("agent");
  const [inspected, setInspected] = useState("");
  const [opening, setOpening] = useState(false);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [roleAgent, setRoleAgent] = useState("");
  const [roleVersion, setRoleVersion] = useState(1);
  const [assigning, setAssigning] = useState(false);
  const [roleError, setRoleError] = useState("");
  const [roleNotice, setRoleNotice] = useState("");
  const loadRequest = useRef<AbortController | null>(null);
  const viewerRef = useRef<HTMLElement>(null);
  const dirty = draft !== null && JSON.stringify(draft) !== baseline;
  const busy = opening || saving || uploading;

  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    setLoading(true);
    setCatalogueError("");
    agentEditorApi.catalogue(controller.signal).then((value) => {
      if (controller.signal.aborted) return;
      setCatalogue(value);
      setRoleAgent(value.investigator.agent_id);
      setRoleVersion(value.investigator.version);
    }).catch((failure: Error) => {
      if (!controller.signal.aborted) setCatalogueError(failure.message);
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [active, refresh]);

  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  useEffect(() => () => loadRequest.current?.abort(), []);

  function show(kind: "agent" | "tool") {
    setViewer(kind);
    if (window.matchMedia("(max-width: 700px)").matches) {
      requestAnimationFrame(() => viewerRef.current?.scrollIntoView({ block: "start" }));
    }
  }

  function applySaved(value: SavedAgent) {
    const definition = definitionOf(value);
    setSaved(value);
    setDraft(definition);
    setBaseline(JSON.stringify(definition));
    setNewVersion(false);
    setEditing(false);
    requestAnimationFrame(() => viewerRef.current?.querySelector(".ae-pane")?.scrollTo({ top: 0 }));
  }

  function mayDiscard() {
    return !dirty || window.confirm("Discard unsaved agent changes?");
  }

  async function openAgent(id: string, version?: number, reload = false) {
    if (busy) return;
    if (saved?.agent_id === id && !version && !reload) { show("agent"); return; }
    if (!mayDiscard()) return;
    loadRequest.current?.abort();
    const controller = new AbortController();
    loadRequest.current = controller;
    setOpening(true);
    setError("");
    setNotice("");
    show("agent");
    try {
      const value = await agentEditorApi.version(id, version, controller.signal);
      if (!controller.signal.aborted) applySaved(value);
    } catch (failure) {
      if (!controller.signal.aborted) setError((failure as Error).message);
    } finally {
      if (!controller.signal.aborted) setOpening(false);
    }
  }

  function createAgent() {
    if (!catalogue || busy || !mayDiscard()) return;
    loadRequest.current?.abort();
    const definition: AgentDefinition = { name: "", model: catalogue.models[0]?.id ?? "",
      version_name: "", system_prompt: "", instruction_files: [], tool_ids: [] };
    setSaved(null);
    setDraft(definition);
    setBaseline(JSON.stringify(definition));
    setNewVersion(false);
    setEditing(true);
    setError("");
    setNotice("");
    setInspected("");
    show("agent");
    requestAnimationFrame(() => document.getElementById("ae-name")?.focus());
  }

  function createVersion() {
    if (!saved || busy || newVersion) return;
    setNewVersion(true);
    setEditing(true);
    setError("");
    setNotice("");
    show("agent");
    requestAnimationFrame(() => {
      const input = document.getElementById("ae-version-name") as HTMLInputElement | null;
      input?.focus();
      input?.select();
    });
  }

  function toggleEditing() {
    if (!draft || busy) return;
    if (!editing && saved && !newVersion) { createVersion(); return; }
    setEditing((value) => !value);
  }

  function resetDraft() {
    if (!draft || busy) return;
    if (saved) applySaved(saved);
    else {
      setDraft(JSON.parse(baseline) as AgentDefinition);
      setEditing(true);
    }
    setError("");
    setNotice("");
  }

  async function saveAgent() {
    if (!draft || busy || !editing || !dirty || (saved && !newVersion)) return;
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const result = await agentEditorApi.save(draft, saved);
      const confirmed = await agentEditorApi.version(result.agent_id, result.version);
      applySaved(confirmed);
      setNotice(saved ? "New version saved." : "Agent saved.");
      setRefresh((value) => value + 1);
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function uploadFiles(files: File[]) {
    if (!draft || busy || !editing || !files.length) return;
    setError("");
    setNotice("");
    setUploading(true);
    try {
      if (draft.instruction_files.length + files.length > 12) throw new Error("At most 12 instruction files are allowed.");
      const names = new Set(draft.instruction_files.map((file) => file.name.toLowerCase()));
      for (const file of files) {
        if (!file.name.toLowerCase().endsWith(".md")) throw new Error("Instruction uploads must be .md files.");
        if (file.size > 65_536) throw new Error(`${file.name} exceeds the 64 KiB file limit.`);
        if (names.has(file.name.toLowerCase())) throw new Error(`An instruction file named ${file.name} already exists.`);
        names.add(file.name.toLowerCase());
      }
      const instruction_files = await Promise.all(files.map(async (file) => {
        const content = new TextDecoder("utf-8", { fatal: true }).decode(await file.arrayBuffer());
        if (!content.trim() || content.includes("\0")) throw new Error(`${file.name} must contain Markdown text.`);
        return { name: file.name, content };
      }));
      setDraft((current) => current && { ...current, instruction_files: [...current.instruction_files, ...instruction_files] });
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setUploading(false);
    }
  }

  async function assignRole() {
    if (!catalogue || assigning) return;
    setAssigning(true);
    setRoleError("");
    setRoleNotice("");
    try {
      const result = await agentEditorApi.assign(roleAgent, roleVersion, catalogue.investigator.revision);
      const confirmed = await agentEditorApi.catalogue();
      if (confirmed.investigator.agent_id !== result.agent_id || confirmed.investigator.version !== result.version) {
        throw new Error("The Investigator assignment changed during verification. Reload the library.");
      }
      const agent = await agentEditorApi.version(result.agent_id, result.version);
      setCatalogue(confirmed);
      setRoleAgent(result.agent_id);
      setRoleVersion(result.version);
      setRoleNotice(`${agent.name} / ${versionLabel(agent.version, agent.version_name)}`);
      onAssigned(agent);
    } catch (failure) {
      setRoleError((failure as Error).message);
    } finally {
      setAssigning(false);
    }
  }

  const tool = catalogue?.tools.find((entry) => entry.id === inspected);
  const roleChoice = catalogue?.agents.find((entry) => entry.id === roleAgent);
  const roleChanged = roleAgent !== catalogue?.investigator.agent_id || roleVersion !== catalogue?.investigator.version;

  return <ExplorerLayout viewerRef={viewerRef}
      testId="agent-editor" heading={<>
        <Pencil size={15} aria-hidden="true" />
        <span className="ae-configuration-name">{viewer === "tool" ? "Tool"
          : draft?.name || (draft ? "New agent" : "Agent configuration")}</span>
        {viewer === "agent" && draft && <button type="button" className="ae-edit-lock"
          aria-label={editing ? "Lock editing" : "Unlock editing"} data-locked={!editing}
          title={editing ? "Lock editing" : saved && !newVersion ? "Unlock editing (new version draft)" : "Unlock editing"}
          disabled={busy} onClick={toggleEditing}>
          {editing ? <LockKeyholeOpen size={17} aria-hidden="true" /> : <LockKeyhole size={17} aria-hidden="true" />}
        </button>}
      </>}
      agents={<>
        <header className="rex-header">
          <h2><Bot size={15} />Agents</h2>
          <div className="rex-controls">
            <span role="status">{loading ? "Loading..." : `${catalogue?.agents.length ?? 0} agents`}</span>
            <button type="button" title="Refresh agent library" aria-label="Refresh agent library"
              disabled={loading || busy || assigning} onClick={() => setRefresh((value) => value + 1)}><RefreshCw size={15} /></button>
            <button type="button" title="Create agent" aria-label="Create agent" disabled={!catalogue || busy}
              onClick={createAgent}><Plus size={17} /></button>
          </div>
        </header>
        {catalogueError && <div className="ae-error" role="alert">{catalogueError}</div>}
        <div className="ae-agent-list">
          {draft && !saved && <button type="button" aria-label="Continue new agent"
            aria-pressed={viewer === "agent"} onClick={() => show("agent")}>
            <Pencil size={15} /><span>{draft.name || "New agent"}<small>Unsaved</small></span>
          </button>}
          {catalogue?.agents.map((entry) => <button key={entry.id} type="button" aria-label={`Edit ${entry.name}`}
            disabled={busy} aria-pressed={saved?.agent_id === entry.id}
            onClick={() => void openAgent(entry.id)}>
            <Bot size={15} /><span>{entry.name}<small>{versionLabel(entry.latest_version, entry.version_names?.[entry.latest_version])} / {entry.tool_ids.length} tools</small></span>
            {catalogue.investigator.agent_id === entry.id && <Check size={14} aria-label="Assigned Investigator" />}
          </button>)}
        </div>
        {catalogue && <form className="ae-roles" aria-label="Role assignment" onSubmit={(event) => {
          event.preventDefault(); void assignRole();
        }}>
          <h3>Role assignment</h3>
          <label htmlFor="ae-investigator">Investigator
            <select id="ae-investigator" aria-label="Investigator agent" value={roleAgent} disabled={assigning || busy || loading}
              onChange={(event) => {
                setRoleAgent(event.target.value);
                setRoleVersion(catalogue.agents.find((entry) => entry.id === event.target.value)?.latest_version ?? 1);
                setRoleError(""); setRoleNotice("");
              }}>
              {catalogue.agents.map((entry) => <option key={entry.id} value={entry.id}>{entry.name}</option>)}
            </select>
          </label>
          <label htmlFor="ae-role-version">Version
            <select id="ae-role-version" aria-label="Investigator version" value={roleVersion} disabled={assigning || busy || loading}
              onChange={(event) => { setRoleVersion(Number(event.target.value)); setRoleError(""); setRoleNotice(""); }}>
              {roleChoice?.versions.map((version) => <option key={version} value={version}>
                {versionLabel(version, roleChoice.version_names?.[version])}
              </option>)}
            </select>
          </label>
          <button type="submit" disabled={assigning || busy || loading || !roleChanged}>
            <Check size={15} />{assigning ? "Assigning..." : "Assign Investigator"}
          </button>
          <p className="ae-assignment" data-testid="investigator-assignment">{catalogue.assigned_agent.name} / {versionLabel(catalogue.investigator.version, catalogue.assigned_agent.version_name)}</p>
          {roleError && <div className="ae-error" role="alert">{roleError}</div>}
          {roleNotice && <div className="ae-notice" role="status">Assigned: {roleNotice}</div>}
        </form>}
      </>}>
      <div className="rex-pane ae-pane" hidden={viewer !== "agent"}>
        {opening && <p className="ae-empty" role="status">Loading configuration...</p>}
        {draft && catalogue ? <AgentForm catalogue={catalogue} draft={draft} saved={saved}
          dirty={dirty} newVersion={newVersion} editing={editing} busy={busy} saving={saving} error={error} notice={notice}
          onChange={(value) => { if (editing && !busy) { setDraft(value); setNotice(""); } }} onSave={() => void saveAgent()}
          onCreateVersion={createVersion} onReset={resetDraft}
          onVersion={(version) => { if (saved) void openAgent(saved.agent_id, version, true); }}
          onUpload={(files) => void uploadFiles(files)} onInspect={(id) => { setInspected(id); show("tool"); }} />
          : !opening && <div className="ae-empty">{error || "No agent selected"}</div>}
      </div>
      <div className="rex-pane" hidden={viewer !== "tool"}>
        <div className="ae-tool-toolbar"><button type="button" onClick={() => show("agent")}>
          <ArrowLeft size={15} />Agent configuration
        </button></div>
        {tool && draft && <div className="agent-detail"><AgentToolDetail tool={tool} agent={draft} /></div>}
      </div>
    </ExplorerLayout>;
}