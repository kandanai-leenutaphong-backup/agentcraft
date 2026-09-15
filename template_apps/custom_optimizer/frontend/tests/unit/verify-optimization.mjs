// The measurement layer of the optimization trajectory, on its own terms.
//
// The rule these tests hold to is the one the specification is strictest about: a score
// exists only where the scorer produced it. Nothing pending, running, failed or cancelled
// may reach the chart, and no absent number may render as a zero.
import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import ts from "typescript";
import { loadModule } from "../support/transpile.mjs";
import { assertDetectorLineage, assertMeasuredBaseline } from "../support/optimization-acceptance.mjs";

const trajectory = await loadModule("../../../app/components/agent_optimization/frontend/trajectory.ts", import.meta.url);
const {
  MISSING, baselineOf, baselineReady, buildPlot, diffAgainstParent, failingCases, formatMs,
  formatPercent, formatScore, groupTools, isRunning, macroF1, measured, medianMs,
} = trajectory;

const BOX = { width: 600, height: 200, left: 50, right: 10, top: 10, bottom: 30 };

function metrics(macro, median = 100) {
  return {
    macro_f1: macro, accuracy: macro, median_ms: median, p95_ms: median * 2, elapsed_ms: median * 10,
    error_rate: 0, case_count: 20, per_class: {}, validation_macro_f1: macro, development_macro_f1: macro,
  };
}

function version(number, overrides = {}) {
  return {
    version: number, name: `candidate ${number}`, parent_version: number === 1 ? null : number - 1,
    system_prompt: "grade the alert", model: "gpt-4.1", tool_ids: [`tool@${number}`],
    created_at: "2026-09-10T00:00:00Z", status: "completed", rationale: "", origin: number === 1 ? "baseline" : "copilot-cli",
    metrics: metrics(0.5), evaluations: [], ...overrides,
  };
}

test("staged baseline counts every error without requiring a selected error-free rerun", () => {
  const measured = { status: "completed", cases_finished: 3, started_at: "2024-01-01", completed_at: "2024-01-02",
    metrics: {case_count:3,macro_f1:0.2,error_rate:1/3,confusion_matrix:{accept:{accept:1,reject:0,Error:1},reject:{accept:0,reject:1,Error:0}},per_class:{accept:{support:2},reject:{support:1}}}};
  const baseline = {status:"completed",training_runs:[measured],evaluations:[{...structuredClone(measured),started_at:"2024-01-03"}]};
  const experiment = {stage_counts:{training:3,evaluation:3},versions:[baseline]};
  assert.doesNotThrow(() => assertMeasuredBaseline(experiment));
  baseline.evaluations[0].metrics.error_rate = 0;
  assert.throws(() => assertMeasuredBaseline(experiment));
  baseline.evaluations[0].metrics.error_rate = 1/3;
  baseline.evaluations[0].cases_finished = 2;
  assert.throws(() => assertMeasuredBaseline(experiment));
});

test("detector lineage permits replacing baseline rules with new revision-one rules", () => {
  const baseline = { version: 1, parent_version: null, rules: [{ id: "window_shape", digest: "shape", revision: 1 }] };
  const successor = { version: 2, parent_version: 1, rules: [{ id: "technique_role_time", digest: "specificity", revision: 1 }] };
  assert.doesNotThrow(() => assertDetectorLineage([baseline, successor]));
  successor.rules[0].revision = 2;
  assert.throws(() => assertDetectorLineage([baseline, successor]), /Rule technique_role_time revision/);
});

test("detector lineage requires exact parent-relative revisions and rejects unknown parents", () => {
  const baseline = { version: 1, parent_version: null, rules: [{ id: "window_shape", digest: "shape", revision: 1 }] };
  const successor = { version: 2, parent_version: 1, rules: [{ id: "window_shape", digest: "changed", revision: 2 }] };
  const reused = { version: 3, parent_version: 2, rules: structuredClone(successor.rules) };
  assert.doesNotThrow(() => assertDetectorLineage([reused, successor, baseline]));
  successor.rules[0].revision = 1;
  assert.throws(() => assertDetectorLineage([baseline, successor]), /Rule window_shape revision/);
  successor.rules[0].revision = 3;
  assert.throws(() => assertDetectorLineage([baseline, successor]), /Rule window_shape revision/);
  successor.rules[0].revision = 2;
  successor.parent_version = 99;
  assert.throws(() => assertDetectorLineage([baseline, successor]), /parent must precede/);
});

