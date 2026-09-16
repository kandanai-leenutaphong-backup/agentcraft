import type { GridStatus, GridStatusMetric, GridStatusRegion } from "@/api/situationApi";

const metric = (tag_id: string, latest: number, min: number, max: number, samples = 96): GridStatusMetric => ({
  tag_id,
  avg: Number(((min + max + latest) / 3).toFixed(1)),
  min,
  max,
  latest,
  latest_ts: "2026-02-12T11:24:00+10:00",
  sample_count: samples,
});

const region = ({
  code,
  generation,
  demand,
  reserve,
  wind,
  solar,
  freqMin,
  freqMax,
  band,
  bandLabel,
  excursions,
  threatened,
  situations,
  stations,
}: {
  code: string;
  generation: number;
  demand: number;
  reserve: number;
  wind: number;
  solar: number;
  freqMin: number;
  freqMax: number;
  band: string;
  bandLabel: string;
  excursions: number;
  threatened: number;
  situations: number;
  stations: number;
}): GridStatusRegion => {
  const renewable = wind + solar;
  return {
    generation_mw: metric(`${code}.GEN.TOTAL_MW`, generation, generation - 140, generation + 90),
    demand_mw: metric(`${code}.LOAD.TOTAL_MW`, demand, demand - 120, demand + 100),
    reserve_mw: metric(`${code}.RESERVE.MW`, reserve, reserve - 55, reserve + 70),
    wind_mw: metric(`${code}.WIND.MW`, wind, Math.max(0, wind - 90), wind + 70),
    solar_mw: metric(`${code}.SOLAR.MW`, solar, Math.max(0, solar - 130), solar + 55),
    storage_mw: metric(`${code}.BESS.MW`, 36, -95, 130),
    renewable_mw: renewable,
    renewable_pct_generation: Number((renewable / generation * 100).toFixed(1)),
    frequency: {
      min_hz: freqMin,
      max_hz: freqMax,
      avg_hz: Number(((freqMin + freqMax) / 2).toFixed(3)),
      band_breached: band,
      band_label: bandLabel,
      excursion_count: excursions,
    },
    threatened_mw: threatened,
    threatened_pct_generation: Number((threatened / generation * 100).toFixed(1)),
    situation_count: situations,
    station_count: stations,
  };
};

const regions = {
  NSW: region({ code: "NSW", generation: 8240, demand: 7890, reserve: 680, wind: 1020, solar: 1510, freqMin: 49.71, freqMax: 50.04, band: "network", bandLabel: "Network", excursions: 5, threatened: 430, situations: 2, stations: 1 }),
  VIC: region({ code: "VIC", generation: 5930, demand: 5710, reserve: 520, wind: 1260, solar: 780, freqMin: 49.86, freqMax: 50.03, band: "generation", bandLabel: "Generation", excursions: 2, threatened: 0, situations: 0, stations: 0 }),
  QLD: region({ code: "QLD", generation: 6810, demand: 6590, reserve: 760, wind: 480, solar: 1740, freqMin: 49.88, freqMax: 50.05, band: "normal", bandLabel: "Normal", excursions: 1, threatened: 0, situations: 0, stations: 0 }),
  SA: region({ code: "SA", generation: 2210, demand: 2050, reserve: 260, wind: 940, solar: 390, freqMin: 49.83, freqMax: 50.06, band: "generation", bandLabel: "Generation", excursions: 2, threatened: 0, situations: 0, stations: 0 }),
  TAS: region({ code: "TAS", generation: 1710, demand: 1540, reserve: 290, wind: 230, solar: 50, freqMin: 49.90, freqMax: 50.02, band: "normal", bandLabel: "Normal", excursions: 1, threatened: 12, situations: 1, stations: 1 }),
};

const totalGeneration = Object.values(regions).reduce((sum, r) => sum + (r.generation_mw.latest ?? 0), 0);
const totalDemand = Object.values(regions).reduce((sum, r) => sum + (r.demand_mw.latest ?? 0), 0);
const totalRenewable = Object.values(regions).reduce((sum, r) => sum + (r.renewable_mw ?? 0), 0);
const totalThreatened = Object.values(regions).reduce((sum, r) => sum + r.threatened_mw, 0);

export const NGM_GRID_STATUS: GridStatus = {
  window: { start: "2026-02-12 11:13:00", end: "2026-02-12 11:28:00", source: "scan_window" },
  tag_dict_version: "demo-grid-status-2026.05.25",
  nem: {
    generation_mw: { value: totalGeneration, components: "regional generation telemetry" },
    demand_mw: { value: totalDemand, components: "regional demand telemetry" },
    reserve_mw: metric("NEM.RESERVE.MW", 2510, 2380, 2675),
    renewable_mw: { value: totalRenewable, components: "wind + solar" },
    renewable_pct_generation: Number((totalRenewable / totalGeneration * 100).toFixed(1)),
    frequency: {
      min_hz: 49.71,
      max_hz: 50.06,
      total_excursion_windows: 11,
      worst_band: "network",
      worst_region: "NSW",
    },
    threatened_mw: totalThreatened,
    threatened_pct_generation: Number((totalThreatened / totalGeneration * 100).toFixed(1)),
  },
  regions,
  situations: {
    count: 5,
    station_count: 5,
    severity_counts: { CRITICAL: 1, MAJOR: 1, SERIOUS: 1, INVESTIGATE: 2 },
    threatened_mw: totalThreatened,
    top_threats: [
      { station: "MARRABEL_NX", region: "NSW", mw: 430, situation_count: 2, worst_severity: "CRITICAL" },
      { station: "OAKBANK_NX", region: "TAS", mw: 12, situation_count: 1, worst_severity: "INVESTIGATE" },
    ],
  },
  data_quality: [
    { severity: "info", code: "DEMO_SYNTHETIC", message: "Synthetic public-demo telemetry anchored to the NGM busbar scenario window." },
    { severity: "warning", code: "FREQ_EXCURSION", message: "Frequency nadir 49.71 Hz observed after MARRABEL_NX generation loss.", tag_id: "NSW.GEN.TOTAL_MW" },
  ],
};
