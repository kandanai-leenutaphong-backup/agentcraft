/**
 * Vocabulary store — centralised domain-specific UI text.
 *
 * Module role:
 *   Every user-visible domain label is defined here as a typed
 *   vocabulary key. Components read individual keys via Zustand
 *   selectors instead of hardcoding domain strings. The vocabulary is
 *   fixed to the energy/grid terms; there is no per-scenario override.
 *
 * Why a Zustand store (not React context):
 *   The rest of the app uses Zustand exclusively for shared state.
 *   A Zustand store avoids an extra <Provider> wrapper, supports
 *   selector-based re-render optimisation, and can be read from
 *   outside React (e.g. situationStore's investigate prompt builder).
 *
 * Extension cost:
 *   Adding a new vocabulary key = add to DomainVocabulary interface +
 *   add default in ENERGY_VOCABULARY + use via useVocabulary() in the
 *   component. No wiring, no providers.
 *
 * Key collaborators:
 *   - Fixed at the energy defaults; no scenario override path exists.
 *   - scenarioSchema.ts    — DomainVocabulary is an optional field on
 *                            KioskBootstrap
 *   - All UI components that previously hardcoded domain strings
 *
 * Dependents:
 *   OperatingStatePanel, SituationCard, PanelLayout, CenterTabs,
 *   ChatPanel, DisclaimerButton, ScanProgress, SpotlightOverlay,
 *   CommandPalette, HelpOverlay, PriorityActionsPanel, EquipmentRow,
 *   StationNode, TopologyMap, TopologyDetailPane, PasswordGate,
 *   PinnedSituationPanel, situationStore (investigate prompt).
 */

import { create } from "zustand";

// ── Vocabulary shape ─────────────────────────────────────────────────

/** User-visible UI text for the energy domain. Every key maps to a
 *  string or string set rendered somewhere in the UI. */
export interface DomainVocabulary {
  /** Product name displayed in header, chat empty state, spotlight
   *  captions, and the password gate. Default: "GridIQ". */
  productName: string;

  /** Left-sidebar operating-state panel heading and the center-column
   *  tab label. Default: "Grid Status". */
  systemStatusLabel: string;

  /** Primary capacity/throughput unit shown in panels, cards, topology
   *  nodes, and threat breakdowns. Default: "MW". */
  primaryUnit: string;

  /** Label for the primary metric aggregate (e.g. "Total Generation",
   *  "Traffic Volume", "Total Flow"). */
  primaryUnitLabel: string;

  /** Secondary oscillating metric unit (e.g. "Hz" for grid frequency,
   *  "MHz" for radio frequency). Empty string hides the section. */
  frequencyUnit: string;

  /** Label for the frequency/oscillation section heading. */
  frequencyLabel: string;

  /** Nominal value for the frequency metric. Used for deviation
   *  highlighting (50.0 Hz for the NEM). */
  frequencyNominal: number;

  /** Generic term for real-time monitoring alerts. Default: "Alarms". */
  alertsLabel: string;

  /** Generic term for telemetry/surveillance data. Default: "SCADA". */
  telemetryLabel: string;

  /** Classification category labels keyed by internal enum value.
   *  Displayed on situation card badges. */
  classificationLabels: Record<string, string>;

  /** The authority / standard cited for classification (e.g.
   *  "NER 4.2.3", "ICAO Annex 11"). */
  classificationAuthority: string;

  /** Spinner text shown while classification is in progress. */
  classifyingText: string;

  /** Rotating status messages shown during a situation scan. */
  scanMessages: string[];

  /** Disclaimer pill text (collapsed header badge). */
  disclaimerPill: string;

  /** Disclaimer heading (expanded popover). */
  disclaimerHeading: string;

  /** Disclaimer body paragraphs (expanded popover). Array of strings,
   *  each rendered as a separate <p>. */
  disclaimerBody: string[];

  /** Chat empty-state description when no agent description is
   *  available. */
  chatEmptyDescription: string;

  /** Empty-state text for the priority actions panel. */
  priorityEmptyText: string;

  /** Spotlight caption prefix. Default: "GridIQ — Look here". */
  spotlightPrefix: string;

  /** Password gate heading. Default: "3IQ Kiosk". */
  gateHeading: string;

  /** Facility/location term used in labels (e.g. "stations",
   *  "facilities", "sectors"). Lowercase plural. */
  facilityTerm: string;

  /** Singular form of facilityTerm. */
  facilityTermSingular: string;

  /** Region/area term (e.g. "region", "sector", "zone"). Lowercase. */
  regionTerm: string;

  /** System-wide aggregate label, e.g. "Grid".
   *  Used in impact percentages: "X% of {systemLabel}". */
  systemLabel: string;

  /** Label for capacity metric (e.g. "Rated Capacity", "Max Throughput"). */
  capacityLabel: string;

  /** Total capacity heading (e.g. "Total Generation", "Total Capacity"). */
  totalCapacityLabel: string;

  /** Per-region capacity heading. Default: "Regional Capacity". */
  regionalCapacityLabel: string;

  /** Threat summary label (e.g. "MW Threatened", "Ops Impacted"). */
  threatLabel: string;

  /** Step-change metric label (e.g. "Step Changes", "Track Deviations"). */
  stepChangeLabel: string;

  /** Impact label for situations (e.g. "MW lost", "ops affected"). */
  impactLabel: string;

  /** Impact boost label for situations (e.g. "MW+", "ops+"). */
  impactBoostLabel: string;

  /** Short impact-magnitude unit shown inline on the situation card head
   *  row next to the impact number (e.g. "MW", "ops", "subs"). Distinct
   *  from primaryUnit because the head number is an impact magnitude, not
   *  a throughput reading. */
  impactUnit: string;

