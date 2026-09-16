# Python Function Binding Evidence

Source: https://learn.microsoft.com/en-us/azure/azure-functions/functions-reference-python?pivots=python-mode-configuration

Observed 2026-09-16 through the editor's public `fetch_webpage` tool. Page title: Python developer
reference for Azure Functions. Returned source revision: MicrosoftDocs/azure-docs-pr commit
`1a48602ec3642c208cab5511d31eff670cf17e32`, page updated 2026-06-15. This note is an authored summary,
not a byte-identical archived page. No retrieved-byte hash is claimed.

Verified documentation facts:

- Python supports the decorator-based model and configuration-based model.
- Configuration-based functions declare each HTTP trigger/output in `function.json` beside Python code.
- `scriptFile` and `entryPoint` identify the Python implementation; binding names identify handler parameters.
- A local build can package dependencies rather than requesting a remote requirements install.

Experiment evidence:

- [Decorator package check](../records/20260916T061127464724Z-package-check.json) indexed locally.
- [Native deployment/runtime diagnostic](../records/20260916T062705308239Z-runtime-diagnostic.json)
  reported a completed deployment and empty live function list. Exact underlying host cause remains unknown.
- The final package uses five explicit configuration bindings, including three named method routes, all
  calling one shared handler. [Live acceptance](../records/20260916T065843550937Z-acceptance.json)
  proves authenticated execution, matching refusals and six complete provider result readbacks.

The adaptation changes only Function registration. It does not disable auth, change the native extraction
API, run a local provider SDK, or claim that the decorator model is generally unsupported.