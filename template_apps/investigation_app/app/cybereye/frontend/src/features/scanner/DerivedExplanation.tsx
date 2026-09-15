import type { FactorObserved, RuleExplanation, RuleObservation } from "../../shared/types";
import { RoleBadge } from "./RoleBadge";
import { narrativeSteps, observationLines, observedLines, rawTerms, type DerivedStep } from "./humanize";

interface Props {
  explanation: RuleExplanation;
  observation?: RuleObservation;
  observed?: FactorObserved;
  caption?: boolean;
}

/**
 * Narrates the rule's parsed query structure and this run's output.
 * Every sentence comes from the generic fragment humanizer — nothing is authored per rule.
 */
export function DerivedExplanation({ explanation, observation, observed, caption = true }: Props) {
  const steps: DerivedStep[] = [...narrativeSteps(explanation)];
  if (observation) steps.push({ key: "observation", title: "In this window it found", lines: observationLines(observation) });
  if (observed) steps.push({ key: "observed", title: "In this window it found", lines: observedLines(observed) });

  return (
    <div className="derived">
      <div className="derived-headline">
        <RoleBadge role={explanation.role} />        <span className="derived-meta">v{explanation.version}</span>
        <span className="derived-meta">threshold {explanation.threshold}</span>
        <span className="derived-meta">score +{explanation.score}</span>
      </div>
      {caption && <p className="derived-caption">How this rule decided, read from its own query</p>}
      <ol className="derived-steps">
        {steps.map((step, index) => (
          <li key={step.key}>
            <span className="derived-step-index" aria-hidden="true">{index + 1}</span>
            <div className="derived-step-body">
              <b>{step.title}</b>
              <ul>
                {step.lines.map((line, position) => <li key={position}>{line}</li>)}
              </ul>
            </div>
          </li>
        ))}
      </ol>
      <details className="derived-raw">
        <summary>Show the exact query terms</summary>
        <dl className="derived-rows">
          {rawTerms(explanation).map((row) => (
            <div key={row.label}>
              <dt>{row.label}</dt>
              <dd className="mono">
                {row.values.map((value, index) => <span key={index}>{value}</span>)}
              </dd>
            </div>
          ))}
        </dl>
      </details>
    </div>
  );
}
