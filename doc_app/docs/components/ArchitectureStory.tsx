import type { ReactNode } from 'react'
import styles from './ArchitectureStory.module.css'

// Shared primitives. Private to this file so both stories stay visually identical.

const CRITERION: { key: string; value: string }[] = [
  { key: 'must_detect', value: 'two_generating_unit_trips' },
  { key: 'separation_seconds', value: '3' },
  { key: 'expected verdict', value: 'common_mode' },
]

function CriterionBand({ note }: { note: string }) {
  return (
    <div className={styles.criterion} data-carried-criterion="true">
      <div className={styles.criterionLabel}>Carried criterion — {note}</div>
      {CRITERION.map((c) => (
        <div key={c.key} className={styles.criterionField}>
          <span className={styles.criterionKey}>{c.key}</span>
          <span className={styles.criterionValue}>{c.value}</span>
        </div>
      ))}
    </div>
  )
}

type Stage = { title: string; body: ReactNode; note: ReactNode }

function Stages({ stages }: { stages: Stage[] }) {
  return (
    <ol className={styles.stages}>
      {stages.map((s, i) => (
        <li key={s.title} className={styles.stage}>
          <div className={styles.stageHead}>
            <span className={styles.stageIndex} aria-hidden="true">
              {String(i + 1).padStart(2, '0')}
            </span>
            <h3 className={styles.stageTitle}>{s.title}</h3>
          </div>
          <p className={styles.stageBody}>{s.body}</p>
          <p className={styles.stageNote}>{s.note}</p>
        </li>
      ))}
    </ol>
  )
}

function Strip({ items }: { items: { name: string; detail: string }[] }) {
  return (
    <ul className={styles.strip}>
      {items.map((it) => (
        <li key={it.name} className={styles.stripItem}>
          <span className={styles.stripName}>{it.name}</span>
          <span className={styles.stripDetail}>{it.detail}</span>
        </li>
      ))}
    </ul>
  )
}

function CausalityNote() {
  return (
    <li className={styles.note}>
      <strong className={styles.noteTerm}>Chronology is not causality.</strong> A clean
      chronological pair makes the three-second gap visible, which is what the held-out criterion
      checks. It does not on its own show that the two units failed through a shared plant
      dependency. That conclusion still needs topology, shared-dependency, and operator-guidance
      evidence, and the dataset scores those separately.
    </li>
  )
}

function MigrationDebtNote() {
  return (
    <li className={styles.note}>
      <strong className={styles.noteTerm}>Honest state of the pack.</strong> GridIQ is
      composition-owned by its pack, but its routers, tools, prompts, and configuration still carry
      physical migration debt, recorded in <code>usecases/gridiq/manifest.v2.yaml</code>. WorkOrders
      is the pack that demonstrates clean ownership end to end; GridIQ is on the way there.
    </li>
  )
}

// --- Modular Change -------------------------------------------------------

const MODULAR_STAGES: Stage[] = [
  {
    title: 'Diagnose',
    body: (
      <>
        A held-out run misses the criterion. Inspect the boundary first: did <code>find_alarms</code>{' '}
        run, did its envelope contain the ordered rows, and did the response use that evidence?
      </>
    ),
    note: (
      <>
        Current GridIQ already projects timestamps and equipment in chronological order; do not
        invent a tool defect.
      </>
    ),
  },
  {
    title: 'Change',
    body: (
      <>
        Edit the first failing owner only. A missing call points to registration or workflow
        guidance; missing evidence points to the projection; ignored evidence points to the prompt.
      </>
    ),
    note: (
      <>
        Untouched: the runtime and host, every unrelated tool, and every boundary already proven
        correct.
      </>
    ),
  },
  {
    title: 'Prove',
    body: (
      <>
        Run the focused envelope test first — schema and chronological order — then re-score the
        held-out case for <code>separation_seconds: 3</code>.
      </>
    ),
    note: (
      <>
        Negative guard: the case must still fail if the run calls the shared-plant conclusion on
        alarms alone.
      </>
    ),
  },
  {
    title: 'Reverse',
    body: (
      <>
        If the held-out score does not move, restore only the prompt, registration, or projection
        that changed, then roll back to the previously deployed revision.
      </>
    ),
    note: <>One seam changed means one seam to undo; nothing else was generated.</>,
  },
]

const OTHER_SLOTS = [
  { name: 'Prompt', detail: 'control/prompts/grid/* via loader' },
  { name: 'Config / team', detail: 'control/agents/grid.yaml; role map' },
  { name: 'Provider', detail: 'pack adapter behind a stable protocol' },
  { name: 'API', detail: 'schema + router via BackendContribution' },
  { name: 'UI', detail: 'uiContribution.tsx via @agentkit/ui' },
]

export function ModularChangeStory({ part = 'flow' }: { part?: 'flow' | 'slots' }) {
  if (part === 'flow') {
    return (
      <div className={styles.block}>
        <p className={styles.sectionLead}>
          The criterion below comes straight from the labelled case on{' '}
          <a className={styles.link} href="/dataset-prep">
            Dataset Preparation
          </a>
          . It is the check the run has to satisfy, and it is what makes the next four steps
          arguable rather than a matter of taste.
        </p>

        <div data-primary-visual="modular-change">
          <CriterionBand note="from the Yallourn W case" />
          <Stages stages={MODULAR_STAGES} />
        </div>
      </div>
    )
  }

  return (
    <div className={styles.block}>
      <p className={styles.sectionLead}>
        A tool is one of several slots the host already knows how to load. The same
        change-prove-reverse discipline applies to each; none of them were touched here.
      </p>
      <Strip items={OTHER_SLOTS} />

      <ul className={styles.notes}>
        <CausalityNote />
        <MigrationDebtNote />
      </ul>

      <p className={styles.onward}>
        The full slot atlas this page condenses is preserved verbatim as{' '}
        <a
          className={styles.link}
          href="/architecture/sources/gridiq-modular-change-atlas.html"
          target="_blank"
          rel="noreferrer"
        >
          the original modular change atlas
        </a>
        . Next, open the seam itself:{' '}
        <a className={styles.link} href="/specialized-tools">
          Specialized Tools
        </a>{' '}
        shows what the alarm capability actually offers the agent.
      </p>
    </div>
  )
}

