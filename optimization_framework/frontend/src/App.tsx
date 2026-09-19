import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { Activity, ArrowDownToLine, ArrowLeft, ArrowRight, Check, ChevronRight, CircleAlert, Clock3, FileCode2, FileText, FlaskConical, GitBranch, LayoutList, LoaderCircle, MessageSquare, Play, RefreshCw, RotateCcw, Square, X } from 'lucide-react';
import { api, type Candidate, type Disposition, type Run, type Task } from './api';

type View = 'comparison' | 'timeline' | 'evidence' | 'report';
const views = [
  { id: 'comparison', name: 'Comparison', icon: LayoutList },
  { id: 'timeline', name: 'Run timeline', icon: Activity },
  { id: 'evidence', name: 'Candidate evidence', icon: FileCode2 },
  { id: 'report', name: 'Experiment report', icon: FileText },
] as const;
const readable = (value: string) => value.replaceAll('_', ' ').replaceAll('-', ' ');
const measured = (value: number | null, unit = '') => value === null ? 'Not captured' : `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}${unit}`;
const date = (value: string) => Number.isNaN(Date.parse(value)) ? value : new Date(value).toLocaleString();
const knownGood = (candidate: Candidate) => candidate.status === 'passed' && candidate.checks.length > 0 && candidate.checks.every(check => check.status === 'passed');

function Badge({ value }: { value: string }) {
  return <span className={`badge ${value === 'passed' || value === 'completed' || value === 'improved' ? 'good' : value === 'failed' || value === 'regressed' ? 'bad' : ''}`}>{readable(value)}</span>;
}

function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return <section className="empty"><FileText size={28} aria-hidden="true" /><h2>{title}</h2>{children && <p>{children}</p>}</section>;
}

