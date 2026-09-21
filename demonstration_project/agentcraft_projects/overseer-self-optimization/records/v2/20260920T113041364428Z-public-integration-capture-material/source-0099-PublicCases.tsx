import { useEffect, useRef, useState } from "react";
import { ArrowLeft, FileSearch, GitBranch, Monitor, RefreshCw, User, Workflow } from "lucide-react";
import { GraphPanel } from "../graph";
import { SuspectProfiles } from "./SuspectProfiles";
import { publicApi, type PublicProfile, type PublicRecord } from "./publicApi";
import "./publicCases.css";

export function PublicCases({ profile, onAskAgent }: { profile: PublicProfile; onAskAgent: (prompt: string) => void }) {
  const partition = profile.partition!;
  const [cases, setCases] = useState<PublicRecord[]>([]);
  const [selectedCase, setCase] = useState<PublicRecord | null>(null);
  const [alarms, setAlarms] = useState<PublicRecord[]>([]);
  const [alarm, setAlarm] = useState<PublicRecord | null>(null);
  const [events, setEvents] = useState<PublicRecord[]>([]);
  const [event, setEvent] = useState<PublicRecord | null>(null);
  const [source, setSource] = useState<PublicRecord | null>(null);
  const [focus, setFocus] = useState<{ id: number; nodeId: string; name: string } | null>(null);
  const [tab, setTab] = useState<"case" | "graph" | "profiles">("case");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const generation = useRef(0);
  const lastAction = useRef<(() => Promise<void>) | null>(null);

  async function act(label: string, work: (current: () => boolean) => Promise<void>) {
    const current = ++generation.current;
    setBusy(label); setError("");
    lastAction.current = () => act(label, work);
    try { await work(() => generation.current === current); }
    catch (error) { if (current === generation.current) setError(error instanceof Error ? error.message : "Public source unavailable"); }
    finally { if (current === generation.current) setBusy(""); }
  }

  function refresh() {
    return act("Loading cases", async (current) => {
      const result = await publicApi.cases(partition);
      if (current()) { setCases(result); setCase(null); setAlarms([]); setAlarm(null); setEvents([]); setEvent(null); setSource(null); setFocus(null); setTab("case"); }
    });
  }

  useEffect(() => { void refresh(); return () => { generation.current += 1; }; }, [partition]);

  function chooseCase(item: PublicRecord) {
    setCase(item); setAlarm(null); setEvents([]); setEvent(null); setSource(null); setFocus(null); setAlarms([]); setTab("case");
    void act("Loading derived alarms", async (current) => {
      const result = await publicApi.alarms(partition, item.id);
      if (current()) setAlarms(result);
    });
  }

  function chooseAlarm(item: PublicRecord) {
    setAlarm(item); setEvents([]); setEvent(null); setSource(null); setFocus(null);
    void act("Loading source events", async (current) => {
      const result = await Promise.all(item.event_refs.map((ref) => publicApi.evidence(partition, ref)));
      if (current()) setEvents(result.flat());
    });
  }

  function chooseEvent(item: PublicRecord) { setEvent(item); setSource(null); setFocus(null); setTab("case"); }

  function openEvidence(resource: string) {
    void act("Reading graph evidence", async (current) => {
      const result = await publicApi.evidence(partition, resource);
      if (current()) chooseEvent(result[0]);
    });
  }

  return <section className="tool-board public-cases" aria-label="Public investigation">
    <header className="public-heading"><h2>Public investigation</h2>
      <button type="button" title="Refresh cases" aria-label="Refresh cases" disabled={!!busy} onClick={() => void refresh()}><RefreshCw size={16} /></button>
    </header>
    <p className="public-provenance">Public emulation / derived alarms / unlabelled events</p>
    <p className="public-transport">{profile.transport}</p>
    <nav className="public-tabs" aria-label="Public investigation views">
      {(["case", "graph", "profiles"] as const).map((name) => <button type="button" key={name}
        aria-pressed={tab === name} onClick={() => setTab(name)}>{name === "case" ? "Case evidence" : name === "graph" ? "Entity graph" : "Profiles"}</button>)}
    </nav>
    {busy && <p role="status">{busy}</p>}
    {error && <div role="alert" className="error-box">{error}<button type="button" onClick={() => void lastAction.current?.()}><RefreshCw size={14} /> Retry</button></div>}
    {tab === "profiles" ? <SuspectProfiles onAskAgent={onAskAgent} /> : tab === "graph" ? <>
      <button className="public-back" type="button" onClick={() => setTab("case")}><ArrowLeft size={15} /> Case evidence</button>
      <GraphPanel scenarioWindow={null} focusRequest={focus} selectionRequest={null} onEvidence={openEvidence} />
    </> : <div className="public-evidence">
      <h3>Emulation cases</h3>
      {!busy && !cases.length && <p>No cases in this configured scenario.</p>}
      <ul className="public-records">{cases.map((item) => <li key={item.id}>
        <button type="button" aria-pressed={selectedCase?.id === item.id} onClick={() => chooseCase(item)}>{item.title}</button>
      </li>)}</ul>
      {selectedCase && <section aria-label="Derived alarms"><h3>Derived alarms</h3>
        {!busy && !alarms.length && <p>No derived alarm for this case.</p>}
        <ul className="public-records">{alarms.map((item) => <li key={item.id}>
          <button type="button" aria-pressed={alarm?.id === item.id} onClick={() => chooseAlarm(item)}>{item.rule_version}</button>
          <small>Derived pattern, not an original vendor alarm</small>
        </li>)}</ul>
      </section>}
      {alarm && <section aria-label="Source events"><h3>Source events</h3>
        <ul className="public-records">{events.map((item, index) => <li key={item.id}>
          <button type="button" aria-pressed={event?.id === item.id} onClick={() => chooseEvent(item)}>
            Event {index + 1} <time>{item.timestamp}</time>
          </button>
        </li>)}</ul>
      </section>}
      {event && <section aria-label="Event detail" className="public-event-detail">
        <h3>Sysmon process creation</h3><p>{event.host}</p>
        <code className="public-id" data-testid="public-event-id">{event.resource_id}</code>
        <pre>{event.fields.CommandLine}</pre>
        <div className="public-entities" aria-label="Event entities">
          {Object.entries(event.entity_refs).map(([role, id]) => {
            const Icon = role === "host" ? Monitor : role === "user" ? User : role.includes("process") ? Workflow : GitBranch;
            return <button type="button" key={role} aria-label={`Open ${role.replace(/_/g, " ")} graph`}
              onClick={() => { setFocus({ id: Date.now(), nodeId: id, name: role }); setTab("graph"); }}>
              <Icon size={16} /><span>{role.replace(/_/g, " ")}</span>
            </button>;
          })}
        </div>
        <button type="button" className="public-source-button" disabled={!!busy} onClick={() => void act("Reading source record", async (current) => {
          const readback = await publicApi.document(partition, event.id);
          if (current()) setSource(readback);
        })}><FileSearch size={16} /> Source provenance</button>
        {source && <section aria-label="Source provenance" data-testid="public-source"><h3>Source record</h3>
          <dl><div><dt>Cosmos ID</dt><dd>{source.id}</dd></div>
            {Object.entries(source.source).map(([key, value]) => <div key={key}><dt>{key.replace(/_/g, " ")}</dt><dd>{value}</dd></div>)}
          </dl>
        </section>}
      </section>}
    </div>}
  </section>;
}