test("detector version labels alone do not prove tuning but ruleset changes do", () => {
  const baseline = { version: 1, parent_version: null, configuration: { version: "first", max_window_seconds: 600 },
    rules: [{ id: "window_shape", digest: "shape", revision: 1 }] };
  const successor = { ...structuredClone(baseline), version: 2, parent_version: 1 };
  successor.configuration.version = "second";
  assert.throws(() => assertDetectorLineage([baseline, successor]), /not only its version label/);
  successor.rules[0].revision = 2;
  assert.throws(() => assertDetectorLineage([baseline, successor]), /Rule window_shape revision/);
  successor.rules[0].revision = 1;
  successor.configuration.max_window_seconds = 300;
  assert.doesNotThrow(() => assertDetectorLineage([baseline, successor]));
});

test("only measured candidates become points", () => {
  const versions = [
    version(1, { metrics: metrics(0.4) }),
    version(2, { status: "failed", metrics: null }),
    version(3, { status: "running", metrics: null }),
    version(4, { metrics: metrics(0.6) }),
  ];
  assert.deepEqual(measured(versions).map((entry) => entry.version), [1, 4]);
  const plot = buildPlot(versions, macroF1, BOX);
  assert.deepEqual(plot.points.map((point) => point.version), [1, 4]);
  assert.equal(plot.points.some((point) => point.value === 0), false);
});

test("a higher score plots above a lower one, inside the box", () => {
  const plot = buildPlot([version(1, { metrics: metrics(0.4) }), version(2, { metrics: metrics(0.9) })], macroF1, BOX);
  const [first, second] = plot.points;
  assert.ok(second.y < first.y, "the better candidate must sit higher");
  assert.equal(first.x, BOX.left);
  assert.equal(second.x, BOX.width - BOX.right);
  for (const point of plot.points) {
    assert.ok(point.y >= BOX.top && point.y <= BOX.height - BOX.bottom, "point escaped the plot box");
  }
  assert.ok(plot.min < 0.4 && plot.max > 0.9);
});

test("a single measured candidate does not divide by zero", () => {
  const plot = buildPlot([version(1, { metrics: metrics(0.75) })], macroF1, BOX);
  assert.equal(plot.points.length, 1);
  assert.ok(Number.isFinite(plot.points[0].x) && Number.isFinite(plot.points[0].y));
  assert.ok(plot.max > plot.min);
});

test("a flat series still separates its ticks", () => {
  const plot = buildPlot([version(1, { metrics: metrics(0.5) }), version(2, { metrics: metrics(0.5) })], macroF1, BOX);
  assert.ok(plot.max > plot.min);
  assert.equal(plot.points.length, 2);
});

test("no measurement renders as an em dash, never as zero", () => {
  assert.equal(formatScore(null), MISSING);
  assert.equal(formatScore(undefined), MISSING);
  assert.equal(formatScore(Number.NaN), MISSING);
  assert.equal(formatScore(0), "0.000");
  assert.equal(formatMs(null), MISSING);
  assert.equal(formatMs(1234.6), "1235 ms");
  assert.equal(formatPercent(null), MISSING);
  assert.equal(formatPercent(0.125), "12.5%");
});

test("latency is picked from the same measured record as quality", () => {
  const plot = buildPlot([version(1, { metrics: metrics(0.4, 300) }), version(2, { metrics: metrics(0.9, 120) })], medianMs, BOX);
  assert.deepEqual(plot.points.map((point) => point.value), [300, 120]);
});

test("full protocol separates stages and waits for both before plotting overall latency", () => {
  const source = readFileSync(new URL("../../../app/components/agent_optimization/frontend/PerformanceView.tsx", import.meta.url), "utf8");
  const compiled = ts.transpileModule(source, { compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS } }).outputText;
  const compiledModule = { exports: {} };
  const jsx = (type, props) => ({ type, props });
  const requireStub = (name) => name === "react/jsx-runtime" ? { jsx, jsxs: jsx, Fragment: "fragment" }
    : name === "./TrajectoryChart" ? { TrajectoryChart: "chart" }
    : name === "./trajectory" ? { ...trajectory, versionAssessment: () => ({}) } : {};
  new Function("require", "module", "exports", compiled)(requireStub, compiledModule, compiledModule.exports);
  const training = metrics(0.6);
  const evaluation = metrics(0.4);
  const candidate = version(2, { training_metrics: training, evaluation_metrics: null, mean_latency_ms: 120 });
  const render = () => compiledModule.exports.PerformanceView({ experiment: { protocol: "full-10", versions: [candidate] }, selected: 2, onSelect() {} });
  const chartGroup = () => render().props.children.find(child => child?.props?.children?.[0]?.type === "chart").props.children;
  let charts = chartGroup();
  assert.deepEqual(charts.map(chart => chart.props.title), ["Training macro-F1", "Evaluation macro-F1", "Average case latency"]);
  assert.equal(charts[0].props.versions[0].metrics, training);
  assert.equal(charts[1].props.versions[0].metrics, null);
  assert.equal(charts[2].props.versions[0].metrics, null);
  candidate.evaluation_metrics = evaluation;
  charts = chartGroup();
  assert.equal(charts[1].props.versions[0].metrics, evaluation);
  assert.equal(charts[2].props.versions[0].metrics.mean_ms, 120);
});