export function App() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [taskId, setTaskId] = useState('');
  const [runs, setRuns] = useState<Run[]>([]);
  const [runId, setRunId] = useState(() => new URLSearchParams(location.search).get('run') ?? '');
  const [detail, setDetail] = useState<Run | null>(null);
  const [view, setView] = useState<View>('comparison');
  const [candidateId, setCandidateId] = useState('');
  const [loading, setLoading] = useState(true);
  const [connectionError, setConnectionError] = useState('');
  const [actionError, setActionError] = useState('');
  const [notice, setNotice] = useState('');
  const [pending, setPending] = useState('');
  const [refresh, setRefresh] = useState(0);
  const [syncedAt, setSyncedAt] = useState('');
  const [restoreTarget, setRestoreTarget] = useState<Candidate | null>(null);
  const [restoreConfirmed, setRestoreConfirmed] = useState(false);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const busy = useRef(false);
  const revision = useRef(0);
  const requestKeys = useRef(new Map<string, string>());
  const run = detail?.id === runId ? detail : runs.find(item => item.id === runId) ?? null;
  const candidate = run?.candidates.find(item => item.id === candidateId)
    ?? run?.candidates.find(item => item.id === run.selected_candidate_id)
    ?? run?.candidates[0];
  const selectedTask = tasks.find(task => task.id === taskId);

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    let disposed = false;
    async function poll() {
      const currentRevision = revision.current;
      try {
        const [nextTasks, nextRuns, nextDetail] = await Promise.all([
          api.tasks(controller.signal), api.runs(controller.signal),
          runId ? api.run(runId, controller.signal) : Promise.resolve(null),
        ]);
        if (disposed || currentRevision !== revision.current || busy.current) return;
        setTasks(nextTasks);
        setTaskId(previous => nextTasks.some(task => task.id === previous) ? previous : nextTasks[0]?.id ?? '');
        setRuns(nextRuns);
        setDetail(nextDetail);
        setConnectionError('');
        setSyncedAt(new Date().toISOString());
        setLoading(false);
      } catch (error) {
        if (!disposed && currentRevision === revision.current) {
          setConnectionError(error instanceof Error ? error.message : 'Unable to read runs.');
          setLoading(false);
        }
      } finally {
        if (!disposed) timer = setTimeout(poll, 1800);
      }
    }
    void poll();
    return () => { disposed = true; controller.abort(); clearTimeout(timer); };
  }, [runId, refresh]);

  useEffect(() => {
    if (restoreTarget) dialogRef.current?.showModal();
    else dialogRef.current?.close();
  }, [restoreTarget]);

  function chooseRun(id: string) {
    setRunId(id);
    setCandidateId('');
    setActionError('');
    setNotice('');
    const url = new URL(location.href);
    url.searchParams.set('run', id);
    history.replaceState(null, '', url);
  }

  function showCandidate(id: string) {
    setCandidateId(id);
    setView('evidence');
  }

  async function mutate(label: string, signature: string, action: (key: string) => Promise<Run>): Promise<boolean> {
    if (busy.current) return false;
    busy.current = true;
    revision.current += 1;
    setPending(label);
    setActionError('');
    setNotice('');
    const key = requestKeys.current.get(signature) ?? crypto.randomUUID();
    requestKeys.current.set(signature, key);
    try {
      const updated = await action(key);
      setRuns(previous => [updated, ...previous.filter(item => item.id !== updated.id)]);
      setDetail(updated);
      chooseRun(updated.id);
      setNotice(`${label}: recorded.`);
      requestKeys.current.delete(signature);
      return true;
    } catch (error) {
      setActionError(error instanceof Error ? error.message : `${label} failed.`);
      return false;
    } finally {
      revision.current += 1;
      busy.current = false;
      setPending('');
      setRefresh(previous => previous + 1);
    }
  }

  async function startRun(event: FormEvent) {
    event.preventDefault();
    if (!taskId) return;
    await mutate('Start run', `start:${taskId}`, key => api.start(taskId, key));
  }

  async function restore() {
    if (!run || !restoreTarget || !restoreConfirmed || !knownGood(restoreTarget)) return;
    const target = restoreTarget;
    const success = await mutate('Restore candidate', `restore:${run.id}:${target.id}`, async key => {
      const updated = await api.restore(run.id, target.id, key);
      if (updated.selected_candidate_id !== target.id || !updated.restorations.some(receipt => receipt.candidate_id === target.id && receipt.verified)) {
        throw new Error('Restore response lacks matching selected candidate and verified receipt. Outcome is not confirmed.');
      }
      return updated;
    });
    if (success) { setCandidateId(target.id); setRestoreTarget(null); }
  }

  async function download(format: 'json' | 'csv' | 'html') {
    if (!run || busy.current) return;
    busy.current = true;
    setPending(`Download ${format.toUpperCase()}`);
    setActionError('');
    try {
      const response = await fetch(api.reportUrl(run.id, format), { credentials: 'same-origin', cache: 'no-store' });
      if (!response.ok) throw new Error(`Report download refused (HTTP ${response.status}): ${(await response.text()).slice(0, 500)}`);
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `optimization-${run.id.replace(/[^a-zA-Z0-9_-]/g, '_')}.${format}`;
      anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setNotice(`${format.toUpperCase()} report downloaded.`);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'Download failed.');
    } finally { busy.current = false; setPending(''); }
  }

  return <div className="workspace">
    <a className="skip-link" href="#main">Skip to workspace</a>
    <aside className="sidebar" aria-label="Workspace navigation">
      <div className="brand"><GitBranch size={24} aria-hidden="true" /><div>Optimization<span>Experiment workspace</span></div></div>
      <nav aria-label="Views">{views.map(({ id, name, icon: Icon }) => <button key={id} className={`nav-item ${view === id ? 'active' : ''}`} aria-current={view === id ? 'page' : undefined} onClick={() => setView(id)}><Icon size={18} aria-hidden="true" />{name}</button>)}</nav>
      <div className="sidebar-heading"><h2>Runs</h2><span>{runs.length}</span></div>
      <div className="run-list">{runs.map(item => <button key={item.id} disabled={!!pending} className={`run-item ${runId === item.id ? 'selected' : ''}`} onClick={() => chooseRun(item.id)} aria-pressed={runId === item.id}><span>{item.task_name}</span><small className="mono">{item.id}</small><span className="run-state">{readable(item.status)}<ChevronRight size={14} aria-hidden="true" /></span></button>)}{!loading && !runs.length && <p className="sidebar-empty">No recorded runs</p>}</div>
      <div className="host-state"><span className={`signal ${connectionError ? 'offline' : ''}`} /><span>{connectionError ? 'Connection interrupted' : loading ? 'Connecting' : 'Local operator host'}<small>{syncedAt ? `Read ${new Date(syncedAt).toLocaleTimeString()}` : 'Awaiting API'}</small></span><button className="icon-button" aria-label="Refresh runs" title="Refresh runs" onClick={() => setRefresh(previous => previous + 1)}><RefreshCw size={16} /></button></div>
    </aside>
    <main id="main" tabIndex={-1}>
      <header className="page-header"><div><div className="eyebrow">Optimization / {run?.domain ?? 'Workspace'}</div><h1>{views.find(item => item.id === view)?.name}</h1></div><div className="header-mark"><FlaskConical size={18} aria-hidden="true" />Local experiments</div></header>
      <form className="launch-bar" onSubmit={startRun} aria-label="Start experiment">
        <label>Task<select value={taskId} onChange={event => setTaskId(event.target.value)} disabled={!!pending || !tasks.length} required><option value="" disabled>{loading ? 'Loading tasks...' : 'Select task'}</option>{tasks.map(task => <option key={task.id} value={task.id}>{task.name}</option>)}</select></label>
        <label>Executor<select value="deterministic" aria-label="Executor" disabled={!!pending} onChange={() => undefined}><option value="deterministic">Deterministic</option></select></label>
        <button className="primary" disabled={!taskId || !!pending || !!connectionError} type="submit">{pending === 'Start run' ? <LoaderCircle className="spin" size={16} /> : <Play size={16} />}Start run</button>
        {run?.status === 'running' && <button type="button" className="danger" disabled={!!pending} onClick={() => void mutate('Cancel run', `cancel:${run.id}`, () => api.cancel(run.id))}><Square size={15} />Cancel run</button>}
      </form>
      {selectedTask && <p className="task-context"><span>{selectedTask.domain}</span>{selectedTask.description}</p>}
      <div className="live-status" role="status" aria-live="polite">{pending && <LoaderCircle size={14} className="spin" />}{pending || notice}</div>
      {connectionError && <div className="alert" role="alert"><CircleAlert size={18} /><div><strong>API unavailable or incompatible</strong><p>{connectionError}</p>{syncedAt && <p>Last read retained. Current server state is unknown.</p>}</div><button className="icon-button" aria-label="Retry connection" title="Retry connection" onClick={() => setRefresh(previous => previous + 1)}><RefreshCw size={18} /></button></div>}
      {actionError && !restoreTarget && <div className="alert" role="alert"><CircleAlert size={18} /><div><strong>Operation not confirmed</strong><p>{actionError}</p></div><button className="icon-button" aria-label="Dismiss operation error" title="Dismiss operation error" onClick={() => setActionError('')}><X size={18} /></button></div>}
      {run && <section className="run-heading" aria-label="Selected run"><div><h2>{run.task_name}</h2><div className="run-meta"><code>{run.id}</code><span>{run.executor}</span><span>{date(run.created_at)}</span></div></div><div className="badges"><Badge value={run.status} /><Badge value={run.evidence_class} /></div></section>}
      {run?.evidence_class === 'synthetic-integration' && <div className="evidence-notice"><FlaskConical size={17} aria-hidden="true" /><span><strong>Synthetic evidence.</strong> Deterministic integration; not live model, deployment, or optimization proof.</span></div>}
      {loading ? <Empty title="Loading workspace">Reading tasks and recorded runs.</Empty> : view === 'comparison' ? <Comparison runs={runs} selectedId={runId} disabled={!!pending} select={chooseRun} /> : !run ? <Empty title="No run selected">{runs.length ? 'Select a recorded run.' : 'No experiment evidence has been recorded.'}</Empty> : view === 'timeline' ? <Timeline run={run} showCandidate={showCandidate} /> : view === 'evidence' ? <Evidence key={run.id} run={run} candidate={candidate} pending={!!pending} showCandidate={showCandidate} restore={target => { setRestoreTarget(target); setRestoreConfirmed(false); setActionError(''); }} mutate={mutate} /> : <Report run={run} pending={!!pending} download={download} showCandidate={showCandidate} />}
      {run && <section className="limitations"><h2><CircleAlert size={16} aria-hidden="true" />Limitations</h2>{run.limitations.length ? <ul>{run.limitations.map((limitation, index) => <li key={index}>{limitation}</li>)}</ul> : <p>No limitations supplied by service. This is not a completeness guarantee.</p>}</section>}
      <footer>Optimization framework <span>Evidence from recorded API results</span></footer>
    </main>
    <dialog ref={dialogRef} aria-labelledby="restore-title" onCancel={event => { if (pending) event.preventDefault(); else setRestoreTarget(null); }}>
      <div className="dialog-heading"><h2 id="restore-title">Restore known-good candidate?</h2><button className="icon-button" disabled={!!pending} aria-label="Close restore confirmation" title="Close restore confirmation" onClick={() => setRestoreTarget(null)}><X size={18} /></button></div>
      {restoreTarget && <><p>Restore <strong>{restoreTarget.name}</strong>. Current selection may be replaced. Service authorization and verification are required.</p><code className="digest">{restoreTarget.digest}</code><label className="confirmation"><input type="checkbox" checked={restoreConfirmed} onChange={event => setRestoreConfirmed(event.target.checked)} disabled={!!pending} />I confirm restoration to this candidate.</label>{actionError && <p className="dialog-error" role="alert">{actionError}</p>}<div className="dialog-actions"><button disabled={!!pending} onClick={() => setRestoreTarget(null)}>Keep current</button><button className="primary" disabled={!restoreConfirmed || !!pending} onClick={() => void restore()}><RotateCcw size={16} />{pending ? 'Restoring...' : 'Confirm restore'}</button></div></>}
    </dialog>
  </div>;
}