// --- Specialized Tools ----------------------------------------------------

const KQL = `let start = datetime(2024-04-15T10:00:00Z);
let end = datetime(2024-04-15T10:15:00Z);
WatcherAlarmsAll
| where station == "STN_A"
| where timestamp_aest between (start .. end)
| where alarm_label has "CB"
| project timestamp_aest, alarm_label, priority,
          client_composite_id, alarm_text
| order by timestamp_aest asc`

const TOOL_CALL = `find_alarms(
  station="STN_A",
  start="2024-04-15T10:00:00Z",
  end="2024-04-15T10:15:00Z",
  label="CB"
)`

const RESULT_ROWS = [
  { time: 'T+02m00s', label: 'CB', priority: 'high', equipment: 'CB-101' },
  { time: 'T+02m03s', label: 'CB', priority: 'high', equipment: 'CB-102' },
  { time: 'T+07m', label: 'CB', priority: 'medium', equipment: 'CB-104' },
]

const LAYERS = [
  {
    name: 'Capability',
    owns: 'typed station / start / end / label / equipment parameters, domain projection',
    where: 'a real @tool in the pack',
  },
  {
    name: 'Shared adapter',
    owns: 'transport, read-only enforcement, row bounds',
    where: 'the shared KQL adapter behind every alarm tool',
  },
  {
    name: 'Stable slot',
    owns: 'SDK-free metadata, allowlisted module:function resolution',
    where: 'agentkit.tools.tool, agentkit/core/tool_resolver.py',
  },
]

export function SpecializedToolStory({
  part = 'compare',
}: {
  part?: 'compare' | 'layers' | 'limits'
}) {
  if (part === 'compare') {
    return (
      <div className={styles.block}>
        <CriterionBand note="still the same held-out check" />
        <p className={styles.sectionLead}>
          Both sides ask the same question of the same alarm table. On the left the agent has to
          write and repair a query; on the right it chooses a capability and supplies parameters,
          and the result comes back already ordered.
        </p>

        <div data-primary-visual="specialized-tools">
          <div className={styles.comparison}>
            <div className={styles.side}>
              <h3 className={styles.columnTitle}>Write the query</h3>
              <pre
                className={styles.code}
                tabIndex={0}
                role="group"
                aria-label="Representative KQL query against WatcherAlarmsAll"
              >
                {KQL}
              </pre>
            </div>
            <div className={styles.side}>
              <h3 className={styles.columnTitle}>Call the tool</h3>
              <pre
                className={`${styles.code} ${styles.codeTool}`}
                tabIndex={0}
                role="group"
                aria-label="Equivalent typed find_alarms tool call"
              >
                {TOOL_CALL}
              </pre>
            </div>
          </div>

          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <caption>
                Synthetic result — chronological projection, illustrative values only
              </caption>
              <thead>
                <tr>
                  <th scope="col">Time</th>
                  <th scope="col">Label</th>
                  <th scope="col">Priority</th>
                  <th scope="col">Equipment</th>
                </tr>
              </thead>
              <tbody>
                {RESULT_ROWS.map((r) => (
                  <tr key={r.equipment}>
                    <th scope="row">{r.time}</th>
                    <td>{r.label}</td>
                    <td>{r.priority}</td>
                    <td>{r.equipment}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    )
  }

  if (part === 'layers') {
    return (
      <div className={styles.block}>
        <p className={styles.sectionLead}>
          A <strong>stable slot</strong> is a runtime contract the host already knows how to load. A{' '}
          <strong>capability</strong> is a bounded typed function that fills one. Together the tool
          and its shared adapter own schema, validation, bounds, and projection, which is why the
          agent is left with a choice rather than a query.
        </p>
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <caption>What each layer is responsible for</caption>
            <thead>
              <tr>
                <th scope="col">Layer</th>
                <th scope="col">Owns</th>
                <th scope="col">Where it lives</th>
              </tr>
            </thead>
            <tbody>
              {LAYERS.map((l) => (
                <tr key={l.name}>
                  <th scope="row">{l.name}</th>
                  <td>{l.owns}</td>
                  <td>{l.where}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className={styles.sectionLead}>
          The decorator is SDK-free: it stamps metadata and returns the callable unwrapped, so
          framework binding happens later and the same function stays testable on its own. The same
          shape covers other backends — <code>graph_station_equipment</code> over the topology graph
          and <code>search_nearhit_reports</code> over the report index.
        </p>
      </div>
    )
  }

  return (
    <div className={styles.block}>
      <ul className={styles.notes}>
        <CausalityNote />
        <MigrationDebtNote />
      </ul>
      <p className={styles.onward}>
        The denser original is preserved verbatim as{' '}
        <a
          className={styles.link}
          href="/architecture/sources/gridiq-specialized-tools.html"
          target="_blank"
          rel="noreferrer"
        >
          the specialized tools writeup
        </a>
        . For how a failed check becomes a scored decision, read{' '}
        <a className={styles.link} href="/method">
          Method
        </a>
        ; to watch an agent use these capabilities on a live-feed incident,{' '}
        <a className={styles.link} href="/demo/">
          See Demo
        </a>
        .
      </p>
    </div>
  )
}
