#!/usr/bin/env node
// Browser acceptance for the rendered /dataset-prep page.
//
// Run it from `doc_app/demo/app/frontend` so `createRequire` rooted at the working
// directory finds the Playwright already installed there. Nothing is added to
// any manifest.
//
//   cd doc_app/demo/app/frontend
//   node ../../../dataset_prep/scripts/verify-rendered.mjs http://127.0.0.1:5179/dataset-prep

import { createRequire } from 'node:module'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join, resolve } from 'node:path'
import { deepStrictEqual } from 'node:assert'

const url = process.argv[2]
if (!url) {
  console.error('usage: node verify-rendered.mjs <url>')
  process.exit(2)
}

const require = createRequire(join(resolve(process.cwd()), 'package.json'))
let chromium
try {
  ;({ chromium } = require('playwright'))
} catch {
  ;({ chromium } = require('@playwright/test'))
}

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const artifact = JSON.parse(
  readFileSync(join(root, 'artifacts', 'yallourn-w-2025-10-16.case.json'), 'utf8'),
)
const GROUPS = ['key_events', 'expected_signal_detection', 'expected_next_action', 'expected_analysis']

const failures = []
const fail = (msg) => {
  failures.push(msg)
  console.error(`FAIL  ${msg}`)
}
const pass = (msg) => console.log(`ok    ${msg}`)

const browser = await chromium.launch()

async function inspect(name, width, height) {
  const context = await browser.newContext({ viewport: { width, height } })
  const page = await context.newPage()
  const response = await page.goto(url, { waitUntil: 'networkidle' })
  if (!response || !response.ok()) {
    fail(`${name}: page did not load (${response?.status() ?? 'no response'})`)
    await context.close()
    return
  }

  const regions = await page.$$eval('[data-dataset-json]', (nodes) =>
    nodes.map((n) => ({ key: n.getAttribute('data-dataset-json'), text: n.textContent ?? '' })),
  )
  if (regions.length !== GROUPS.length) {
    fail(`${name}: expected ${GROUPS.length} JSON regions, found ${regions.length}`)
  }
  if (regions.map((r) => r.key).join(',') !== GROUPS.join(',')) {
    fail(`${name}: JSON regions are ${regions.map((r) => r.key).join(', ')}, expected document order`)
  }

  const renderedRefs = new Set()
  for (const region of regions) {
    const expected = artifact.labels[region.key]
    if (!expected) {
      fail(`${name}: rendered region ${region.key} has no matching artifact object`)
      continue
    }
    let parsed
    try {
      parsed = JSON.parse(region.text)
    } catch (err) {
      fail(`${name}: ${region.key} visible text is not valid JSON (${err.message})`)
      continue
    }
    try {
      deepStrictEqual(parsed, expected)
      pass(`${name}: ${region.key} matches the artifact (${region.text.length} visible chars)`)
    } catch {
      fail(`${name}: ${region.key} differs from the artifact object`)
      continue
    }
    const walk = (node) => {
      if (Array.isArray(node)) node.forEach(walk)
      else if (node && typeof node === 'object') {
        for (const [k, v] of Object.entries(node)) {
          if (k === 'source_refs' && Array.isArray(v)) v.forEach((id) => renderedRefs.add(String(id)))
          else walk(v)
        }
      }
    }
    walk(parsed)
  }

  const renderedExcerpts = await page.$$eval('[data-source-id]', (nodes) =>
    nodes.map((n) => ({ id: n.getAttribute('data-source-id'), text: n.textContent ?? '' })),
  )
  const excerptIds = new Set(renderedExcerpts.map((e) => e.id))
  const dangling = [...renderedRefs].filter((id) => !excerptIds.has(id))
  if (dangling.length > 0) fail(`${name}: rendered source refs do not resolve: ${dangling.join(', ')}`)
  else pass(`${name}: all ${renderedRefs.size} rendered source refs resolve to ${excerptIds.size} excerpts`)

  const byId = new Map(artifact.evidence.map((e) => [e.id, e.text]))
  const normalize = (s) => s.replace(/[\s\u00a0]+/g, ' ').trim()
  const wrong = renderedExcerpts.filter((e) => !normalize(e.text).includes(normalize(byId.get(e.id) ?? '\u0000')))
  if (wrong.length > 0) fail(`${name}: excerpt text truncated or altered: ${wrong.map((w) => w.id).join(', ')}`)
  else pass(`${name}: every rendered excerpt shows its full verbatim text`)

  const overflow = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    client: document.documentElement.clientWidth,
  }))
  if (overflow.scroll > overflow.client + 1) {
    fail(`${name}: page scrolls horizontally (${overflow.scroll} > ${overflow.client})`)
  } else {
    pass(`${name}: no horizontal page overflow (${overflow.scroll}px)`)
  }

  const pdfHref = await page.getAttribute('a[href$=".pdf"]', 'href')
  if (!pdfHref) fail(`${name}: no full-report PDF link`)
  else {
    const head = await context.request.get(new URL(pdfHref, url).toString())
    if (!head.ok()) fail(`${name}: full-report link ${pdfHref} returned ${head.status()}`)
    else pass(`${name}: full-report link resolves (${pdfHref})`)
  }

  const navLinks = await page.$$('nav[aria-label="Dataset labels"] a')
  if (navLinks.length !== GROUPS.length) fail(`${name}: expected ${GROUPS.length} anchor links, found ${navLinks.length}`)
  else pass(`${name}: semantic anchor nav has ${navLinks.length} links`)

  if (navLinks.length > 0) {
    await navLinks[0].focus()
    const focus = await page.evaluate(() => {
      const el = document.activeElement
      if (!el) return null
      const s = getComputedStyle(el)
      return { outline: s.outlineStyle, width: s.outlineWidth, shadow: s.boxShadow }
    })
    const visible =
      focus && ((focus.outline !== 'none' && parseFloat(focus.width) > 0) || (focus.shadow && focus.shadow !== 'none'))
    if (visible) pass(`${name}: focused anchor has a visible focus indicator`)
    else fail(`${name}: focused anchor has no visible focus indicator (${JSON.stringify(focus)})`)
  }

  const shot = `/tmp/dataset-prep-${name}.png`
  await page.screenshot({ path: shot, fullPage: true })
  console.log(`shot  ${shot}`)
  await context.close()
}

await inspect('desktop-1440x900', 1440, 900)
await inspect('mobile-390x844', 390, 844)
await browser.close()

if (failures.length > 0) {
  console.error(`verify-rendered: ${failures.length} failure(s)`)
  process.exit(1)
}
console.log('verify-rendered: OK')