function Comparison({ runs, selectedId, disabled, select }: { runs: Run[]; selectedId: string; disabled: boolean; select: (id: string) => void }) {
  if (!runs.length) return <Empty title="No experiments yet">{ 'Available tasks are loaded from the local service.' }</Empty>;
  return <section aria-labelledby="comparison-title">
    <div className="section-heading"><h2 id="comparison-title">Recorded runs <span className="count">{runs.length}</span></h2><span className="muted">Per-run observations; no cohort aggregate supplied</span></div>
    <div className="table-scroll" role="region" aria-label="Run comparison table" tabIndex={0}><table><thead><tr><th scope="col">Task / run</th><th scope="col">Outcome</th><th scope="col">Time</th><th scope="col">Repairs</th><th scope="col">Actions / calls</th><th scope="col">Footprint</th><th scope="col">Coverage</th></tr></thead><tbody>{runs.map(run => <tr key={run.id} className={selectedId === run.id ? 'selected-row' : ''}><th scope="row"><button className="text-button" disabled={disabled} onClick={() => select(run.id)} aria-label={`Select run ${run.id}`}>{run.task_name}<ArrowRight size={15} /></button><small className="mono">{run.id}</small><small>{run.domain} / {run.executor}</small><Badge value={run.evidence_class} /></th><td><Badge value={run.status} /><small>Acceptance: {readable(run.acceptance)}</small><small>{readable(run.decision)}</small><small>First pass: {run.metrics.first_pass_success === null ? 'Not captured' : run.metrics.first_pass_success ? 'yes' : 'no'}</small></td><td className="numeric">{measured(run.metrics.elapsed_seconds, ' s')}</td><td className="numeric">{measured(run.metrics.repair_cycles)}</td><td className="numeric">{measured(run.metrics.actions)} / {measured(run.metrics.calls)}</td><td><span>{measured(run.metrics.files_changed)} files</span><small className="mono">+{measured(run.metrics.lines_added)} / -{measured(run.metrics.lines_deleted)}</small></td><td><span>{run.metrics.telemetry_coverage}</span><small>Model requests: {measured(run.metrics.model_requests)}</small></td></tr>)}</tbody></table></div>
    <dl className="availability"><div><dt>Cohort size / success rate</dt><dd>Not supplied</dd></div><div><dt>Failed trial count</dt><dd>Not supplied</dd></div><div><dt>Cost / architecture pins</dt><dd>Not captured</dd></div></dl>
  </section>;
}

