---
name: azure-sky-styling
description: "Use when the requested design is Azure Sky: scoped CSS tokens, typography, textured blue/light materials, reusable depth effects and seeded distant architecture. Includes the original React and plain-HTML galleries, local assets/notices and browser/pixel tests. Use only when this visual direction fits the host; synthetic demo data is not production capability."
---

# Azure Sky Styling

The complete [design and reuse contract](README.md), scoped CSS, React gallery, plain HTML,
depth-effect recipes, local fonts/artwork notices, generation scripts and tests are included.
No live application, authentication, dataset or cloud configuration is imported.

Consume CSS under `.azure-sky`, or opt-in depth classes from the separate stylesheet. Import
the declared npm package public exports rather than copying individual rules into consumers.
Preserve existing application design unless Azure Sky is the requested theme. Demo save/export
behaviors are local synthetic fixtures; production service APIs remain host-owned.

Resolve `SKILL_ROOT` from the loaded file. Copy the whole capability into an external working
directory, run `npm ci`, `npm run build`, then the documented verification commands. Dependency
and screenshot output must not be installed in the shared plugin directory. The gallery can be
served on a free loopback port using its existing Vite commands. All publisher notices travel
with assets; no external artwork or font service is contacted at runtime.