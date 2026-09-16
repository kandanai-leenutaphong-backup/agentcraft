import styles from './AssetCanvas.module.css'

const assets = [
  { slug: 'agent-harness', x: 20, y: 20, name: 'Agent Harness',
    desc: 'Long-running autonomous work: hooks, review gates, issue-bound specs.' },
  { slug: 'component-library', x: 370, y: 50, name: 'Component Library',
    desc: 'Chat surface, tool renderers, theme tokens, contribution contracts.' },
  { slug: 'azure-connectors', x: 720, y: 20, name: 'Azure Connectors',
    desc: 'Data plane clients on managed identity. No keys, no connection strings.' },
  { slug: 'eval-harness', x: 20, y: 300, name: 'Evaluation Harness',
    desc: 'Scored test batteries producing quantifiable evidence bundles.' },
  { slug: 'deploy-templates', x: 370, y: 320, name: 'Deploy Templates',
    desc: 'Bicep plus auth wiring. One command to a tenant-gated app.' },
  { slug: 'data-pipelines', x: 720, y: 300, name: 'Data Pipelines',
    desc: 'Ingestion, profiling, and labeled dataset construction.' },
]

// Each wire runs edge-to-edge between two boxes; redraw these if boxes move.
const wires = [
  'M316 95 C348 95 340 125 370 125',
  'M666 125 C698 125 690 95 720 95',
  'M168 170 C168 220 168 250 168 300',
  'M518 320 C580 250 800 250 868 170',
  'M720 375 C698 375 690 395 666 395',
]

export function AssetCanvas({ org = 'han-microsoft' }: { org?: string }) {
  return (
    <div className={styles.canvasScroll}>
      <div className={styles.canvas}>
        <svg className={styles.wires} viewBox="0 0 1036 490" aria-hidden="true">
          <defs>
            <marker id="wire-arrow" viewBox="0 0 10 10" refX="9" refY="5"
                    markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M0 0 L10 5 L0 10 z" className={styles.wireHead} />
            </marker>
          </defs>
          {wires.map((d) => (
            <path key={d} className={styles.wire} d={d} markerEnd="url(#wire-arrow)" />
          ))}
        </svg>

        {assets.map((a) => (
          <a key={a.slug} className={styles.node} style={{ left: a.x, top: a.y }}
             href={`https://github.com/${org}/${a.slug}`}
             target="_blank" rel="noopener noreferrer">
            <span className={styles.name}>{a.name}</span>
            <span className={styles.desc}>{a.desc}</span>
            <span className={styles.repo}>{org}/{a.slug}</span>
          </a>
        ))}
      </div>
    </div>
  )
}
