# Play Demo Hook Order Crash

**Symptom**: Selecting the alternate ATC scenario from the kiosk scenario picker rendered the error boundary with `Rendered fewer hooks than expected. This may be caused by an accidental early return statement.`

**Root cause**: `PlayDemoButton` called `useMemo()` after early returns for running and single-scenario states. Starting any scenario changed the component from the picker path to the running path, reducing the number of hooks called during render.

**Problematic code**:

```tsx
if (isRunning) {
  return (
    <button type="button" onClick={stop}>
      Stop demo
    </button>
  );
}

const groups = useMemo(() => groupByIndustry(SCENARIOS), []);
```

**Fix**:

```tsx
const groups = useMemo(() => groupByIndustry(SCENARIOS), []);

if (isRunning) {
  return (
    <button type="button" onClick={stop}>
      Stop demo
    </button>
  );
}
```

**Files changed**:

- `app/frontend/src/components/demo/PlayDemoButton.tsx` — moved the scenario grouping hook before all conditional returns.
- `app/frontend/e2e/atc-scenario.spec.ts` — added and tightened the ATC scenario picker smoke test.

**Regression test**: `app/frontend/e2e/atc-scenario.spec.ts` — `loads ATC scenario and applies ATC vocabulary`.
