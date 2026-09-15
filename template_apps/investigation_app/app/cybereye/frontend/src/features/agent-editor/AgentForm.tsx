import { useRef } from "react";
import { Code2, FilePlus2, FileText, LockKeyhole, Plus, RotateCcw, Save, Trash2, Upload, Wrench } from "lucide-react";
import type { AgentCatalogue, AgentDefinition, SavedAgent } from "./api";
import { versionLabel } from "./api";

interface Props {
  catalogue: AgentCatalogue;
  draft: AgentDefinition;
  saved: SavedAgent | null;
  dirty: boolean;
  newVersion: boolean;
  editing: boolean;
  busy: boolean;
  saving: boolean;
  error: string;
  notice: string;
  onChange: (draft: AgentDefinition) => void;
  onSave: () => void;
  onCreateVersion: () => void;
  onReset: () => void;
  onVersion: (version: number) => void;
  onUpload: (files: File[]) => void;
  onInspect: (toolId: string) => void;
}

export function AgentForm({ catalogue, draft, saved, dirty, newVersion, editing, busy, saving, error, notice,
  onChange, onSave, onCreateVersion, onReset, onVersion, onUpload, onInspect }: Props) {
  const upload = useRef<HTMLInputElement>(null);
  const patch = (values: Partial<AgentDefinition>) => onChange({ ...draft, ...values });

  return <form className="ae-form" aria-label="Agent configuration" data-drafting={newVersion || !saved} onSubmit={(event) => {
    event.preventDefault();
    onSave();
  }}>
    <div className="ae-toolbar">
      <select className="ae-version-select" aria-label="Agent version"
        value={!saved ? "new" : newVersion ? "draft" : saved.version} disabled={busy || !saved}
        onChange={(event) => { if (event.target.value !== "draft") onVersion(Number(event.target.value)); }}>
        {!saved && <option value="new">New agent</option>}
        {newVersion && saved && <option value="draft">Draft from {versionLabel(saved.version, saved.version_name)}</option>}
        {saved?.versions.map((version) => <option value={version} key={version}>
          {versionLabel(version, saved.version_names?.[version])}
        </option>)}
      </select>
      <button type="button" disabled={busy || !saved || newVersion} onClick={onCreateVersion}>
        <FilePlus2 size={16} aria-hidden="true" />Create New Version
      </button>
      <button type="submit" className="ae-save" disabled={busy || !editing || !dirty || (Boolean(saved) && !newVersion)}>
        <Save size={16} aria-hidden="true" />{saving ? "Saving..." : saved ? "Save New Version" : "Save Agent"}
      </button>
      <button type="button" className="ae-reset" disabled={busy || (!dirty && !newVersion)} onClick={onReset}>
        <RotateCcw size={16} aria-hidden="true" />Reset
      </button>
    </div>
    {error && <div className="ae-error" role="alert">{error}</div>}
    {notice && <div className="ae-notice" role="status">{notice}</div>}
    <fieldset disabled={busy} className="ae-fields">
      <label htmlFor="ae-version-name">Version name
        <input id="ae-version-name" value={draft.version_name} maxLength={80} readOnly={!editing}
          placeholder={editing ? "e.g. Focused triage" : undefined} autoComplete="off"
          onChange={(event) => patch({ version_name: event.target.value })} />
      </label>
      <div className="ae-name-model">
        <label htmlFor="ae-name">Name
          <input id="ae-name" value={draft.name} maxLength={80} required autoComplete="off" readOnly={!editing}
            onChange={(event) => patch({ name: event.target.value })} />
        </label>
        <label htmlFor="ae-model">LLM
          <select id="ae-model" value={draft.model} required disabled={!editing} onChange={(event) => patch({ model: event.target.value })}>
            {catalogue.models.map((model) => <option key={model.id} value={model.id}>{model.name}</option>)}
          </select>
        </label>
      </div>
      <label htmlFor="ae-system-prompt">Prompt / system instruction
        <textarea id="ae-system-prompt" value={draft.system_prompt} rows={7} maxLength={65_536}
          spellCheck={false} readOnly={!editing} onChange={(event) => patch({ system_prompt: event.target.value })} />
      </label>
      <section className="ae-section" aria-labelledby="ae-instructions-heading">
        <div className="ae-section-heading">
          <h3 id="ae-instructions-heading"><FileText size={15} />Instruction files <span>{draft.instruction_files.length}</span></h3>
          <button type="button" onClick={() => upload.current?.click()} disabled={!editing || draft.instruction_files.length >= 12}>
            <Upload size={15} aria-hidden="true" />Upload .md
          </button>
          <input ref={upload} type="file" accept=".md,text/markdown" multiple hidden disabled={!editing}
            aria-label="Upload Markdown instructions" onChange={(event) => {
              onUpload(Array.from(event.target.files ?? []));
              event.target.value = "";
            }} />
        </div>
        {draft.instruction_files.length === 0 && <p className="ae-empty">No instruction files</p>}
        {draft.instruction_files.map((file, index) => <div key={file.name} className="ae-file">
          <details open={index === 0}>
            <summary><FileText size={14} /><span>{file.name}</span></summary>
            <textarea aria-label={`${file.name} instructions`} value={file.content} rows={6} spellCheck={false}
              maxLength={65_536} readOnly={!editing} onChange={(event) => patch({ instruction_files: draft.instruction_files.map(
                (item, position) => position === index ? { ...item, content: event.target.value } : item) })} />
          </details>
          <button type="button" className="ae-icon" aria-label={`Remove ${file.name}`} title={`Remove ${file.name}`}
            disabled={!editing}
            onClick={() => patch({ instruction_files: draft.instruction_files.filter((_, position) => position !== index) })}>
            <Trash2 size={15} />
          </button>
        </div>)}
      </section>
      <section className="ae-section" aria-labelledby="ae-tools-heading">
        <div className="ae-section-heading">
          <h3 id="ae-tools-heading"><Wrench size={15} />Tools <span>{draft.tool_ids.filter(Boolean).length}</span></h3>
        </div>
        <ol className="ae-tool-rows">
          {draft.tool_ids.map((toolId, index) => <li key={index}>
            <span className="ae-row-number" aria-hidden="true">{index + 1}</span>
            <select aria-label={`Tool ${index + 1}`} value={toolId} required disabled={!editing}
              onChange={(event) => patch({ tool_ids: draft.tool_ids.map(
                (item, position) => position === index ? event.target.value : item) })}>
              <option value="">Select tool</option>
              {catalogue.tools.map((tool) => <option key={tool.id} value={tool.id}
                disabled={tool.id !== toolId && draft.tool_ids.includes(tool.id)}>{tool.name}</option>)}
            </select>
            <button type="button" className="ae-icon" aria-label={`Inspect tool ${index + 1}`} title="Inspect tool"
              disabled={!toolId} onClick={() => onInspect(toolId)}><Code2 size={15} /></button>
            <button type="button" className="ae-icon" aria-label={`Remove tool ${index + 1}`} title="Remove tool"
              disabled={!editing}
              onClick={() => patch({ tool_ids: draft.tool_ids.filter((_, position) => position !== index) })}>
              <Trash2 size={15} />
            </button>
          </li>)}
          <li className="ae-add-tool">
            <button type="button" aria-label="Add tool"
              title={!editing ? "Unlock editing to change tools" : draft.tool_ids.length >= catalogue.tools.length
                ? "All available tools are assigned" : "Add tool"}
              disabled={!editing || draft.tool_ids.length >= catalogue.tools.length}
              onClick={() => patch({ tool_ids: [...draft.tool_ids, ""] })}><Plus size={17} /><span>Add tool</span></button>
          </li>
        </ol>
      </section>
      <details className="ae-policies">
        <summary><LockKeyhole size={14} />Required policies</summary>
        {catalogue.foundation_files.map((file) => <div key={file.name}>
          <h4>{file.name}</h4><pre>{file.content}</pre>
        </div>)}
      </details>
    </fieldset>
  </form>;
}