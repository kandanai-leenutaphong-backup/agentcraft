import styles from './CustomerBoard.module.css'

type Customer = {
  name: string
  project: string
  metrics?: { label: string; kind?: 'win' | 'pending' }[]
  tags?: string[]
  featured?: boolean
}

type Stage = {
  name: string
  owner?: string
  color: string
  customers: Customer[]
}

const stages: Stage[] = [
  {
    name: 'Production Path, Multiple PoCs Succeeded',
    color: 'var(--vocs-color_borderGreen)',
    customers: [
      {
        name: 'AEMO',
        project: 'GridIQ: Control Room Operator Augmentation',
        metrics: [
          { label: '3 PoCs Successful', kind: 'win' },
          { label: '$100M MACC', kind: 'win' },
          { label: 'Platform discussion proceeding' },
        ],
        tags: ['MIQ Win'],
        featured: true,
      },
    ],
  },
  {
    name: 'Value Proving, PoCs Ongoing',
    color: 'var(--vocs-color_borderYellow)',
    customers: [
      {
        name: 'Surbana Jurong',
        project: 'Central Enterprise Tool Search Engine',
        metrics: [
          { label: '1 PoC Successful', kind: 'win' },
          { label: 'Awaiting Expanded PoC Scope', kind: 'pending' },
        ],
        tags: ['FoundryIQ', 'WorkIQ'],
      },
      {
        name: 'SingTel',
        project: 'Workforce Transformation Platform',
        metrics: [
          { label: '1 PoC Successful', kind: 'win' },
          { label: 'Awaiting Expanded PoC Scope', kind: 'pending' },
        ],
        tags: ['FoundryIQ', 'WorkIQ'],
      },
      {
        name: 'Perth Airport',
        project: 'Security Operations Investigation',
        metrics: [{ label: 'Automated Build Ongoing' }],
        tags: ['MIQ'],
      },
    ],
  },
  {
    name: 'Workshopping, Ideation',
    owner: 'Luca Stamatescu',
    color: 'var(--vocs-color_borderBlue)',
    customers: [
      { name: 'TransGrid', project: 'Control Room Operations' },
      { name: 'Telstra', project: 'Autonomous Network Prototyping' },
    ],
  },
  {
    name: 'Planning Stage, Awaiting Requirements',
    color: 'var(--vocs-color_border2)',
    customers: [
      { name: 'SP Power Grid', project: 'Predictive Maintenance, Asset Management, Developer Platform' },
      { name: 'Horizon Power', project: 'Workshops Planned' },
      { name: 'MISO', project: 'Workshop Planned' },
    ],
  },
]

const summary = [
  { value: '9', label: 'Customers', accent: false },
  { value: '5', label: 'PoCs Successful', accent: false },
  { value: '$100M', label: 'MACC Won', accent: true },
  { value: '$250M', label: 'Partnership Target', accent: false },
]

export function CustomerBoard() {
  return (
    <div>
      <div className={styles.summary}>
        {summary.map((s) => (
          <div key={s.label} className={styles.stat}>
            <span className={`${styles.statValue} ${s.accent ? styles.statValueAccent : ''}`}>
              {s.value}
            </span>
            <span className={styles.statLabel}>{s.label}</span>
          </div>
        ))}
      </div>

      {stages.map((stage) => (
        <section key={stage.name} className={styles.stage}>
          <div className={styles.stageHead}>
            <span className={styles.dot} style={{ background: stage.color }} />
            <span className={styles.stageName}>{stage.name}</span>
            {stage.owner && <span className={styles.stageOwner}>{stage.owner}</span>}
            <span className={styles.stageCount}>{stage.customers.length}</span>
          </div>

          <div className={styles.cards}>
            {stage.customers.map((c) => (
              <div
                key={c.name}
                className={`${styles.card} ${c.featured ? styles.featured : ''}`}
                style={{ borderLeftColor: stage.color }}
              >
                <span className={styles.name}>{c.name}</span>
                <span className={styles.project}>{c.project}</span>

                {c.metrics && (
                  <div className={styles.metrics}>
                    {c.metrics.map((m) => (
                      <span
                        key={m.label}
                        className={`${styles.metric} ${
                          m.kind === 'win' ? styles.metricWin : m.kind === 'pending' ? styles.metricPending : ''
                        }`}
                      >
                        {m.label}
                      </span>
                    ))}
                  </div>
                )}

                {c.tags && (
                  <div className={styles.tags}>
                    {c.tags.map((t) => (
                      <span key={t} className={styles.tag}>{t}</span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  )
}