  /** Generic noun for a monitored asset (e.g. "Equipment", "Network
   *  element", "System"). Used in topology detail headings and the
   *  situation card's affected-asset section. */
  equipmentTerm: string;

  /** Label for the per-asset external identifier shown in the topology
   *  detail pane (e.g. "SCADA ID", "Element ID", "Surveillance ID"). */
  identifierLabel: string;

  /** Label for the asset classification list shown in the topology
   *  detail pane (e.g. "CIM classes", "Function classes"). */
  equipmentClassLabel: string;

  /** Unit for the topology equipment-grouping dimension (e.g. "kV" for
   *  energy voltage tiers). Empty string disables grouping entirely —
   *  the equipment list renders flat and the grouping summary row is
   *  hidden. Non-energy domains set "" because voltage tiers are
   *  electrical-only. */
  equipmentGroupUnit: string;

  /** Declarative stat grid for the topology detail pane. Each entry maps
   *  a column label to one numeric field on the equipment record. Lets a
   *  scenario show only the metrics that make sense for its domain
   *  (kV/MW/MVA) without forking the
   *  component. */
  topologyStats: TopologyStatDescriptor[];

  /** Whether to show the left-column detector-tuning dials (Window / Max
   *  Alarms / Max SCADA) and the "Detector Tuning" workspace mode. These
   *  are grid-detector controls with no meaning in domains whose alerts
   *  arrive pre-formed (e.g. a SOC alert queue). Default: true. */
  showDetectorTuning: boolean;
}

/** One column in the topology detail-pane stat grid. `field` is a
 *  numeric key on the topology equipment record; `label` is the
 *  domain-specific unit/heading shown above the value. */
export interface TopologyStatDescriptor {
  label: string;
  field: "nominal_kv" | "mw_max" | "mva_rated";
}

// ── Energy default ───────────────────────────────────────────────────

/** Complete energy-domain vocabulary — the original GridIQ defaults.
 *  Every scenario that does not supply vocabulary, or omits a key,
 *  falls back to these values. */
export const ENERGY_VOCABULARY: DomainVocabulary = {
  productName: "GridIQ",
  systemStatusLabel: "Grid Status",
  primaryUnit: "MW",
  primaryUnitLabel: "Total Generation",
  frequencyUnit: "Hz",
  frequencyLabel: "System Frequency",
  frequencyNominal: 50,
  alertsLabel: "Alarms",
  telemetryLabel: "SCADA",
  classificationLabels: {
    credible: "CREDIBLE",
    non_credible: "NON-CREDIBLE",
    non_event: "NON-EVENT",
  },
  classificationAuthority: "NER 4.2.3",
  classifyingText: "Classifying per NER 4.2.3…",
  scanMessages: [
    "Pulling alarms…",
    "Joining SCADA step-changes…",
    "Crunching frequency excursions…",
    "Scoring stations…",
    "Ranking severity…",
  ],
  disclaimerPill: "Public-Facing Demo Version (Real Operational Data Disabled)",
  disclaimerHeading: "Demonstration only — not operational data.",
  disclaimerBody: [
    "This is a public-facing version of GridIQ. While GridIQ can connect to real grid operational data and knowledge bases, this public-facing demo runs on synthetic data generated from publicly-available incident reports.",
    "All stations, equipment, alarms, personnel, procedures, and incidents shown are fictional. This environment is not connected to any live SCADA, EMS, market, or operator data feed.",
    "No confidential or commercially sensitive information is displayed or stored. Any resemblance to real assets, events, or individuals is coincidental.",
    "Workflows shown are illustrative of GridIQ's value proposition and do not represent recommended operator practice.",
  ],
  chatEmptyDescription:
    "GridIQ can help further analyse alarms, explain system behaviour or surface signals.",
  priorityEmptyText: "Ask GridIQ to investigate an event.",
  spotlightPrefix: "GridIQ — Look here",
  gateHeading: "3IQ Kiosk",
  facilityTerm: "stations",
  facilityTermSingular: "Station",
  regionTerm: "region",
  systemLabel: "Grid",
  capacityLabel: "Rated Capacity",
  totalCapacityLabel: "Total Capacity",
  regionalCapacityLabel: "Regional Capacity",
  threatLabel: "MW Threatened",
  stepChangeLabel: "Step Changes",
  impactLabel: "MW lost",
  impactBoostLabel: "MW+",
  impactUnit: "MW",
  equipmentTerm: "Equipment",
  identifierLabel: "SCADA ID",
  equipmentClassLabel: "CIM classes",
  equipmentGroupUnit: "kV",
  topologyStats: [
    { label: "kV", field: "nominal_kv" },
    { label: "MW", field: "mw_max" },
    { label: "MVA", field: "mva_rated" },
  ],
  showDetectorTuning: true,
};

// ── Store ────────────────────────────────────────────────────────────

interface VocabularyStore {
  vocab: DomainVocabulary;
}

export const useVocabularyStore = create<VocabularyStore>(() => ({
  vocab: { ...ENERGY_VOCABULARY },
}));

/** Convenience selector hook — reads a single vocabulary key with
 *  minimal re-render surface. Usage:
 *    const unit = useVocab("primaryUnit");  // "MW"
 */
export function useVocab<K extends keyof DomainVocabulary>(key: K): DomainVocabulary[K] {
  return useVocabularyStore((s) => s.vocab[key]);
}

/** Direct (non-hook) accessor for use outside React (e.g. store
 *  actions, utility functions). Returns the current vocabulary
 *  snapshot. */
export function getVocab(): DomainVocabulary {
  return useVocabularyStore.getState().vocab;
}