function Timeline({ run, showCandidate }: { run: Run; showCandidate: (id: string) => void }) {
  const [filter, setFilter] = useState('all');
  const kinds = [...new Set(run.events.map(event => event.kind))];
  const events = run.events.filter(event => filter === 'all' || event.kind === filter);
  return <section aria-labelledby="timeline-title"><div className="section-heading"><h2 id="timeline-title">Recorded timeline <span className="count">{run.events.length}</span></h2><label className="inline-label">Event kind<select value={filter} onChange={event => setFilter(event.target.value)}><option value="all">All events</option>{kinds.map(kind => <option key={kind} value={kind}>{readable(kind)}</option>)}</select></label></div><p className="muted">Event timestamps retained in service order. Phase intervals are not supplied.</p>{!events.length ? <Empty title="No matching events" /> : <ol className="timeline">{events.map(event => <li key={event.id}><span className="timeline-point"><Clock3 size={14} aria-hidden="true" /></span><div><div className="event-header"><strong>{readable(event.kind)}</strong><time dateTime={event.at}>{date(event.at)}</time></div><p>{event.detail}</p><div className="event-footer"><code>{event.id}</code>{event.candidate_id && (run.candidates.some(candidate => candidate.id === event.candidate_id) ? <button className="text-button" onClick={() => showCandidate(event.candidate_id!)}>Candidate {event.candidate_id}<ArrowRight size={14} /></button> : <span>Candidate {event.candidate_id}: unavailable</span>)}</div></div></li>)}</ol>}</section>;
}

