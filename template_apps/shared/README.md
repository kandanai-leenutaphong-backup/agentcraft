# Template Foundations

One source owner for the retained `situation_detector`, `azure_llm`, `azure_search` and
`source_code` capabilities used by Investigation and Custom Optimizer. Moved from the
investigation template during optimizer separation; these are not new library implementations.

Python consumers install `agentcraft-template-foundations` through an explicit local uv
dependency and import the public `template_foundations.<capability>` package.
Frontend consumers resolve `@foundations/source_code/frontend` to its public barrel.
No foundation imports either application or reads its configuration.

Optimizer-only workflow, sandbox reader and terminal code live in Custom Optimizer.
Other investigation-only components remain with Investigation. This package is a local
ownership boundary, not a published distribution or an additional universal utility layer.

`local_server.serve` also owns the identical loopback process/port/shutdown mechanics; each
app still owns which settings it accepts, which module it launches and where state belongs.
Inherited component documentation is source history. Current consumers resolve installed
`template_foundations` imports and the declared frontend alias, never the retired app paths.