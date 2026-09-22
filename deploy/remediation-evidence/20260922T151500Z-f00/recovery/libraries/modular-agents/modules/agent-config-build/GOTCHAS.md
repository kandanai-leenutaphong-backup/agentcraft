# GOTCHAS.md — agent-config-build

Failures that cost real time. Symptom first, because that is how you will
arrive here.

---

## G1 — A tool silently never loaded

**Symptom.** An agent behaves as if a tool does not exist. It never calls it,
never mentions it, and gives a plausible answer from memory instead. No error
anywhere. The config clearly lists the tool.

**Cause.** The resolver caught the `ImportError` or `AttributeError` and
continued. A typo in the module path, a renamed function, or a dependency
missing in the deployed image all present identically: the agent ships with a
shorter tool list than its author believes.

**Fix.** `resolve_tools` defaults to `on_missing="raise"`, which fails the
build. Keep it that way. `on_missing="skip"` exists for best-effort callers and
should never be the default in a runtime path.

**Rule.** A capability that silently disappears is worse than a crash: the
agent invents an answer instead of failing, and the output looks fine.

---

## G2 — Config could import any module on the box

**Symptom.** Nothing visible. This is a latent authorisation hole, not a bug
report.

**Cause.** `module.path:function` specs resolve through `importlib`. Without an
allowlist, anyone who can edit a YAML file can execute any importable module in
the process, including anything that runs work at import time.

**Fix.** The allowlist defaults to the empty tuple. Nothing resolves until the
consumer declares a prefix, so the insecure state is unreachable by omission.
Declare the narrowest prefix that covers your tool package.

**Rule.** Config is code when it names code. Fail closed, and make the safe
default the one you get by doing nothing.

---

## G3 — An agent booted with no system prompt

**Symptom.** An agent answers generically, ignores its persona, and behaves
like a bare model. Its prompt file is right there in the repo.

**Cause.** A path typo, a moved file, or a rename left the `instructions` entry
pointing at nothing. Concatenating an empty list yields an empty string, which
is a valid system prompt, so nothing objected.

**Fix.** `PromptLoadError` when a non-empty `instructions` list resolves to no
text. An empty file counts as unresolved, since a stale entry must not silently
strip the prompt. An explicitly empty list stays legal for tool-only agents.

**Rule.** Distinguish "the caller specified nothing" from "the caller specified
things and none of them worked". Only the second is an error.

---

## G4 — Fragment-level keys are parsed and discarded

**Symptom.** A `roles:` or `features:` block sits in a fragment, is valid YAML,
and never reaches the runtime. Reads of it return empty. No warning.

**Cause.** The merge lifts only `agents:` and `tool_display_names:` out of a
fragment. Everything else is read and dropped.

**Fix.** Put consumer config where it survives:

1. **Inside an agent definition** — arrives on `AgentSpec.extra`. Best for
   per-agent metadata.
2. **Top-level in the base file** — readable via `load_agent_config()`. Best
   for global settings.
3. **Read the fragment yourself** with `yaml.safe_load(<fragment path>)`. Best
   for per-use-case blocks that must live beside their roster.

`scripts/validate_config.py` warns for every dropped fragment key.

**Rule.** A merge that silently narrows its input needs a linter, because the
loss is invisible at the point where someone writes the file.

---

## G5 — A duplicate agent id shadows the original

**Symptom.** An agent behaves like a different agent. Its prompt and tools do
not match its definition. Usually after copy-pasting a fragment.

**Cause.** Two fragments define the same id. A last-write-wins merge would make
one definition invisible with no signal.

**Fix.** Duplicate ids raise `ValueError` naming the offending fragment, at load
time.

**Rule.** In a merged namespace, collisions must be loud. Silent precedence is
only acceptable where an override is the documented intent.

---

## G6 — Renaming an agent id breaks saved sessions

**Symptom.** Saved conversations, evaluation runs, or external clients start
returning `AgentNotFound` after a tidy-up rename.

**Cause.** The agent id is a public identifier. Anything that persisted a
reference to it holds a dangling pointer.

**Fix.** Keep the old id as an alias sharing the prompt and tool list via a YAML
anchor, and mark it `surface: hidden` so it disappears from pickers but keeps
resolving:

```yaml
  researcher:
    tools: &researcher_tools
      - my_tools.notes:search_notes
  assistant:                 # legacy id
    surface: hidden
    instructions: [demo/researcher.md]
    tools: *researcher_tools
```

**Rule.** Anchors make an alias provably identical. Copy-pasting the tool list
makes it identical only until someone edits one copy.

---

## G7 — Edited YAML did not take effect

**Symptom.** A prompt or config edit changes nothing. Restarting fixes it.

**Cause.** The merged config is cached in module state. In a long-running
process, or in a test that writes YAML and immediately reloads, the cache is
still serving the previous parse.

**Fix.** Call `invalidate_config_cache()` after any programmatic write. The
cache key spans the base file and every fragment's mtime, so ordinary editing
during development invalidates correctly; the failure mode is writes made
inside the same process.

---

## G8 — Config edits did not ship with the deployment

**Symptom.** A prompt or roster change works locally and has no effect on the
deployed service. The deployment reported success.

**Cause.** Prompt files and YAML are usually baked into the container image at
build time. A deploy mode that only updates environment variables leaves the
old image, and therefore the old prompts, in place.

**Fix.** Any change under the control tree needs a full image build and deploy,
not a config-only update. Verify by reading a prompt back through a running
endpoint rather than trusting the deploy log.

**Rule.** Know which of your artifacts are baked and which are mounted. The
distinction is invisible in the source tree and decides which deploy path is
correct.

---

## G9 — Foundation prompt edits have blast radius

**Symptom.** Every agent's behaviour shifts after a one-line edit to a shared
prompt. Regressions appear in agents nobody touched.

**Cause.** `foundation_prompts` is prepended verbatim to every agent. That is
the feature: it is how cross-cutting rules propagate without duplication. It is
also why a careless edit is a roster-wide change.

**Fix.** Keep foundation text to rules that are genuinely universal. Anything
conditional belongs in a per-agent prompt. Re-run your evaluation suite across
the whole roster after a foundation edit, not just the agent you had in mind.

---

## G10 — A tool parameter type annotation broke every chat

**Symptom.** Every request to one agent fails at agent-build time, before any
tool is called. An endpoint that merely imports the same tool module works fine.

**Cause.** Some SDKs build a schema from the tool signature by resolving type
hints. A module-level type alias used as a parameter annotation cannot be
resolved by the schema builder, so building the agent throws rather than
calling anything.

**Fix.** Inline parameter annotations. Do not alias an annotated tool-parameter
type at module scope.

**Diagnose cheaply.** `typing.get_type_hints(fn, include_extras=True)` on the
tool function, or ask the SDK to produce the tool's JSON schema. Both reproduce
it without deploying.

**Rule.** Tool signatures are a schema surface, not just a Python signature.
Anything that changes how a signature is introspected is a breaking change.
