#!/usr/bin/env node
// Copies the dataset-prep artifact and source assets into the Vocs tree.
// `--check` compares SHA-256 digests instead of writing, so drift fails a gate
// rather than being silently rebuilt at deploy time.

import { createHash } from 'node:crypto'
import { copyFileSync, mkdirSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..')
const prep = join(root, 'dataset_prep')

const COPIES = [
  {
    from: join(prep, 'artifacts', 'yallourn-w-2025-10-16.case.json'),
    to: join(root, 'docs', 'data', 'yallourn-w-2025-10-16.case.json'),
  },
  {
    from: join(prep, 'source', 'trip-of-yallourn-w-power-station-unit-3-and-unit-4.pdf'),
    to: join(root, 'docs', 'public', 'dataset-prep', 'trip-of-yallourn-w-power-station-unit-3-and-unit-4.pdf'),
  },
  {
    from: join(prep, 'source', 'yallourn-report-page-3.png'),
    to: join(root, 'docs', 'public', 'dataset-prep', 'yallourn-report-page-3.png'),
  },
  {
    from: join(prep, 'source', 'yallourn-report-page-3.txt'),
    to: join(root, 'docs', 'public', 'dataset-prep', 'yallourn-report-page-3.txt'),
  },
]

const digest = (path) => createHash('sha256').update(readFileSync(path)).digest('hex')
const rel = (path) => path.slice(root.length + 1)

const check = process.argv.includes('--check')
let drift = 0

for (const { from, to } of COPIES) {
  const source = digest(from)
  let target = null
  try {
    target = digest(to)
  } catch {
    target = null
  }

  if (check) {
    if (target === source) {
      console.log(`ok    ${rel(to)}  ${source.slice(0, 12)}`)
    } else {
      console.error(`DRIFT ${rel(to)}  expected ${source.slice(0, 12)}, found ${target?.slice(0, 12) ?? 'missing'}`)
      drift++
    }
    continue
  }

  if (target === source) {
    console.log(`same  ${rel(to)}`)
    continue
  }
  mkdirSync(dirname(to), { recursive: true })
  copyFileSync(from, to)
  console.log(`wrote ${rel(to)}  ${source.slice(0, 12)}`)
}

if (check && drift > 0) {
  console.error(`sync --check: ${drift} file(s) out of date. Run: node doc_app/dataset_prep/scripts/sync.mjs`)
  process.exit(1)
}
console.log(check ? 'sync --check: OK' : 'sync: done')
