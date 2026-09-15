/**
 * Generic KQL-fragment -> plain-English transformer.
 *
 * Every phrase here is produced by inspecting the shape of a fragment the backend
 * parsed out of a rule's own query, or a value the executed query returned. There is
 * deliberately no rule_id lookup and no per-rule prose: an unrecognised fragment falls
 * through to its original text rather than being dropped or rewritten.
 */

import type { FactorObserved, RuleExplanation, RuleObservation } from "../../shared/types";

const IDENTIFIER = /^[A-Za-z_][A-Za-z0-9_]*$/;
const TIMESPAN = /^(\d+)(ms|s|m|h|d)$/;
const TIME_FIELD = /(^|_)(time|timestamp|datetime|date)$/i;
const UNITS: Record<string, string> = { ms: "millisecond", s: "second", m: "minute", h: "hour", d: "day" };

/** Walk a fragment, reporting only positions at paren depth zero and outside string literals. */
function scanSplit(text: string, breakWidth: (source: string, index: number) => number): string[] {
  const parts: string[] = [];
  let depth = 0;
  let quote = "";
  let verbatim = false;
  let start = 0;
  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    if (quote) {
      if (!verbatim && character === "\\") { index += 1; continue; }
      if (character === quote) quote = "";
      continue;
    }
    if (character === '"' || character === "'") {
      quote = character;
      verbatim = index > 0 && text[index - 1] === "@";
      continue;
    }
    if (character === "(" || character === "[") { depth += 1; continue; }
    if (character === ")" || character === "]") { depth -= 1; continue; }
    if (depth > 0) continue;
    const width = breakWidth(text, index);
    if (width > 0) {
      parts.push(text.slice(start, index));
      start = index + width;
      index += width - 1;
    }
  }
  parts.push(text.slice(start));
  return parts.map((part) => part.trim()).filter((part) => part.length > 0);
}

function isBalanced(text: string): boolean {
  let depth = 0;
  let quote = "";
  let verbatim = false;
  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    if (quote) {
      if (!verbatim && character === "\\") { index += 1; continue; }
      if (character === quote) quote = "";
      continue;
    }
    if (character === '"' || character === "'") {
      quote = character;
      verbatim = index > 0 && text[index - 1] === "@";
      continue;
    }
    if (character === "(" || character === "[") depth += 1;
    else if (character === ")" || character === "]") {
      depth -= 1;
      if (depth < 0) return false;
    }
  }
  return depth === 0 && quote === "";
}

export function splitTopLevelCommas(text: string): string[] {
  return scanSplit(text, (source, index) => (source[index] === "," ? 1 : 0));
}

function splitTopLevelKeyword(text: string, keyword: string): string[] {
  const needle = ` ${keyword} `;
  return scanSplit(text, (source, index) =>
    source.slice(index, index + needle.length).toLowerCase() === needle ? needle.length : 0);
}

function splitTopLevelOperator(text: string, operator: string): string[] | null {
  const parts = scanSplit(text, (source, index) => {
    if (source.slice(index, index + operator.length) !== operator) return 0;
    if (operator === "=" || operator === ">" || operator === "<") {
      const next = source[index + operator.length] ?? "";
      const previous = source[index - 1] ?? "";
      if (next === "=" || next === "~" || "!<>=~".includes(previous)) return 0;
    }
    return operator.length;
  });
  return parts.length === 2 ? parts : null;
}

function stripOuterParens(text: string): string {
  let value = text.trim();
  while (value.startsWith("(") && value.endsWith(")") && isBalanced(value.slice(1, -1))) {
    value = value.slice(1, -1).trim();
  }
  return value;
}

