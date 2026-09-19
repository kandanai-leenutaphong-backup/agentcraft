import { useEffect, useRef, useState } from "react";
import { RefreshCw, Sparkles, UserRound } from "lucide-react";
import { requestJson } from "../../shared/api";
import "./profiles.css";

interface ProfileCitation {
  evidence_id: string;
  record: Record<string, string | number | boolean>;
  retrieval: {
    retrieval_id: string; tool: string; display_name: string; datasource: string;
    query: string; retrieved_at: string; row_count: number;
  };
}

interface SuspectProfile {
  profile_id: string;
  revision: number;
  identity: { account: string; display_name: string };
  activity: { timestamp: string; summary: string; evidence_ids: string[] }[];
  citations: ProfileCitation[];
  updated_at: string;
  historical_replay: true;
}

export function SuspectProfiles({ onAskAgent }: { onAskAgent: (prompt: string) => void }) {
  const [profiles, setProfiles] = useState<SuspectProfile[]>([]);
  const [selected, setSelected] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const generation = useRef(0);

  useEffect(() => {
    const updated = () => setRefresh((value) => value + 1);
    window.addEventListener("suspect-profile-updated", updated);
    return () => window.removeEventListener("suspect-profile-updated", updated);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const current = ++generation.current;
    setLoading(true);
    setError("");
    requestJson<SuspectProfile[]>("/api/cyber/suspect-profiles", { signal: controller.signal })
      .then((value) => {
        if (current !== generation.current || controller.signal.aborted) return;
        setProfiles(value);
        setSelected((previous) => value.some((profile) => profile.profile_id === previous)
          ? previous : value[0]?.profile_id ?? "");
      })
      .catch((failure: Error) => {
        if (!controller.signal.aborted) setError(failure.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [refresh]);

  const profile = profiles.find((item) => item.profile_id === selected);
  const ask = () => onAskAgent(profile
    ? `Update suspect profile ${profile.profile_id} for ${profile.identity.account}. Read its current revision, retrieve historical telemetry in this turn, and persist cited activity with update_suspect_profile. Do not infer guilt or compromise.`
    : "Create a persisted suspect profile for the account in the selected investigation. Read its current profile revision, retrieve historical telemetry in this turn, and persist identity and cited activity with update_suspect_profile. Do not infer guilt or compromise.");

  return <section className="suspect-profiles" aria-label="Suspect profiles" aria-busy={loading}>
    <header className="profile-toolbar">
      <h2><UserRound size={18} aria-hidden="true" /> Suspect profiles</h2>
      <button type="button" title="Refresh profiles" aria-label="Refresh profiles"
        aria-disabled={loading} onClick={() => { if (!loading) setRefresh((value) => value + 1); }}><RefreshCw size={17} /></button>
      <button type="button" onClick={ask}><Sparkles size={16} aria-hidden="true" />{profile ? "Update profile" : "Create profile"}</button>
    </header>
    {loading && <p role="status">Loading profiles...</p>}
    {error && <p role="alert" className="error-box">Profile readback failed: {error}</p>}
    {!loading && !error && !profiles.length && <p role="status">No saved suspect profiles.</p>}
    {profiles.length > 1 && <label className="profile-picker">Suspect
      <select value={selected} onChange={(event) => setSelected(event.target.value)}>
        {profiles.map((item) => <option key={item.profile_id} value={item.profile_id}>{item.identity.display_name} ({item.identity.account})</option>)}
      </select>
    </label>}
    {profile && <div className="profile-detail" data-profile-id={profile.profile_id}>
      <div className="profile-identity">
        <h3>{profile.identity.display_name}</h3>
        <p>{profile.identity.account}</p>
        <p className="profile-status" role="status">Revision {profile.revision}{error ? " (last loaded)" : ""}</p>
        <p className="profile-meta">Historical replay | Saved <time dateTime={profile.updated_at}>{profile.updated_at}</time></p>
      </div>
      <h3>Historical activity</h3>
      <ol className="profile-activity">
        {profile.activity.map((activity, index) => <li key={index}>
          <time dateTime={activity.timestamp}>{activity.timestamp}</time>
          <p>{activity.summary}</p>
          <div className="profile-citations">
            {activity.evidence_ids.map((id) => {
              const citation = profile.citations.find((item) => item.evidence_id === id);
              return citation && <details key={id}>
                <summary aria-label={`Evidence ${id}`}>{id}</summary>
                <dl>
                  <dt>Source</dt><dd>{citation.retrieval.datasource}</dd>
                  <dt>Tool</dt><dd>{citation.retrieval.display_name}</dd>
                  <dt>Retrieved</dt><dd>{citation.retrieval.retrieved_at}</dd>
                  <dt>Query</dt><dd>{citation.retrieval.query}</dd>
                  {Object.entries(citation.record).map(([key, value]) => <div key={key} className="profile-record-field">
                    <dt>{key}</dt><dd>{String(value)}</dd>
                  </div>)}
                </dl>
              </details>;
            })}
          </div>
        </li>)}
      </ol>
    </div>}
  </section>;
}