test("the optimize action waits for a measured baseline", () => {
  const pending = { versions: [version(1, { status: "running", metrics: null })] };
  assert.equal(baselineReady(pending), false);
  assert.equal(baselineReady(null), false);
  assert.equal(baselineReady({ versions: [version(1)] }), true);
  assert.equal(baselineOf({ versions: [version(2), version(1)] }).version, 1);
  assert.equal(isRunning({ status: "baseline_running" }), true);
  assert.equal(isRunning({ status: "completed" }), false);
});

test("creative mode is an explicit API flag and preserves default callers", async () => {
  const source = readFileSync(new URL("../../../app/components/agent_optimization/frontend/api.ts", import.meta.url), "utf8");
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
  const compiledModule = { exports: {} };
  new Function("require", "module", "exports", compiled)(() => ({ createContext: () => null }), compiledModule, compiledModule.exports);
  const requests = [];
  const api = compiledModule.exports.createOptimizationApi(async (path, options) => { requests.push({ path, body: JSON.parse(options.body) }); return {}; }, "/owned");
  await api.createExperiment("Creative", "joint-10", true, true);
  await api.createExperiment("Existing", "joint-10", true);
  await api.createExperiment("Twelve", "joint-12", true, true);
  assert.deepEqual(requests, [
    {path:"/owned/experiments",body:{name:"Creative",protocol:"joint-10",workflow:true,creative:true}},
    {path:"/owned/experiments",body:{name:"Existing",protocol:"joint-10",workflow:true,creative:false}},
    {path:"/owned/experiments",body:{name:"Twelve",protocol:"joint-12",workflow:true,creative:true}},
  ]);
});

test("creative profiles expose questions, alternatives and separate code and agent changes", () => {
  const source = readFileSync(new URL("../../../app/components/agent_optimization/frontend/views.tsx", import.meta.url), "utf8");
  const compiled = ts.transpileModule(source, { compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS } }).outputText;
  const compiledModule = { exports: {} };
  const jsx = (type, props) => ({ type, props });
  const requireStub = name => name === "react/jsx-runtime" ? {jsx,jsxs:jsx,Fragment:"fragment"}
    : name === "./trajectory" ? trajectory : {SourceCodeViewer:"source",MessagesSquare:"icon"};
  new Function("require", "module", "exports", compiled)(requireStub, compiledModule, compiledModule.exports);
  const candidate = version(2, {process_contract:{version:"fixture"}, design_audit:{
    hypothesis:"Inspect different evidence views.", observed_gaps:[], changes:[], expected_tradeoffs:[],
    experiment:{approach_id:"temporal_first",kind:"new-evidence",mechanism:"Compare event order.",alternatives:["Reliability-first strategy","Support-first strategy"],disconfirmation:"Ordering adds no distinguishing evidence."},
    investigation_plan:{version:"question-evidence-tools-v1",questions:[{id:"timeline",question:"What happened first?",data:"event_time",view:"Ordered timeline",tool:"timeline",status:"tool",decision:"Distinguish sequences",limits:"Not causal proof"}],
      code_changes:["Add temporal query"],agent_changes:["Interpret timeline"],held_fixed:["Model and detector"],acceptance_checks:["Contrast two timelines"]},
  }});
  const render = () => JSON.stringify(compiledModule.exports.VersionsView({experiment:{agent_id:"fixture",stage_counts:{training:2,evaluation:1},versions:[version(1),candidate]},version:candidate,tools:[],onInspect(){}}));
  for (const text of ["Creative experiment design","Question and evidence plan","What happened first?","Reliability-first strategy","Code changes","Add temporal query","Agent changes","Interpret timeline","Held fixed","Disconfirmation"]) assert.ok(render().includes(text),text);
  delete candidate.design_audit;
  assert.equal(render().includes("Question and evidence plan"),false);
});