function unquote(token: string): string | null {
  const trimmed = token.trim();
  const verbatim = trimmed.startsWith("@");
  const text = verbatim ? trimmed.slice(1) : trimmed;
  const first = text[0];
  if (text.length < 2 || (first !== '"' && first !== "'")) return null;
  for (let index = 1; index < text.length; index += 1) {
    const character = text[index];
    if (!verbatim && character === "\\") { index += 1; continue; }
    if (character === first) return index === text.length - 1 ? text.slice(1, -1) : null;
  }
  return null;
}

function callParts(text: string): { name: string; args: string[] } | null {
  const match = /^([A-Za-z_][A-Za-z0-9_]*)\s*\(([\s\S]*)\)$/.exec(text.trim());
  if (!match || !isBalanced(match[2])) return null;
  return { name: match[1].toLowerCase(), args: splitTopLevelCommas(match[2]) };
}

/** Field names read better as words; anything non-identifier is left exactly as written. */
export function fieldLabel(token: string): string {
  const text = token.trim();
  return IDENTIFIER.test(text) ? text.replace(/_/g, " ") : text;
}

function joinAny(values: string[]): string {
  if (values.length <= 1) return values.join("");
  return `${values.slice(0, -1).join(", ")} or ${values[values.length - 1]}`;
}

function joinAll(values: string[]): string {
  if (values.length <= 1) return values.join("");
  return `${values.slice(0, -1).join(", ")} and ${values[values.length - 1]}`;
}

