import assert from "node:assert/strict";
import { isDeepStrictEqual } from "node:util";

export function assertDetectorLineage(detectors) {
  assert.ok(detectors.length >= 2);
  const history = new Map();
  let changed = false;
  for (const detector of [...detectors].sort((left, right) => left.version - right.version)) {
    assert.ok(Number.isInteger(detector.version) && detector.version > 0 && !history.has(detector.version));
    const parent = history.get(detector.parent_version);
    if (history.size === 0) assert.equal(detector.parent_version, null);
    else assert.ok(parent, "Detector parent must precede its child");
    const previous = new Map((parent?.rules ?? []).map(rule => [rule.id, rule]));
    assert.ok(detector.rules.length > 0);
    assert.equal(new Set(detector.rules.map(rule => rule.id)).size, detector.rules.length);
    for (const rule of detector.rules) {
      assert.ok(typeof rule.digest === "string" && rule.digest.length > 0);
      const old = previous.get(rule.id);
      assert.equal(rule.revision, old ? old.revision + Number(old.digest !== rule.digest) : 1,
        `Rule ${rule.id} revision must follow its identity in the detector parent`);
    }
    if (parent) {
      const currentConfiguration = structuredClone(detector.configuration ?? {});
      const previousConfiguration = structuredClone(parent.configuration ?? {});
      delete currentConfiguration.version;
      delete previousConfiguration.version;
      changed ||= !isDeepStrictEqual(currentConfiguration, previousConfiguration)
        || detector.rules.length !== parent.rules.length
        || detector.rules.some(rule => previous.get(rule.id)?.digest !== rule.digest);
    }
    history.set(detector.version, detector);
  }
  assert.ok(changed, "Detector history must change a ruleset, not only its version label");
}

export function assertMeasuredBaseline(experiment) {
  const baseline = experiment.versions[0];
  assert.equal(baseline.status, "completed");
  if (!experiment.stage_counts) {
    assert.equal(baseline.metrics.error_rate, 0);
    return;
  }
  for (const [stage, key] of [["training", "training_runs"], ["evaluation", "evaluations"]]) {
    const run = baseline[key].at(-1);
    const total = experiment.stage_counts[stage];
    assert.equal(run.status, "completed");
    assert.equal(run.cases_finished, total);
    assert.equal(run.metrics.case_count, total);
    assert.ok(Number.isFinite(run.metrics.macro_f1));
    const matrix = Object.values(run.metrics.confusion_matrix);
    assert.equal(matrix.reduce((sum, row) => sum + Object.values(row).reduce((count, value) => count + value, 0), 0), total);
    const errors = matrix.reduce((sum, row) => sum + (row.Error ?? 0), 0);
    assert.equal(run.metrics.error_rate, errors / total);
    assert.equal(Object.values(run.metrics.per_class).reduce((sum, item) => sum + item.support, 0), total);
  }
  assert.ok(baseline.training_runs.at(-1).completed_at <= baseline.evaluations.at(-1).started_at);
}