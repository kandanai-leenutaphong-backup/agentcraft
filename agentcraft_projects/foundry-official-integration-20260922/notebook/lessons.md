```json
{
  "constitution": {
    "revision": 1,
    "sha256": "0a7e39fe0b4a62588b24b1f975fd61c1cb42b80ec35a6d1d263bd39c6575e1c8",
    "scope": "Migration context; F00 predates this authority."
  },
  "authoritative_records": [
    "[execute-remediation-v1](../records/v2/20260922T154739145740Z-execute-remediation-v1/record.json)",
    "[f01-uv-dependency-checkpoint](../records/v2/20260922T163403830370Z-f01-uv-dependency-checkpoint/record.json)",
    "[f02-f07-local-checkpoint](../records/v2/20260922T174652824471Z-f02-f07-local-checkpoint/record.json)"
  ],
  "cells": [
    {
      "cell_type": "markdown",
      "metadata": {"id": "f00-package-inventory", "language": "markdown"},
      "source": [
        "## 2026-09-23 | F00 | Inventory must match imported packages\n",
        "- Attribution/evidence: [F00 worker handoff](../../../deploy/remediation-evidence/20260922T151500Z-f00/handoff.json), environment.\n",
        "- Observation: default uv inventory listed zero packages; default check exited 0 after checking zero, despite actual user-site imports and ten base requirement conflicts.\n",
        "- Lesson: bind inventory/checks to the explicit existing target and interpreter; verify import origins and precedence. Empty successful checks do not establish dependency health.\n",
        "- Confidence: supported by supplied F00 evidence; no environment recheck performed for this note."
      ]
    },
    {
      "cell_type": "markdown",
      "metadata": {"id": "f01-complete-profiles", "language": "markdown"},
      "source": [
        "## 2026-09-23 | F01 | Pin complete profiles without repairing unrelated consumers\n",
        "- Attribution/evidence: [F01 worker handoff](../../../deploy/remediation-evidence/20260922T154800Z-f01/handoff.json), package_decisions, profiles and gaps.\n",
        "- Observation: complete H/E 98-package and O 99-package profiles reproduced offline using source-pinned local wheels; inspected imports matched wheels. Shared pre-existing conflicts remained.\n",
        "- Observation: only actual package addition was setuptools 80.9.0. Host installation refused six system-package shadows pending exact recovery review; current imports already satisfied locks.\n",
        "- Lesson: pin full dependency closure and source wheels. Preserve unrelated shared conflicts; require exact recovery review before user-site installs shadow system packages. Scoped closure is not globally healthy dependency state or verified restoration.\n",
        "- Confidence: supported by supplied F01 evidence; live build and recovery remain unverified."
      ]
    },
    {
      "cell_type": "markdown",
      "metadata": {"id": "f00-f01-local-not-live", "language": "markdown"},
      "source": [
        "## 2026-09-23 | F00/F01 | Local checks do not establish live parity\n",
        "- Attribution/evidence: F00 worker handoff baseline and execute-remediation-v1; F01 counts supplied by assigning overseer, with test receipts linked in F01 worker handoff and authoritative f01-uv-dependency-checkpoint above.\n",
        "- Observation: H/E/O local checks passed 21/18/20 at F00 and 25/18/22 at F01. F00 ran owning offline functions, not normal shell receipt wrappers. F01 was a local dependency checkpoint; F08 image build and live acceptance were not executed.\n",
        "- Lesson: these counts establish neither improvement nor live parity. Require changed-artifact live observations before claiming preserved H/E/O outcomes; historical victories do not validate changed artifacts.\n",
        "- Confidence: evidence supports local scope only. Unknown: changed-artifact live parity. These lessons certify neither archival completeness nor restoration."
      ]
    },
    {
      "cell_type": "markdown",
      "metadata": {"id": "overseer-same-path-writes", "language": "markdown"},
      "source": [
        "## 2026-09-23 | Overseer discovery | Serialize same-path draft writes\n",
        "- Attribution: overseer observation supplied in this assignment.\n",
        "- Observation: concurrent apply_patch additions to the same draft concatenated YAML; repaired before authoritative publication.\n",
        "- Lesson: one writer per path; serialize same-path additions and validate repaired drafts before publication.\n",
        "- Confidence: attributed report, not independently reproduced. Unknown: draft path and primary incident receipt. Do not conflate this YAML incident with the separate script syntax failure reported in F01."
      ]
    },
    {
      "cell_type": "markdown",
      "metadata": {"id": "f02-f07-contracts-and-parity", "language": "markdown"},
      "source": [
        "## 2026-09-23 | F02-F07 | Validate contracts separately from completion and parity\n",
        "- Constitution: revision 1, sha256 0a7e39fe0b4a62588b24b1f975fd61c1cb42b80ec35a6d1d263bd39c6575e1c8.\n",
        "- Attribution: F02-F07 worker evidence; authoritative [f02-f07-local-checkpoint](../records/v2/20260922T174652824471Z-f02-f07-local-checkpoint/record.json), run_id null. Worker clock r-20260922T163534Z identifies local work only, per [acceptance addendum](../../../deploy/remediation-evidence/20260922T163453Z-f02-f07/acceptance-addendum.json). Hypothesis: strict agreement adapters and native SDK lifecycle preserve workflows while removing manual authenticated transports; live preservation remains unknown.\n",
        "- Grader discovery: [before/after proof](../../../deploy/remediation-evidence/20260922T163453Z-f02-f07/before-after-regression-proof.json) records nested correct label 0 -> 1 and sample=None AttributeError -> 1. [Retained tests](../../../deploy/remediation-evidence/20260922T163453Z-f02-f07/recovery-after/testbeds/foundry-agent%20optimization/tests/test_live.py) distinguish sample argument None from malformed item.sample=None. Supported paths include sample.output_text, item.response, item['sample.output_text'], and item.sample.output_text; multiple supplied values must agree. Whitespace is stripped for label comparison; wrong/invalid/null/non-string predictions score 0. Missing response mapping, missing/invalid ground truth, malformed envelopes and conflicting paths raise ValueError. Mapping failures must not masquerade as prediction errors.\n",
        "- Result rejection: same proof records conflicting output previously silently choosing direct output, now ValueError; Boolean score previously accepted, now refused. Retained tests also refuse non-finite scores, foreign run/criterion identity, changed evaluator version, failed/skipped/error rows, duplicate or missing rows. A completed row with score 0 and passed=false remains valid evidence: output completion is distinct from semantic acceptance. Preserve failures; never infer acceptance from terminal status.\n",
        "- Native job parity: [handoff](../../../deploy/remediation-evidence/20260922T163453Z-f02-f07/handoff.json) reports three candidate identities, metrics and evaluation links matched for opt_21aee306b2db4bebb7eb89a07d9c1f8d. This read-only result does not prove separately retrieved configuration or new submission/config application. C01 retained bounded config GET because public load_config lacks timeout/retry controls and strips local instruction whitespace. Loader-compatible resolver route is not a verified public REST contract; payload refusal occurs after SDK buffering.\n",
        "- Public types are not validators: handoff records E request TypedDicts mistakenly treated as Azure models, caught by focused serialization testing and corrected. Retained config tests exercise rejection of malformed fields and unsupported skills/model/tool changes. Use each public constructor correctly; keep explicit agreement and authorization checks. Native optimizer evaluator references expose no public data_mapping field; explicit Evals mapping does not establish native-envelope service compatibility.\n",
        "- Conditional retention: [C03/C05/C08 decisions](../../../deploy/remediation-evidence/20260922T163453Z-f02-f07/conditional-decisions.json) retain ResponsesAgentServerHost because AgentBinding exposes no public native-agent accessor; JSON-text tool proof remains, without native structured tool output or public adapter. Containers remain because no deployment-mode or ZIP identity contract was selected, despite CodeConfiguration presence. Host-owned instrumentation and derived metric exports remain; no existing custom span implementation was removed and no new correlation requirement introduced.\n",
        "- Validation/metric retention: C06 retains direct SDK independent validation because service-target row/config/stored-readback equivalence is unestablished; no holdout upload. C07 retains versioned Python exact-label grading and frozen macro-F1 because native string-check mapping/error/whitespace parity is unestablished. Replacement requires contract equivalence, not merely a public type or API.\n",
        "- Confidence/limits: supplied local evidence supports these discoveries; no rerun for this note. H/E/O offline counts 34/24/35 do not establish changed-artifact live parity. F08 new evaluator schema/mapping, H version creation/inference, E builtin version, O submit/config application, image build, live auth/readback and rollback remain unverified. Worker local objective completion is not mission acceptance. Checkpoint coverage remains partial; these lessons certify neither archival completeness nor restoration."
      ]
    },
    {
      "cell_type": "markdown",
      "metadata": {"id": "f08-live-identities", "language": "markdown"},
      "source": [
        "## 2026-09-23 | F08 | Reconcile live identities without overstating coverage\n",
        "- Constitution: revision 1, sha256 0a7e39fe0b4a62588b24b1f975fd61c1cb42b80ec35a6d1d263bd39c6575e1c8. Attribution: F08 worker [handoff](../../../deploy/remediation-evidence/20260922T174900Z-f08/handoff.json) and non-authoritative [publication input](../../../deploy/remediation-evidence/20260922T174900Z-f08/publication-input.json). Final authoritative F08 record pending; no mission-acceptance or archival-completeness claim. Question: does official SDK lifecycle plus narrow agreement normalization preserve the protected live workflows?\n",
        "- Metadata/readback: H persisted metadata null became {}; exact empty normalization repaired stored readback without inference replay. Evaluator registration preserved executable code/schema while service omitted SDK threshold and added empty defaults; reconcile existing version rather than recreate it. E catalogue list/get timestamps differed; E/O criterion IDs/null fields required narrow normalization. Lesson: distinguish documented observational differences from executable identity mismatch; do not broadly relax comparisons or replay inference to repair readback. Both grader canaries returned scores [1,0,0]; [E verification](../../../testbeds/foundry-agent-evaluation/deploy/records/migration-e-v1/20260922T181808468298Z-verify.json), run evalrun_a8607771d7de41abb6ea91cfa71923f1, retained 3/3 passing rows.\n",
        "- Native candidate behavior: migration-o-v1/v2 settled baseline-only after perfect-score/two-stall outcomes; retain both as failed candidate-coverage attempts, not optimization victories. migration-o-v3 job opt_4d8f98325041438aa3fa24dd54050bd4 returned three native candidates: baseline _0000 plus generated _0001/_0002, not three generated candidates. Count actual native membership and retain candidate/config/evaluation identities; completion alone does not guarantee generated-candidate coverage. [Native recomputed metrics](../../../testbeds/foundry-agent%20optimization/deploy/evidence/migration-o-v3/migration-o-v3-recomputed-metrics.json) and [candidate validation](../../../testbeds/foundry-agent%20optimization/deploy/evidence/migration-o-v3/candidate-validation-metrics.json) link service candidates to deployed versions 3/4/5 and stored responses.\n",
        "- Quality boundary: nine direct-SDK validation rows were three shared synthetic development fixtures per candidate; accuracy 0, 2/3, 1 and macro-F1 0, 0.5555555555555555, 1 are integration observations, not independent held-out validation or quality generalization. Shared development labels preclude improvement claims. Historical generated 28/30 versus native baseline 29/30 regression remains unchanged; no held-out read, rerun or upload.\n",
        "- Cancellation: [H receipt](../../../testbeds/foundry-hosted-agents/deploy/records/migration-h-v1/20260922T185121107291Z-invoke.json), response caresp_00822c302ad694af00JxeLGPPpovfUyUUaoXdaX1Eg06xsZI5c, and [O receipt](../../../testbeds/foundry-agent%20optimization/deploy/evidence/migration-o-v1/20260922T184643240858Z-runtime-canary.json), response caresp_03e5f04806272b9800EgYR0NEkTxS0QRWFaLToqGr3Tz3HK5MP, show terminal cancelled with no completed output. H v2 missed the completion window; deferred public TextResponse enabled v3 cancellation. Missed attempts remain terminal completed. Task/client cleanup has local handler-test evidence only; bounded provider logs hit event limit/read timeout and yielded no cleanup marker. Terminal cancellation does not prove remote cleanup or hard-kill durability.\n",
        "- Unknown-build reconciliation: actual initial H build returned null stdout; existing ACR run crf was reconciled using retained archive/tag/digest, never resubmitted. [C04 evidence](../../../deploy/remediation-evidence/20260922T174900Z-f08/acceptance-matrix.json) distinguishes this live recovery from mocked dropped-response/concurrency guards. Lesson: reconcile the original side effect before retry; do not associate submission by inventory difference. No deliberately dropped production write or unrelated concurrent billable build was tested.\n",
        "- Settlement boundary: worker [live settlement](../../../deploy/remediation-evidence/20260922T174900Z-f08/20260922T191008048851Z-settlement-live.json) and publication input report zero pending operations and eight protected/final versions matched; H nonce-tool checks covered three tools with anonymous 401 refusal. Foreign-owner guard is caller-side only, not a live foreign-principal credential test. Archive member-byte verification is not active-tree restoration; no cloud rollback, hard-kill durability proof or teardown. Ongoing resource cost, provider cost and token usage remain unknown; command capture is partial.\n",
        "- Confidence: supported by supplied worker evidence, not independently rerun or digest-verified for this note. Supersedes only the pending-live-evidence portions of F00/F01 | Local checks do not establish live parity and F02-F07 | Validate contracts separately from completion and parity, for the named F08 observations; earlier local findings and failures remain. Next: overseer authoritative publication; no new experiment implied."
      ]
    },
    {
      "cell_type": "markdown",
      "metadata": {"language": "markdown"},
      "source": [
        "## 2026-09-23 | F09 | Bind acceptance to live identities and corrected measurements\n",
        "- Constitution: revision 1, sha256 0a7e39fe0b4a62588b24b1f975fd61c1cb42b80ec35a6d1d263bd39c6575e1c8. Attribution: gap worker [acceptance addendum](../../../deploy/remediation-evidence/20260922T193935Z-acceptance-gaps/acceptance-addendum.json), [result input](../../../deploy/remediation-evidence/20260922T193935Z-acceptance-gaps/result-input.json), and overseer authoritative [f09-migration-accepted](../records/v2/20260922T200128628556Z-f09-migration-accepted/record.json), run official-integration-final; supplied record sha256 9b170b406f631d275efb89cfb4ae71df241561b17706c7fe51eb2680c02d6416.\n",
        "- Concurrency: local guards did not satisfy the original live gate. Bounded actual builds crm/crn overlapped 43.349496 seconds; direct run/context/tag/digest binding proved build identity. Reuse prior dropped-result recovery separately; neither local tests nor inventory differences substitute for live identity evidence.\n",
        "- Final target: changed host version requires E target rebinding. migration-e-final-h-v3 pinned H version 3, source and configuration; evalrun_e56c2dc6860e4cd1975d7e92f0a2bd8b passed 3/3 rows and three oracle checks. Earlier-version evaluation alone cannot accept the final host.\n",
        "- Measurement correction: count Docker install sites, not only Python AST sites. Corrected dependency-install count: 3, all uv. Same 19 production files grew from 3501 to 4372 lines; no net reduction. Keep corrected scope and prior measurements visible.\n",
        "- Supersedes: current pending-publication status in F08 | Reconcile live identities without overstating coverage, including its next-publication step, and the addendum/result-input F09-pending observations. Those remain historical. F09 is now published and migration accepted; recorded verdict improved applies only to integration correctness/operational migration, not prediction quality. Historical 28/30 versus 29/30 regression remains; holdout unchanged and not rerun.\n",
        "- Confidence/limits: supported by supplied evidence and authoritative record content; no independent live rerun or digest verification for this note. C09 live downstream closure/no-dispatch, restoration and cloud rollback remain unverified; costs/tokens unknown. No archival-completeness claim or new experiment implied."
      ]
    }
  ]
}
```