function plural(count: number, word: string): string {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

function humanizeTimespan(token: string): string | null {
  const match = TIMESPAN.exec(token.trim());
  if (!match) return null;
  const amount = Number(match[1]);
  return `${amount === 1 ? "one" : amount}-${UNITS[match[2]]}`;
}

/** A value-producing expression rendered as a readable noun phrase. */
export function humanizeValue(fragment: string): string {
  const text = stripOuterParens(fragment);
  if (!text) return "";
  const literal = unquote(text);
  if (literal !== null) return literal === "" ? "an empty string" : literal;
  if (text.toLowerCase() === "null") return "no value";
  if (IDENTIFIER.test(text)) return fieldLabel(text);

  const call = callParts(text);
  if (!call) return text;
  const [first, second, third] = call.args;
  switch (call.name) {
    case "tolower": case "toupper": case "tostring": case "tolong": case "toint":
    case "todouble": case "toreal": case "todatetime": case "toguid": case "tobool":
      return humanizeValue(first ?? "");
    case "long": case "int": case "real": case "double":
      return call.args.length === 1 && first.trim().toLowerCase() === "null" ? "no value" : text;
    case "coalesce":
      return call.args.length > 1
        ? `the first present value among ${joinAll(call.args.map(humanizeValue))}`
        : humanizeValue(first ?? "");
    case "extract":
      return third
        ? `text pulled from ${humanizeValue(third)} using the pattern ${humanizeValue(first)}`
        : text;
    case "bin": case "bin_at": {
      const span = humanizeTimespan(second ?? "");
      return span ? `${span} buckets of ${humanizeValue(first)}` : text;
    }
    case "iff": case "iif":
      return third !== undefined
        ? `${humanizeValue(second)} when ${humanizeConditionText(first)}, otherwise ${humanizeValue(third)}`
        : text;
    case "prev":
      return `the previous record's ${humanizeValue(first ?? "")}`;
    case "next":
      return `the next record's ${humanizeValue(first ?? "")}`;
    case "datetime_diff": {
      const unit = unquote(first ?? "") ?? humanizeValue(first ?? "");
      return `${unit}s between ${humanizeValue(second)} and ${humanizeValue(third)}`;
    }
    case "count":
      return "number of matching records";
    case "countif":
      return `records where ${humanizeConditionText(first ?? "")}`;
    case "dcount": case "dcountif":
      return `distinct ${humanizeValue(first ?? "")} values`;
    case "min":
      return TIME_FIELD.test(first ?? "") ? `earliest ${humanizeValue(first)}` : `smallest ${humanizeValue(first ?? "")}`;
    case "max":
      return TIME_FIELD.test(first ?? "") ? `latest ${humanizeValue(first)}` : `largest ${humanizeValue(first ?? "")}`;
    case "sum": case "sumif":
      return `total ${humanizeValue(first ?? "")}`;
    case "avg": case "avgif":
      return `average ${humanizeValue(first ?? "")}`;
    case "any": case "take_any":
      return `one sampled ${humanizeValue(first ?? "")}`;
    case "make_list": case "make_set": case "make_list_if": case "make_set_if":
      return second
        ? `up to ${second.trim()} ${humanizeValue(first)} values kept as evidence`
        : `${humanizeValue(first ?? "")} values kept as evidence`;
    default:
      return text;
  }
}

const CONDITION_CALLS: Record<string, (args: string[]) => string> = {
  isnotempty: (args) => `${humanizeValue(args[0] ?? "")} is present`,
  isempty: (args) => `${humanizeValue(args[0] ?? "")} is empty`,
  isnotnull: (args) => `${humanizeValue(args[0] ?? "")} has a value`,
  isnull: (args) => `${humanizeValue(args[0] ?? "")} has no value`,
  not: (args) => `it is not true that ${humanizeConditionText(args[0] ?? "")}`,
};

/** Renderers take raw operands: list operators must not have their argument list pre-flattened. */
const WORD_OPERATORS: [string, (left: string, right: string) => string][] = [
  ["has_any", (left, right) => `${humanizeValue(left)} contains any of ${joinAny(listValues(right))}`],
  ["has_all", (left, right) => `${humanizeValue(left)} contains all of ${joinAll(listValues(right))}`],
  ["!has_cs", (left, right) => `${humanizeValue(left)} does not contain ${humanizeValue(right)}`],
  ["has_cs", (left, right) => `${humanizeValue(left)} contains ${humanizeValue(right)} (case-sensitive)`],
  ["!has", (left, right) => `${humanizeValue(left)} does not contain ${humanizeValue(right)}`],
  ["has", (left, right) => `${humanizeValue(left)} contains ${humanizeValue(right)}`],
  ["!contains", (left, right) => `${humanizeValue(left)} does not contain ${humanizeValue(right)}`],
  ["contains_cs", (left, right) => `${humanizeValue(left)} contains ${humanizeValue(right)} (case-sensitive)`],
  ["contains", (left, right) => `${humanizeValue(left)} contains ${humanizeValue(right)}`],
  ["!startswith", (left, right) => `${humanizeValue(left)} does not start with ${humanizeValue(right)}`],
  ["startswith", (left, right) => `${humanizeValue(left)} starts with ${humanizeValue(right)}`],
  ["!endswith", (left, right) => `${humanizeValue(left)} does not end with ${humanizeValue(right)}`],
  ["endswith", (left, right) => `${humanizeValue(left)} ends with ${humanizeValue(right)}`],
  ["!in~", (left, right) => `${humanizeValue(left)} is not one of ${joinAny(listValues(right))}`],
  ["in~", (left, right) => `${humanizeValue(left)} is one of ${joinAny(listValues(right))}`],
  ["!in", (left, right) => `${humanizeValue(left)} is not one of ${joinAny(listValues(right))}`],
  ["in", (left, right) => `${humanizeValue(left)} is one of ${joinAny(listValues(right))}`],
];

const SYMBOL_OPERATORS: [string, (left: string, right: string) => string][] = [
  ["=~", (left, right) => `${humanizeValue(left)} is ${humanizeValue(right)} (ignoring case)`],
  ["!~", (left, right) => `${humanizeValue(left)} is not ${humanizeValue(right)} (ignoring case)`],
  ["==", (left, right) => `${humanizeValue(left)} is ${humanizeValue(right)}`],
  ["!=", (left, right) => `${humanizeValue(left)} is not ${humanizeValue(right)}`],
  [">=", (left, right) => `${humanizeValue(left)} is at least ${humanizeValue(right)}`],
  ["<=", (left, right) => `${humanizeValue(left)} is at most ${humanizeValue(right)}`],
  [">", (left, right) => `${humanizeValue(left)} is more than ${humanizeValue(right)}`],
  ["<", (left, right) => `${humanizeValue(left)} is less than ${humanizeValue(right)}`],
];

function listValues(fragment: string): string[] {
  return splitTopLevelCommas(stripOuterParens(fragment)).map(humanizeValue);
}

function humanizeBetween(fragment: string): string | null {
  const negated = splitTopLevelKeyword(fragment, "!between");
  const parts = negated.length === 2 ? negated : splitTopLevelKeyword(fragment, "between");
  if (parts.length !== 2) return null;
  const bounds = scanSplit(stripOuterParens(parts[1]), (source, index) =>
    source.slice(index, index + 4) === " .. " ? 4 : 0);
  if (bounds.length !== 2) return null;
  const field = parts[0].trim();
  if (TIME_FIELD.test(field) && bounds[0] === "start" && bounds[1] === "end") {
    return "the record occurred inside the selected UTC window";
  }
  const verb = negated.length === 2 ? "is not between" : "is between";
  return `${humanizeValue(field)} ${verb} ${humanizeValue(bounds[0])} and ${humanizeValue(bounds[1])}`;
}

/** One comparison, membership test, or predicate function rendered as a clause. */
function humanizeAtom(fragment: string): string {
  const text = stripOuterParens(fragment);
  if (!text) return "";

  const between = humanizeBetween(text);
  if (between) return between;

  const regex = splitTopLevelKeyword(text, "matches regex");
  if (regex.length === 2) return `${humanizeValue(regex[0])} matches the pattern ${humanizeValue(regex[1])}`;

  for (const [keyword, render] of WORD_OPERATORS) {
    const parts = splitTopLevelKeyword(text, keyword);
    if (parts.length === 2) return render(parts[0], parts[1]);
  }
  for (const [operator, render] of SYMBOL_OPERATORS) {
    const parts = splitTopLevelOperator(text, operator);
    if (parts) return render(parts[0], parts[1]);
  }

  const call = callParts(text);
  const predicate = call && CONDITION_CALLS[call.name];
  if (call && predicate) return predicate(call.args);

  const value = humanizeValue(text);
  return value || text;
}

/** A whole boolean expression as one sentence, preserving and/or structure. */
export function humanizeConditionText(fragment: string): string {
  const orParts = splitTopLevelKeyword(fragment, "or");
  if (orParts.length > 1) return orParts.map(humanizeConditionText).join(", or ");
  const andParts = splitTopLevelKeyword(fragment, "and");
  if (andParts.length > 1) return andParts.map(humanizeConditionText).join(" and ");
  return humanizeAtom(fragment);
}

/** A boolean expression as separate readable bullets, one per top-level `and`. */
export function humanizeConditionLines(fragment: string): string[] {
  if (!fragment.trim()) return [];
  if (splitTopLevelKeyword(fragment, "or").length > 1) return [`either ${humanizeConditionText(fragment)}`];
  const andParts = splitTopLevelKeyword(fragment, "and");
  return (andParts.length > 1 ? andParts : [fragment]).map(humanizeConditionText);
}

function assignmentIndex(text: string): number {
  let found = -1;
  scanSplit(text, (source, index) => {
    if (found >= 0 || source[index] !== "=") return 0;
    const previous = source[index - 1] ?? "";
    const next = source[index + 1] ?? "";
    if ("!<>=~".includes(previous) || next === "=" || next === "~") return 0;
    found = index;
    return 0;
  });
  return found;
}

/** `alias=expr` becomes "alias — <humanized expr>"; a bare column stays a column. */
export function humanizeAssignment(fragment: string): string {
  const text = fragment.trim();
  const index = assignmentIndex(text);
  if (index < 0) return humanizeValue(text);
  const alias = fieldLabel(text.slice(0, index));
  const expression = humanizeValue(text.slice(index + 1));
  return expression && expression !== alias ? `${alias} — ${expression}` : alias;
}

export interface DerivedStep {
  key: string;
  title: string;
  lines: string[];
}

/** The rule's parsed query structure as an ordered plain-English narrative. */
export function narrativeSteps(explanation: RuleExplanation): DerivedStep[] {
  const steps: DerivedStep[] = [];
  const add = (key: string, title: string, lines: string[]) => {
    const kept = lines.filter((line) => line.trim().length > 0);
    if (kept.length) steps.push({ key, title, lines: kept });
  };
  add("reads", "Reads", explanation.source_table
    ? [`${explanation.source_table} records from the historical replay export`]
    : []);
  add("keeps", "Keeps records where",
    [explanation.time_predicate, ...explanation.filters].filter(Boolean).flatMap(humanizeConditionLines));
  add("derives", "Derives", explanation.derived_fields.map(humanizeAssignment));
  add("groups", "Groups by", explanation.group_by.map(humanizeAssignment));
  add("measures", "Measures", explanation.aggregations.map(humanizeAssignment));
  add("qualifies", "Qualifies when", explanation.qualification.flatMap(humanizeConditionLines));
  return steps;
}

/** What the executed query actually returned for this run. */
export function observationLines(observation: RuleObservation): string[] {
  const lines = [
    `Entity groups returned: ${observation.groups_returned}`,
    `Groups that qualified: ${observation.groups_qualified} of ${observation.groups_returned}, testing ${humanizeConditionText(observation.threshold_expression)}`,
    `Largest group: ${plural(observation.max_group_count, "record")}`,
    `Query time: ${observation.elapsed_ms} ms`,
  ];
  if (observation.entities.length) lines.push(`Qualified entities: ${observation.entities.join("; ")}`);
  lines.push(observation.outcome === "hit"
    ? "Outcome: hit — at least one group met the threshold"
    : "Outcome: miss — no group met the threshold");
  return lines;
}

/** What the one group that qualified actually contained. */
export function observedLines(observed: FactorObserved): string[] {
  return [
    `Qualifying entity: ${observed.entity}`,
    `Records counted in that group: ${observed.event_count}`,
    `Qualification test: ${humanizeConditionText(observed.qualification_test)}`,
    `Columns returned: ${observed.returned_columns.map(fieldLabel).join(", ")}`,
    `Resource ids sampled for citation: ${observed.evidence_ids_returned}`,
  ];
}

/** The unmodified fragments, for the collapsed exact-terms disclosure. */
export function rawTerms(explanation: RuleExplanation): { label: string; values: string[] }[] {
  const rows: { label: string; values: string[] }[] = [];
  const add = (label: string, values: string[]) => {
    const kept = values.filter((value) => value !== undefined && value !== "");
    if (kept.length) rows.push({ label, values: kept });
  };
  add("source table", [explanation.source_table]);
  add("time predicate", [explanation.time_predicate]);
  add("filters", explanation.filters);
  add("derived fields", explanation.derived_fields);
  add("group by", explanation.group_by);
  add("aggregations", explanation.aggregations);
  add("qualification", explanation.qualification);
  add("projection", explanation.projection);
  add("ordering", explanation.ordering);
  add("pipeline steps", [`${explanation.pipeline_steps} piped operator(s)`]);
  return rows;
}

/** Keep the full UTC instant but split it so it never runs into the next column. */
export function formatUtc(value: string): { date: string; time: string } {
  const match = /^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})(\.\d+)?Z?$/.exec(value.trim());
  if (!match) return { date: value, time: "" };
  const fraction = match[3] && /[1-9]/.test(match[3]) ? match[3] : "";
  return { date: match[1], time: `${match[2]}${fraction} UTC` };
}
