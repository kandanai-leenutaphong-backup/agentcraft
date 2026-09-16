import caseData from '../data/yallourn-w-2025-10-16.case.json'
import styles from './DatasetPreparation.module.css'

type Excerpt = { id: string; marker: number; field: string; text: string }

type LabelKey =
  | 'key_events'
  | 'expected_signal_detection'
  | 'expected_next_action'
  | 'expected_analysis'

const data = caseData as unknown as {
  source: {
    publisher: string
    title: string
    document_type: string
    published: string
    url: string
    retrieved: string
    page: number
    page_count: number
  }
  evidence: Excerpt[]
  labels: Record<LabelKey, unknown>
}

const PDF_HREF = '/dataset-prep/trip-of-yallourn-w-power-station-unit-3-and-unit-4.pdf'
const PAGE_IMAGE = '/dataset-prep/yallourn-report-page-3.png'

const SECTIONS: { key: LabelKey; anchor: string; title: string; question: string }[] = [
  {
    key: 'key_events',
    anchor: 'key-events',
    title: 'Key Events',
    question: 'What happened, in order, and where is each step written down?',
  },
  {
    key: 'expected_signal_detection',
    anchor: 'expected-signal-detection',
    title: 'Expected Signal Detection',
    question: 'Which signals must the agent raise, and must it read them as common-mode?',
  },
  {
    key: 'expected_next_action',
    anchor: 'expected-next-action',
    title: 'Expected Next Action',
    question: 'What must the agent do next, and what must it never propose?',
  },
  {
    key: 'expected_analysis',
    anchor: 'expected-analysis',
    title: 'Expected Analysis',
    question: 'What must the written analysis assert, and what would be a hallucination?',
  },
]

const LOOP: { step: string; label: string; detail: string }[] = [
  {
    step: 'Dataset',
    label: 'Four label objects',
    detail:
      'The four objects below are the case. Nothing in them is opinion: every entry carries source ' +
      'references back to excerpts on page 3.',
  },
  {
    step: 'Run',
    label: 'Agent output',
    detail:
      'The agent receives the same incident as a live feed and produces its own events, signals, ' +
      'actions and analysis.',
  },
  {
    step: 'Score',
    label: 'Pass / fail per entry',
    detail:
      'Each labelled entry becomes one check. Missing 1334.32 fails. Calling the trips independent ' +
      'fails. Claiming customer load loss or a transmission fault fails on must_not_claim.',
  },
  {
    step: 'Refine',
    label: 'Edit the application',
    detail:
      'A failed check names the artifact to edit — a tool that never returned the shared-plant ' +
      'dependency, a prompt that did not demand a citation, an interface that hid the 3-second gap. ' +
      'Tuning is a code change, not a weight update.',
  },
]

function collectRefs(node: unknown, out: Set<string> = new Set()): Set<string> {
  if (Array.isArray(node)) {
    for (const item of node) collectRefs(item, out)
  } else if (node && typeof node === 'object') {
    for (const [key, value] of Object.entries(node as Record<string, unknown>)) {
      if (key === 'source_refs' && Array.isArray(value)) {
        for (const id of value) out.add(String(id))
      } else {
        collectRefs(value, out)
      }
    }
  }
  return out
}

export function DatasetPreparation() {
  const { source, evidence, labels } = data
  const byId = new Map(evidence.map((e) => [e.id, e]))

  return (
    <div className={styles.root}>
      <section className={styles.stage} aria-labelledby="source-page">
        <h2 id="source-page" className={styles.stageTitle}>
          The source: page {source.page} of {source.page_count}
        </h2>
        <p className={styles.stageMeta}>
          {source.publisher} — <cite>{source.title}</cite>. {source.document_type}, published{' '}
          {source.published}. Retrieved {source.retrieved}.{' '}
          <a className={styles.pdfLink} href={PDF_HREF} target="_blank" rel="noreferrer">
            Open the full report (PDF)
          </a>
        </p>

        <figure className={styles.well}>
          <img
            className={styles.page}
            src={PAGE_IMAGE}
            width={953}
            height={1348}
            alt={
              `Page ${source.page} of the AEMO incident report. It carries the summary table — ` +
              'incident classification, 597 MW of generation lost, no customer load lost, the ' +
              'common cooling system — then the numbered key events from the 1334.29 and 1334.32 ' +
              'unit trips through restoration, and the confirmed cooling-water valve actuator cause. ' +
              'The verbatim text of every fact used below is listed under this image.'
            }
          />
          <figcaption className={styles.wellCaption}>
            Rendered from the local copy of the PDF. The numbered excerpts below are transcribed
            from this page and are checked against its extracted text on every build.
          </figcaption>
        </figure>
      </section>

      <nav className={styles.nav} aria-label="Dataset labels">
        {SECTIONS.map((s) => (
          <a key={s.key} className={styles.navLink} href={`#${s.anchor}`}>
            {s.title}
          </a>
        ))}
      </nav>

      {SECTIONS.map((s) => {
        const value = labels[s.key]
        const refs = [...collectRefs(value)]
          .map((id) => byId.get(id))
          .filter((e): e is Excerpt => Boolean(e))
          .sort((a, b) => a.marker - b.marker)

        return (
          <section key={s.key} id={s.anchor} className={styles.section}>
            <h2 className={styles.sectionTitle}>{s.title}</h2>
            <p className={styles.sectionQuestion}>{s.question}</p>

            <div className={styles.split}>
              <div className={styles.evidence}>
                <h3 className={styles.columnTitle}>Source excerpts — page {source.page}, verbatim</h3>
                <ol className={styles.ledger}>
                  {refs.map((e) => (
                    <li key={e.id} className={styles.excerpt} data-source-id={e.id}>
                      <span className={styles.marker} aria-hidden="true">
                        {e.marker}
                      </span>
                      <span className={styles.excerptBody}>
                        <span className={styles.excerptField}>{e.field}</span>
                        <q className={styles.excerptText}>{e.text}</q>
                        <span className={styles.excerptId}>{e.id}</span>
                      </span>
                    </li>
                  ))}
                </ol>
              </div>

              <div className={styles.json}>
                <h3 className={styles.columnTitle}>Labelled output — {s.key}.json</h3>
                <pre className={styles.code} data-dataset-json={s.key}>
                  {JSON.stringify(value, null, 2)}
                </pre>
              </div>
            </div>
          </section>
        )
      })}

      <section id="closing-the-loop" className={styles.section}>
        <h2 className={styles.sectionTitle}>From labels to a score to a code change</h2>
        <p className={styles.sectionQuestion}>
          The labels are only useful because each one is a check the agent either passes or fails.
        </p>
        <ol className={styles.loop}>
          {LOOP.map((l, i) => (
            <li key={l.step} className={styles.loopStep}>
              <span className={styles.loopIndex} aria-hidden="true">
                {String(i + 1).padStart(2, '0')}
              </span>
              <span className={styles.loopBody}>
                <span className={styles.loopHead}>
                  <strong className={styles.loopStepName}>{l.step}</strong>
                  <span className={styles.loopLabel}>{l.label}</span>
                </span>
                <span className={styles.loopDetail}>{l.detail}</span>
              </span>
            </li>
          ))}
        </ol>
        <p className={styles.handoff}>
          The next page follows one of those failed checks all the way down.{' '}
          <a className={styles.handoffLink} href="/modular-change">
            Modular Change
          </a>{' '}
          carries this case's three-second criterion forward, localizes the failure to a single
          owned seam, and shows how the change is proved and reversed.
        </p>
      </section>
    </div>
  )
}