test("a candidate's diff names what changed against its parent", () => {
  const parent = version(1);
  const child = version(2, { model: "gpt-4.1-mini", tool_ids: ["tool@1", "tool@2"], system_prompt: "grade the alert carefully" });
  const rows = diffAgainstParent(child, [parent, child]);
  assert.deepEqual(rows.map((row) => [row.field, row.changed]), [["Model", true], ["Tool versions", true], ["System prompt", true]]);
  const unchanged = diffAgainstParent(version(2), [parent, version(2)]);
  assert.deepEqual(unchanged.map((row) => row.changed), [false, true, false]);
  const baseline = diffAgainstParent(parent, [parent]);
  assert.deepEqual(baseline.map((row) => [row.before, row.changed]), [[MISSING, false], [MISSING, false], [MISSING, false]]);
});

test("failing cases come from the newest evaluation, errors included", () => {
  const evaluated = version(2, { evaluations: [
    { id: "e1", status: "completed", started_at: "", metrics: null, cases: [{ case_id: "old", correct: false }] },
    { id: "e2", status: "completed", started_at: "", metrics: null, cases: [
      { case_id: "a", split: "development", expected: "TruePositive", predicted: "FalsePositive", correct: false, elapsed_ms: 10, rationale: "" },
      { case_id: "b", split: "development", expected: "BenignPositive", predicted: "BenignPositive", correct: true, elapsed_ms: 10, rationale: "" },
      { case_id: "c", split: "development", expected: "FalsePositive", predicted: null, correct: true, elapsed_ms: 10, rationale: "", error: "timeout" },
    ] },
  ] });
  assert.deepEqual(failingCases(evaluated).map((item) => item.case_id), ["a", "c"]);
  assert.deepEqual(failingCases(null), []);
  assert.deepEqual(failingCases(version(1)), []);
});

test("tool versions group by name, newest first", () => {
  const groups = groupTools([
    { name: "grade_counts", version: 1 }, { name: "alert_join", version: 2 },
    { name: "grade_counts", version: 3 }, { name: "alert_join", version: 1 },
  ]);
  assert.deepEqual(groups.map((group) => [group.name, group.versions.map((entry) => entry.version)]),
    [["alert_join", [2, 1]], ["grade_counts", [3, 1]]]);
});

test("visible tools use ascending creation time rather than alphabetical or tool-version grouping", () => {
  const tools = [{ id: "b", created_at: "2026-09-10T02:00:00Z" }, { id: "z", created_at: "2026-09-10T01:00:00Z" }];
  assert.deepEqual(trajectory.chronologicalTools(tools).map((tool) => tool.id), ["z", "b"]);
});

test("each divider reaches zero on either side with no minimum width", () => {
  for (let index = 0; index < 3; index++) {
    const initial = [18, 23, 28, 31];
    assert.equal(trajectory.resizePair(initial, index, -1000)[index], 0);
    assert.equal(trajectory.resizePair(initial, index, 1000)[index + 1], 0);
    assert.equal(trajectory.resizePair(initial, index, 1000).reduce((sum, width) => sum + width), 100);
  }
});

test("all columns collapse and any one can be restored", () => {
  let widths = [18, 23, 28, 31];
  for (let index = 0; index < 4; index++) widths = trajectory.toggleColumn(widths, index);
  assert.deepEqual(widths, [0, 0, 0, 0]);
  assert.deepEqual(trajectory.toggleColumn(widths, 2), [0, 0, 100, 0]);
});

test("progress summaries are grounded in validation cases and retain regressions", () => {
  const candidate = version(2, { validation_metrics: { ...metrics(0.5), per_class: {
    TruePositive: { precision: 1, recall: 1, f1: 1, support: 5, fn: 0 },
    FalsePositive: { precision: 0, recall: 0, f1: 0, support: 5, fn: 5 },
  } }, evaluations: [{ comparison: { reason: "Quality regressed against v1." } }] });
  const assessment = trajectory.versionAssessment(candidate);
  assert.match(assessment.strength, /TruePositive/);
  assert.match(assessment.weakness, /5 missed/);
  assert.match(assessment.comparison, /regressed/);
  assert.match(trajectory.versionAssessment(version(3)).strength, /No validation result/);
});
