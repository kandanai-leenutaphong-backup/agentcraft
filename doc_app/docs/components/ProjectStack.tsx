import styles from './ProjectStack.module.css'

type Project = {
  name: string
  status: string
  shipped?: boolean
  summary: string
  facts?: { value: string; label: string }[]
}

const projects: Project[] = [
  {
    name: 'GridIQ — Control Room Operator Augmentation',
    status: 'Successful',
    shipped: true,
    summary:
      'The control room augmentation agent team. Built within six weeks, then hardened against ' +
      'historical test cases over a six month period.',
    facts: [
      { value: '6 weeks', label: 'To first build' },
      { value: '95%', label: 'Success' },
      { value: '100%', label: 'Detection' },
    ],
  },
  {
    name: 'Agentic Cybersecurity PoC',
    status: 'Successful',
    shipped: true,
    summary: 'Detecting simulated cyberattacks against the operating environment.',
    facts: [{ value: 'PoC', label: 'Delivered' }],
  },
  {
    name: 'Third PoC — to be named',
    status: 'Successful',
    shipped: true,
    summary:
      'Placeholder. The record states three successful PoCs; the third is not yet written up here.',
  },
  {
    name: 'Platform Discussion',
    status: 'In progress',
    summary:
      'Proceeding on the back of the three PoCs, toward a long-term partnership.',
    facts: [
      { value: '$100M', label: 'MACC secured' },
      { value: '$250M', label: 'Partnership target' },
    ],
  },
]

export function ProjectStack() {
  return (
    <div className={styles.stack}>
      {projects.map((p, i) => (
        <article
          key={p.name}
          className={`${styles.project} ${p.shipped ? styles.shipped : styles.pending}`}
        >
          <div className={styles.head}>
            <span className={styles.index}>{String(i + 1).padStart(2, '0')}</span>
            <span className={styles.name}>{p.name}</span>
            <span className={`${styles.status} ${p.shipped ? styles.statusShipped : ''}`}>
              {p.status}
            </span>
          </div>

          <p className={styles.summary}>{p.summary}</p>

          {p.facts && (
            <div className={styles.facts}>
              {p.facts.map((f) => (
                <div key={f.label} className={styles.fact}>
                  <span className={styles.factValue}>{f.value}</span>
                  <span className={styles.factLabel}>{f.label}</span>
                </div>
              ))}
            </div>
          )}
        </article>
      ))}
    </div>
  )
}
