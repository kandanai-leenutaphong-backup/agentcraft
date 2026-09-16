// Post-build fixups the Vocs config cannot do:
//   1. Delete the plaintext whole-site dumps (llms.generateMarkdown:false does
//      not suppress them).
//   2. Inject the identity script (config `head` does not emit into prerendered
//      HTML in this version).

import { readdir, readFile, rm, writeFile } from 'node:fs/promises'
import { join, sep } from 'node:path'

const dist = new URL('../docs/dist/', import.meta.url).pathname
const TAG = '<script src="/identity.js" defer></script>'

async function htmlFiles(dir) {
  const out = []
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name)
    if (entry.isDirectory()) out.push(...(await htmlFiles(path)))
    else if (entry.name.endsWith('.html')) out.push(path)
  }
  return out
}

let removed = 0
for (const name of ['llms.txt', 'llms-full.txt']) {
  try {
    await rm(join(dist, name))
    removed++
  } catch {
    // already absent
  }
}

const SOURCES = `${sep}architecture${sep}sources${sep}`

let injected = 0
for (const file of await htmlFiles(dist)) {
  // The staged demo is a separate app; it must not get the site's sidebar dock.
  if (file.includes(`${sep}demo${sep}`)) continue
  // Preserved originals must stay byte-identical to their recorded hashes.
  if (file.includes(SOURCES)) continue
  const html = await readFile(file, 'utf8')
  if (html.includes(TAG)) continue
  await writeFile(file, html.replace('</head>', `${TAG}</head>`))
  injected++
}

console.log(`postbuild: removed ${removed} llms dump(s), injected identity script into ${injected} page(s)`)
