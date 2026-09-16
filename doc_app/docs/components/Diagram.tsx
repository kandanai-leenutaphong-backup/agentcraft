/* Method step diagrams. Square corners; cyan carries flow, sage and red carry outcome. */

const box = { fill: 'var(--vocs-color_background3)', stroke: 'var(--vocs-color_border2)', strokeWidth: 1 }
const boxAccent = { fill: 'var(--vocs-color_backgroundAccentTint, transparent)', stroke: 'var(--vocs-color_borderAccent)', strokeWidth: 1.5 }
const boxGood = { fill: 'transparent', stroke: 'var(--vocs-color_borderGreen)', strokeWidth: 1.5 }
const boxBad = { fill: 'transparent', stroke: 'var(--vocs-color_borderRed)', strokeWidth: 1.5 }
const arrow = { fill: 'none', stroke: 'var(--vocs-color_borderAccent)', strokeWidth: 2 }
const rule = { stroke: 'var(--vocs-color_border)', strokeWidth: 1 }
const label = { fontSize: 14, textAnchor: 'middle' as const, fill: 'var(--vocs-color_text2)' }
const caption = { fontSize: 12, textAnchor: 'middle' as const, fill: 'var(--vocs-color_text3)', letterSpacing: '0.1em' }

function Frame({ children }: { children: React.ReactNode }) {
  return (
    <svg viewBox="0 0 520 150" style={{ width: '100%', maxWidth: 620, height: 'auto', display: 'block', margin: '18px 0' }}>
      <defs>
        <marker id="m-arrow" viewBox="0 0 10 10" refX="9" refY="5"
                markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M0 0 L10 5 L0 10 z" fill="var(--vocs-color_borderAccent)" />
        </marker>
      </defs>
      {children}
    </svg>
  )
}

const diagrams: Record<string, React.ReactNode> = {
  experiment: (
    <>
      <rect x="8" y="30" width="120" height="90" {...box} />
      <text x="68" y="70" {...label}>unstructured</text>
      <text x="68" y="90" {...label}>source</text>
      <path d="M136 75 H196" {...arrow} markerEnd="url(#m-arrow)" />
      <rect x="204" y="20" width="130" height="110" {...box} />
      <line x1="204" y1="48" x2="334" y2="48" {...rule} />
      <line x1="204" y1="76" x2="334" y2="76" {...rule} />
      <line x1="204" y1="104" x2="334" y2="104" {...rule} />
      <text x="269" y="14" {...caption}>LABELED SET</text>
      <path d="M342 75 H402" {...arrow} markerEnd="url(#m-arrow)" />
      <rect x="410" y="45" width="100" height="60" {...boxAccent} />
      <text x="460" y="80" {...label}>ceiling</text>
    </>
  ),
  build: (
    <>
      <rect x="20" y="24" width="96" height="40" {...box} />
      <text x="68" y="49" {...label}>tools</text>
      <rect x="20" y="86" width="96" height="40" {...box} />
      <text x="68" y="111" {...label}>prompts</text>
      <rect x="140" y="55" width="96" height="40" {...box} />
      <text x="188" y="80" {...label}>config</text>
      <path d="M124 44 H140 V70" {...arrow} />
      <path d="M124 106 H140 V82" {...arrow} />
      <path d="M244 75 H304" {...arrow} markerEnd="url(#m-arrow)" />
      <rect x="312" y="40" width="150" height="70" {...boxAccent} />
      <text x="387" y="80" {...label}>agent</text>
    </>
  ),
  deploy: (
    <>
      <rect x="30" y="50" width="120" height="55" {...box} />
      <text x="90" y="83" {...label}>image</text>
      <path d="M158 78 H248" {...arrow} markerEnd="url(#m-arrow)" />
      <path d="M300 40 a44 30 0 1 1 66 34 h-88 a30 26 0 1 1 22 -34 z" {...boxAccent} />
      <rect x="278" y="86" width="180" height="34" {...box} />
      <text x="368" y="108" {...label}>running service</text>
    </>
  ),
  test: (
    <>
      {[40, 112, 184, 256, 328, 400].map((x, i) => (
        <rect key={`a${x}`} x={x} y="30" width="60" height="38" {...(i === 3 ? boxBad : boxGood)} />
      ))}
      {[40, 112, 184, 256, 328, 400].map((x, i) => (
        <rect key={`b${x}`} x={x} y="82" width="60" height="38" {...(i === 1 ? boxBad : boxGood)} />
      ))}
    </>
  ),
  evaluate: (
    <>
      <line x1="60" y1="126" x2="470" y2="126" {...rule} />
      <rect x="90" y="96" width="52" height="30" {...box} />
      <rect x="170" y="74" width="52" height="52" {...box} />
      <rect x="250" y="58" width="52" height="68" {...box} />
      <rect x="330" y="40" width="52" height="86" {...boxAccent} />
      <rect x="410" y="34" width="52" height="92" {...boxAccent} />
      <text x="80" y="26" {...caption}>SCORE</text>
    </>
  ),
  refine: (
    <>
      <path d="M150 108 a115 62 0 1 1 220 0" {...arrow} strokeDasharray="6 5" markerEnd="url(#m-arrow)" />
      <rect x="96" y="90" width="120" height="42" {...box} />
      <text x="156" y="116" {...label}>edit</text>
      <rect x="304" y="90" width="120" height="42" {...boxAccent} />
      <text x="364" y="116" {...label}>re-run</text>
      <text x="260" y="34" {...caption}>PLATEAU, THEN STOP</text>
    </>
  ),
}

export function Diagram({ name }: { name: keyof typeof diagrams }) {
  return <Frame>{diagrams[name]}</Frame>
}