type Mutate = (label: string, signature: string, action: (key: string) => Promise<Run>) => Promise<boolean>;
function Evidence({ run, candidate, pending, showCandidate, restore, mutate }: { run: Run; candidate?: Candidate; pending: boolean; showCandidate: (id: string) => void; restore: (candidate: Candidate) => void; mutate: Mutate }) {
  const [text, setText] = useState('');
  const [feedbackCandidate, setFeedbackCandidate] = useState('');
  const ancestors: Candidate[] = [];
  const seen = new Set([candidate?.id]);
  let parentId = candidate?.parent_id;
  while (parentId && !seen.has(parentId)) {
    seen.add(parentId);
    const parent = run.candidates.find(item => item.id === parentId);
    if (!parent) break;
    ancestors.push(parent);
    parentId = parent.parent_id;
  }
  const baseline = candidate?.parent_id === null ? candidate : ancestors.find(item => item.parent_id === null);
  const previousGood = ancestors.find(knownGood);
  async function submitFeedback(event: FormEvent) {
    event.preventDefault();
    if (!text.trim()) return;
    const success = await mutate('Submit feedback', JSON.stringify(['feedback', run.id, text.trim(), feedbackCandidate]), key => api.feedback(run.id, text.trim(), feedbackCandidate || null, key));
    if (success) setText('');
  }
  return <>
    <section aria-labelledby="candidate-title"><div className="section-heading"><h2 id="candidate-title">Candidate source & checks</h2><label className="inline-label">Candidate<select aria-label="Candidate" value={candidate?.id ?? ''} disabled={!run.candidates.length || pending} onChange={event => showCandidate(event.target.value)}>{!run.candidates.length && <option value="">None recorded</option>}{run.candidates.map(item => <option key={item.id} value={item.id}>{item.name} ({item.status})</option>)}</select></label></div>
      {!candidate ? <Empty title="No candidates recorded" /> : <><div className="candidate-heading"><div><div className="badges"><h3>{candidate.name}</h3><Badge value={candidate.status} />{candidate.id === run.selected_candidate_id && <span className="badge">selected</span>}</div><p>{candidate.hypothesis}</p><code className="digest">{candidate.digest}</code></div><button disabled={pending || run.status === 'running' || !knownGood(candidate)} title={!knownGood(candidate) ? 'Requires passed candidate and all recorded checks passed' : 'Restore this candidate with confirmation'} onClick={() => restore(candidate)}><RotateCcw size={16} />Restore candidate</button></div>
      <div className="candidate-links">{baseline && baseline.id !== candidate.id && <button className="text-button" onClick={() => showCandidate(baseline.id)}><ArrowLeft size={15} />Baseline</button>}{candidate.parent_id && <button className="text-button" disabled={!run.candidates.some(item => item.id === candidate.parent_id)} onClick={() => showCandidate(candidate.parent_id!)}><GitBranch size={15} />Parent: {candidate.parent_id}</button>}{previousGood && <button className="text-button" onClick={() => showCandidate(previousGood.id)}><Check size={15} />Previous known-good: {previousGood.name}</button>}</div>
      <h3 className="subheading">Recorded diff</h3>{candidate.diff ? <pre className="diff" aria-label="Candidate source diff" tabIndex={0}><code>{candidate.diff.split('\n').map((line, index) => <span key={index} className={line.startsWith('+') && !line.startsWith('+++') ? 'added' : line.startsWith('-') && !line.startsWith('---') ? 'removed' : line.startsWith('@@') ? 'hunk' : ''}>{line || ' '}{'\n'}</span>)}</code></pre> : <p className="muted">No diff recorded for this candidate.</p>}
      <h3 className="subheading" id={`checks-${candidate.id}`}>Acceptance checks</h3><div className="checks">{candidate.checks.length ? candidate.checks.map((check, index) => <div className="check-row" key={index}><Badge value={check.status} /><div><strong>{check.name}</strong><pre>{check.detail}</pre></div></div>) : <p className="muted">No check results recorded. Not verified.</p>}</div></>}
      <p className="contract-gap">Screenshots, deployment identity, persisted-result identity and recorded-case captures: not supplied by this API.</p>
    </section>
    <section className="feedback-section" aria-labelledby="feedback-title"><div className="section-heading"><h2 id="feedback-title"><MessageSquare size={18} aria-hidden="true" />SME feedback <span className="count">{run.feedback.length}</span></h2></div>
      <form className="feedback-form" onSubmit={submitFeedback}><label>Observation<textarea value={text} onChange={event => setText(event.target.value)} required rows={3} disabled={pending} /></label><div className="form-bottom"><label>Linked candidate<select value={feedbackCandidate} onChange={event => setFeedbackCandidate(event.target.value)} disabled={pending}><option value="">Run-level observation</option>{run.candidates.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><button className="primary" disabled={pending || !text.trim()} type="submit"><MessageSquare size={16} />Submit feedback</button></div></form>
      <div className="feedback-list">{run.feedback.length ? run.feedback.map(feedback => <FeedbackEntry key={feedback.id} run={run} feedback={feedback} pending={pending} showCandidate={showCandidate} mutate={mutate} />) : <p className="muted">No SME observations recorded.</p>}</div>
    </section>
  </>;
}

function FeedbackEntry({ run, feedback, pending, showCandidate, mutate }: { run: Run; feedback: Run['feedback'][number]; pending: boolean; showCandidate: (id: string) => void; mutate: Mutate }) {
  const [disposition, setDisposition] = useState<Disposition>('clarify');
  const [reason, setReason] = useState('');
  const [linkedId, setLinkedId] = useState(feedback.candidate_id ?? '');
  const [expanded, setExpanded] = useState(false);
  async function respond(event: FormEvent) {
    event.preventDefault();
    if (!reason.trim()) return;
    const success = await mutate('Record disposition', JSON.stringify(['respond', run.id, feedback.id, disposition, reason.trim(), linkedId]), key => api.respond(run.id, feedback.id, disposition, reason.trim(), linkedId || null, key));
    if (success) { setReason(''); setExpanded(false); }
  }
  const linked = run.candidates.find(item => item.id === feedback.candidate_id);
  return <article className="feedback-entry"><div className="feedback-meta"><strong>{feedback.author}</strong><time dateTime={feedback.at}>{date(feedback.at)}</time><Badge value={feedback.disposition || 'awaiting_response'} /></div><p className="preserve">{feedback.text}</p>{feedback.reason && <p className="disposition-reason">{feedback.reason}</p>}<div className="feedback-links">{linked ? <button className="text-button" onClick={() => showCandidate(linked.id)}>Change & checks: {linked.name}<ArrowRight size={15} /></button> : <span className="muted">{feedback.candidate_id ? `Linked candidate unavailable: ${feedback.candidate_id}` : 'No candidate linked'}</span>}<button aria-expanded={expanded} aria-controls={`respond-${feedback.id}`} disabled={pending} onClick={() => setExpanded(previous => !previous)}><MessageSquare size={15} />{feedback.disposition ? 'Update disposition' : 'Respond'}</button></div>
    {expanded && <form id={`respond-${feedback.id}`} className="response-form" onSubmit={respond}><label>Disposition<select value={disposition} disabled={pending} onChange={event => setDisposition(event.target.value as Disposition)}><option value="apply">Apply</option><option value="clarify">Clarify</option><option value="defer">Defer</option><option value="decline">Decline</option></select></label><label>Resulting candidate<select value={linkedId} disabled={pending} onChange={event => setLinkedId(event.target.value)} required={disposition === 'apply'}><option value="">No candidate linked</option>{run.candidates.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label className="full">Reason<textarea rows={2} required disabled={pending} value={reason} onChange={event => setReason(event.target.value)} /></label><button className="primary" type="submit" disabled={pending || !reason.trim() || (disposition === 'apply' && !linkedId)}><Check size={16} />Record disposition</button></form>}
  </article>;
}

function Report({ run, pending, download, showCandidate }: { run: Run; pending: boolean; download: (format: 'json' | 'csv' | 'html') => Promise<void>; showCandidate: (id: string) => void }) {
  return <section aria-labelledby="report-title"><div className="section-heading"><h2 id="report-title">Experiment record</h2><div className="download-actions">{(['json', 'csv', 'html'] as const).map(format => <button key={format} disabled={pending} aria-label={`Download ${format.toUpperCase()} report`} onClick={() => void download(format)}><ArrowDownToLine size={16} />{format.toUpperCase()}</button>)}</div></div>
    <dl className="report-summary"><div><dt>Decision</dt><dd><Badge value={run.decision} /></dd></div><div><dt>Acceptance</dt><dd><Badge value={run.acceptance} /></dd></div><div><dt>Evidence class</dt><dd>{run.evidence_class}</dd></div><div><dt>Last updated</dt><dd>{date(run.updated_at)}</dd></div></dl>
    <h3 className="subheading">Measured effort</h3><dl className="metrics-grid"><div><dt>Elapsed time</dt><dd>{measured(run.metrics.elapsed_seconds, ' s')}</dd></div><div><dt>Repair cycles</dt><dd>{measured(run.metrics.repair_cycles)}</dd></div><div><dt>Actions</dt><dd>{measured(run.metrics.actions)}</dd></div><div><dt>Calls</dt><dd>{measured(run.metrics.calls)}</dd></div><div><dt>Files changed</dt><dd>{measured(run.metrics.files_changed)}</dd></div><div><dt>Model requests</dt><dd>{measured(run.metrics.model_requests)}</dd></div></dl>
    <h3 className="subheading">Restore receipts</h3>{run.restorations.length ? <ul className="receipts">{run.restorations.map((receipt, index) => <li key={index}><Badge value={receipt.verified ? 'passed' : 'not_verified'} /><span>{receipt.verified ? 'Restore verified by service' : 'Restore not verified'}</span><time dateTime={receipt.at}>{date(receipt.at)}</time><button className="text-button" disabled={!run.candidates.some(item => item.id === receipt.candidate_id)} onClick={() => showCandidate(receipt.candidate_id)}>{receipt.candidate_id}<ArrowRight size={15} /></button></li>)}</ul> : <p className="muted">No restore receipts recorded.</p>}
    <h3 className="subheading">Unreported evidence</h3><dl className="report-gaps"><div><dt>Decision thresholds / trial policy</dt><dd>Not supplied</dd></div><div><dt>Construction cost</dt><dd>Not captured</dd></div><div><dt>Fresh-agent handoff</dt><dd>Not verified</dd></div><div><dt>Outstanding cloud resources</dt><dd>Unknown; no inventory supplied</dd></div><div><dt>Task / tool / agent version pins</dt><dd>Not supplied</dd></div></dl>
  </section>;
}