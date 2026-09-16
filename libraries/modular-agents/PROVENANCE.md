# Provenance

Source moved from the former `modular-agents` skill. Configuration and tool-shaping
modules retain their source contracts, tests, examples and notices. Hosted definitions,
immutable bundle construction and invocation ownership were retained; raw model
orchestration was replaced by canonical `llm_interface` calls.

[Original composition provenance](provenance/skill-origin.md) is historical, not the
current installation/deployment contract. [Retired runtime guidance](provenance/retired-foundryagent/README.md)
preserves hard-won native findings; its executable `foundryagent` package is not shipped.
[LICENSE](LICENSE) is the unchanged MIT source notice. Dependencies and host-authored
tools/configurations retain their own terms; no additional rights are implied.

[MIGRATION.json](MIGRATION.json) records frozen source hashes, moves and retirement.
Old generated source bundles, editable skill implementations, independent locks and
administration engines are not current releases. New bundles and distributions are
generated from canonical sources only. Customer data, host checkpoints and `.local`
records are not cleanup candidates.