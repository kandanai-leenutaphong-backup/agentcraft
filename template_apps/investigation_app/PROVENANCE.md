# Source Snapshot

Copied 2026-09-15 from the current working tree of `/home/hanchoong/perth_cyber`.
Source HEAD: `4bf04d86fd42175791ecfd45c97cea3ebcc4c4a0`.

[SOURCE.sha256](SOURCE.sha256) records the original runtime snapshot (358 files, 3,020,815 bytes)
and the subsequently copied Search test-fixture dependency, before adaptation.
These are working-tree hashes, not a claim that HEAD contained every
copied byte. Source changes to the component README and optimization frontend tests were
preserved in the copy; the source repository was not edited.

Included: CyberEye backend, frontend, control configuration and tests; its retained runtime
components and tests; the ontology contract. Excluded: Git/harness metadata, raw and prepared
datasets, credentials and environment files, saved agents/experiments, generated output,
dependencies, cloud deployment scripts, telemetry-processing pipelines and unrelated styling demos.
The Search publishing package was added because existing retrieval tests import its public
`build_document`; no publishing operation ran. The copied Dockerfile and requirements were
retired because they do not describe the template's new dependency/build boundary.

The template is an independent consumer of Agentcraft libraries, not an import of the source
checkout. Reusing existing data and cloud targets for local tests does not transfer ownership
of those resources. Authored state belongs under this template's ignored local directories.

Component provenance and notices remain beside their source. Copying does not establish new
third-party distribution rights; the retained Copilot terminal and GUIDE data have unresolved
license records. Do not publish data, private state, or a derived distribution without review.