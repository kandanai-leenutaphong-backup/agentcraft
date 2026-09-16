# Integration Gotchas

These ids belong to the super-skill. Each preserved module keeps its own original
GOTCHAS document and numbering. No historical cloud measurement is re-certified
by this migration's offline tests.

## G1 - The Two agentconfig Packages Are Not Interchangeable

**Symptom:** A runtime expects `agentconfig.dataplane` or `agentconfig.document`
but imports the YAML roster package instead.

**Cause:** The source canvas configuration component and the reference roster
loader share a Python package name but have different contracts.

**Resolution:** Install this skill in its own environment. The hosted bridge
uses the YAML loader and explicit tool packages; it intentionally excludes the
canvas package. Verified by the extracted-bundle import checks.

## G2 - A Local Agent Factory Does Not Deploy A Hosted Agent

**Symptom:** `foundryagent.build_agent` returns an SDK object, but nothing runs
as a custom hosted source bundle.

**Cause:** Client-side MAF construction and Foundry hosted deployment are
different APIs.

**Resolution:** Pass the same `AgentSpec` through `hostedagents`, build the flat
zip and run the authorized deployment sequence. Preserve the two tool marker
names when using the MAF factory. The offline example exercises both consumers.

## G3 - A Tool Passes Locally But Cannot Be Packaged

**Symptom:** Packaging refuses a nested function, absent source package,
signature/spec disagreement, credential parameter or interactive approval.

**Cause:** A callable object is not necessarily a portable headless contract.

**Resolution:** Put typed functions in a real package, declare its source,
match ToolSpec defaults to Python defaults and inject credentials at the edge.
Do not erase approval requirements to make a build pass. Definition tests pin
these refusals before execution.

## G4 - Reusing A Loader Accidentally Reuses Its Import Grant

**Symptom:** A later configuration load imports tools despite an omitted
allowlist.

**Cause:** The preserved loader has process-global defaults. Its convenience
`configure` only changes some defaults when non-empty values are supplied.

**Resolution:** Use `load_definition`, which explicitly resets the allowlist,
default id and caches while holding its composition lock. The regression loads
a granted roster, then proves an ungranted load is refused.

## G5 - A 201 Or Healthy Container Is Not A Completed Feature

**Symptom:** Upload succeeds but runtime startup, model access or data access
still fails.

**Cause:** Upload, remote build, authenticated invocation, inference permission
and data permissions are separate observations.

**Resolution:** Verify the exact version, runtime source digest, configuration
and grants, then perform the authorized live tool/model probe. Offline mocks and
health never claim inference success. Cold-start retries do not retry 403 as
though it were readiness delay.

## G6 - Maintenance Calls Can Claim A Consumer Session

**Symptom:** A consumer's session returns an ownership refusal after deployment
warming used the same session name under another identity.

**Cause:** The source hosted protocol records identity-bound sessions; a header
named `agent_session_id` is not the routing parameter.

**Resolution:** Use `session_key` with separate consumer and maintenance purposes,
and put it in the invocation query. Namespace separation and request shape are
offline-tested; current live cross-identity behavior still needs verification.

## G7 - Interrupted Deployment Must Not Blindly Repeat Mutation

**Symptom:** A retry would create another version or forget a grant whose PUT
succeeded before its read-back failed.

**Cause:** An HTTP failure does not prove that the remote mutation did not occur.

**Resolution:** Retain receipts. Uploading without a recorded version stops for
reconciliation. Grant intent is saved before mutation; failed read-back leaves
an owned cleanup record. Teardown verifies revocation before deleting identity.
The recovery tests reproduce both boundaries with injected failures.

## G8 - Cancel Does Not Undo A Synchronous Backend

**Symptom:** A caller sees cancellation while a blocking tool thread continues.

**Cause:** Python task cancellation cannot forcibly stop an already-running
thread or reverse effects it committed.

**Resolution:** Use async/cooperative backends with finite timeouts and bounded
effects. Do not grant mutation merely because a function is callable. Async
model cancellation and owner-only abort are verified; arbitrary backend rollback
is not provided.

## G9 - A Zip Checksum Alone Does Not Identify The Running Source

**Symptom:** A deployment receipt names one build but runtime inspection proves
only the same model/configuration values.

**Cause:** Equal configuration does not imply equal tool implementation.

**Resolution:** Runtime startup verifies the source manifest and health reports
its digest. The deployment verifier compares that digest to the receipt. A
modified tool source fails readiness in the portability regression.