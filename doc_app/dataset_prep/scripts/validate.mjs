#!/usr/bin/env node
// Checks the labeled case against the committed page-3 text extracted from the
// source PDF. `--self-test` proves the checks actually refuse bad input.

import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const ARTIFACT = join(root, 'artifacts', 'yallourn-w-2025-10-16.case.json')
const PAGE_TEXT = join(root, 'source', 'yallourn-report-page-3.txt')

const LABEL_GROUPS = [
  'key_events',
  'expected_signal_detection',
  'expected_next_action',
  'expected_analysis',
]

const norm = (s) => s.replace(/[\s\u00a0]+/g, ' ').trim()

function collectRefs(node, out = []) {
  if (Array.isArray(node)) {
    for (const item of node) collectRefs(item, out)
  } else if (node && typeof node === 'object') {
    for (const [key, value] of Object.entries(node)) {
      if (key === 'source_refs') {
        if (!Array.isArray(value) || value.length === 0) {
          out.push({ id: null, reason: 'source_refs must be a non-empty array' })
        } else {
          for (const id of value) out.push({ id })
        }
      } else {
        collectRefs(value, out)
      }
    }
  }
  return out
}

function validate(artifact, pageText) {
  const failures = []
  const fail = (msg) => failures.push(msg)
  const page = norm(pageText)

  if (!artifact.source || artifact.source.page !== 3) fail('source.page must be 3')
  for (const field of ['publisher', 'title', 'url', 'retrieved', 'pdf_sha256']) {
    if (!artifact.source?.[field]) fail(`source.${field} is missing`)
  }

  const evidence = artifact.evidence
  if (!Array.isArray(evidence) || evidence.length === 0) fail('evidence must be a non-empty array')

  const ids = new Set()
  for (const ex of evidence ?? []) {
    if (!ex.id) fail('every excerpt needs an id')
    if (ids.has(ex.id)) fail(`duplicate excerpt id ${ex.id}`)
    ids.add(ex.id)
    if (typeof ex.text !== 'string' || ex.text.trim() === '') {
      fail(`${ex.id}: excerpt text is empty`)
      continue
    }
    // The whole point of the ledger: every excerpt is verbatim page-3 text.
    if (!page.includes(norm(ex.text))) fail(`${ex.id}: excerpt is not verbatim page-3 text`)
  }

  const labels = artifact.labels ?? {}
  for (const group of LABEL_GROUPS) {
    const value = labels[group]
    if (!value || typeof value !== 'object') {
      fail(`labels.${group} is missing`)
      continue
    }
    if (Object.keys(value).length === 0) fail(`labels.${group} is empty`)
    const round = JSON.parse(JSON.stringify(value))
    if (JSON.stringify(round) !== JSON.stringify(value)) {
      fail(`labels.${group} does not survive a stringify/parse round trip`)
    }
  }
  for (const extra of Object.keys(labels)) {
    if (!LABEL_GROUPS.includes(extra)) fail(`labels.${extra} is not one of the four label groups`)
  }

  const used = new Set()
  for (const ref of collectRefs(labels)) {
    if (ref.id === null) {
      fail(ref.reason)
      continue
    }
    if (!ids.has(ref.id)) fail(`dangling source reference ${ref.id}`)
    else used.add(ref.id)
  }
  for (const id of ids) if (!used.has(id)) fail(`excerpt ${id} is never used by a label`)

  const events = labels.key_events?.events
  if (!Array.isArray(events) || events.length === 0) fail('key_events.events is empty')

  const detection = labels.expected_signal_detection
  if (detection?.classification?.verdict !== 'common_mode') {
    fail('expected_signal_detection must classify the event as common_mode')
  }
  if (!detection?.must_not_classify_as?.some((x) => x.verdict === 'independent_trips')) {
    fail('expected_signal_detection must rule out independent_trips')
  }

  const actions = labels.expected_next_action?.required_actions ?? []
  for (const required of ['manage_system_strength', 'direct_fast_start_units', 'investigate_shared_dependency']) {
    if (!actions.some((a) => a.action === required)) fail(`expected_next_action is missing ${required}`)
  }
  if (!labels.expected_next_action?.prohibited_actions?.length) {
    fail('expected_next_action must list prohibited actions')
  }

  const analysis = labels.expected_analysis
  const claims = (analysis?.must_include ?? []).map((c) => c.claim)
  for (const required of ['chronology', 'impact', 'common_cause', 'restoration']) {
    if (!claims.includes(required)) fail(`expected_analysis is missing the ${required} claim`)
  }
  const forbidden = (analysis?.must_not_claim ?? []).map((c) => c.claim)
  for (const required of ['customer_load_lost', 'transmission_fault_caused_the_trips']) {
    if (!forbidden.includes(required)) fail(`expected_analysis must prohibit ${required}`)
  }

  return failures
}

const raw = readFileSync(ARTIFACT, 'utf8')
const pageText = readFileSync(PAGE_TEXT, 'utf8')
const artifact = JSON.parse(raw)

if (process.argv.includes('--self-test')) {
  let bad = 0

  const tampered = JSON.parse(raw)
  tampered.evidence[6].text = 'At 1334.29 hrs, YWPS unit 4 tripped after a transmission line fault.'
  const a = validate(tampered, pageText)
  const caughtExcerpt = a.some((m) => m.includes('not verbatim'))
  console.log(`self-test 1 non-verbatim excerpt: ${caughtExcerpt ? 'REFUSED' : 'NOT REFUSED'}`)
  a.forEach((m) => console.log(`  - ${m}`))
  if (!caughtExcerpt) bad++

  const dangling = JSON.parse(raw)
  dangling.labels.expected_analysis.must_include[0].source_refs = ['P3-EVENT-999']
  const b = validate(dangling, pageText)
  const caughtRef = b.some((m) => m.includes('dangling source reference P3-EVENT-999'))
  console.log(`self-test 2 dangling source reference: ${caughtRef ? 'REFUSED' : 'NOT REFUSED'}`)
  b.forEach((m) => console.log(`  - ${m}`))
  if (!caughtRef) bad++

  const clean = validate(artifact, pageText)
  console.log(`self-test 3 unmodified artifact: ${clean.length === 0 ? 'ACCEPTED' : 'REJECTED'}`)
  clean.forEach((m) => console.log(`  - ${m}`))
  if (clean.length !== 0) bad++

  process.exit(bad === 0 ? 0 : 1)
}

const failures = validate(artifact, pageText)
if (failures.length > 0) {
  console.error(`validate: ${failures.length} failure(s)`)
  failures.forEach((m) => console.error(`  - ${m}`))
  process.exit(1)
}
console.log(
  `validate: OK — ${artifact.evidence.length} verbatim page-3 excerpts, ` +
    `${LABEL_GROUPS.length} label groups, every source reference resolves.`,
)
