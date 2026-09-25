# ERCOT open data source candidates

Candidate public sources for a real-data GridOps benchmark, anchored on ERCOT (Texas). Covers five categories:
topology, telemetry, alarms, technical documentation and incident reports.

Links were checked on 2026-09-25:

- **checked**: the link answered HTTP 200 with the expected page, from Singapore or from Azure East US.
- **checked (US)**: ercot.com, api.ercot.com and puc.texas.gov block requests from outside the US (Imperva/Cloudflare).
  These links returned HTTP 200 with the expected page title from Azure East US
  ([scripts/us_egress_probe.sh](scripts/us_egress_probe.sh)). `api.ercot.com` answers 401 without a key there,
  instead of 403. ERCOT data product pages render their content client-side, so for those the product ID (EMIL) and
  title were matched against the ERCOT Public API spec ([ercot/api-specs](https://github.com/ercot/api-specs)) or the
  `gridstatus` ERCOT source.
- **unverified**: blocked from both locations. ferc.gov serves a Cloudflare bot challenge even from the US.

Fetch ERCOT and PUCT data from a US location.

Nothing here has been downloaded or licence-reviewed. Check each source's terms of use before redistributing data.

## Topology

| Candidate | What it gives | Caveat | Source |
|---|---|---|---|
| ERCOT Network Operations Model (CIM) | Full breaker-level CIM network model | Security-restricted (CEII); market participants only, under NDA. Not usable | [ERCOT transmission info](https://www.ercot.com/gridinfo/transmission) (checked (US)) |
| Settlement Points List and Electrical Buses Mapping (NP4-160-SG) | Resource node → electrical bus → substation, with kV | Real names; the best public link from units to buses | [NP4-160-SG](https://www.ercot.com/mp/data-products/data-product-details?id=NP4-160-SG) (checked (US); ID corroborated: gridstatus) |
| SCED Shadow Prices and Binding Transmission Constraints (NP6-86-CD) | Real monitored element and contingency names (lines, transformers) | Shows which elements exist, not how they connect | [NP6-86-CD](https://www.ercot.com/mp/data-products/data-product-details?id=NP6-86-CD) (ID corroborated: ERCOT API spec) |
| LMP by Electrical Bus (NP6-787-CD) | List of electrical bus names over time | Supplements the bus mapping | [NP6-787-CD](https://www.ercot.com/mp/data-products/data-product-details?id=NP6-787-CD) (ID corroborated: ERCOT API spec) |
| EIA-860 / EIA-860M (balancing authority `ERCO`) | Every generator: plant, unit, coordinates, capacity, technology, grid voltage | Public domain; the unit registry backbone. 860M is the monthly update | [EIA-860](https://www.eia.gov/electricity/data/eia860/) (checked), [EIA-860M](https://www.eia.gov/electricity/data/eia860m/) (checked) |
| ERCOT Capacity, Demand and Reserves (CDR) report | Unit list with zone and capacity | Published twice a year | [ERCOT resource adequacy](https://www.ercot.com/gridinfo/resource) (checked (US)) |
| Generator Interconnection Status report (PG7-200-ER) | Interconnection queue with point-of-interconnection substation and county | Monthly | [PG7-200-ER](https://www.ercot.com/mp/data-products/data-product-details?id=PG7-200-ER) (page loads (US); ID not corroborated) |
| HIFLD transmission lines and substations | Lines and substations with voltage and geometry | Hub loads; unknown: which open layers remain available | [HIFLD hub](https://hifld-geoplatform.hub.arcgis.com/) (checked), [GeoPlatform](https://www.geoplatform.gov/) (checked) |
| OpenStreetMap power data | Lines, substations, plants | ODbL licence; Texas coverage is good | [Geofabrik Texas extract](https://download.geofabrik.de/north-america/us/texas.html) (checked), [Open Infrastructure Map](https://openinframap.org/) (checked) |
| Texas A&M ACTIVSg2000 (synthetic Texas) | 2,000 buses, geolocated; power flow, dynamics and GMD parameters; PowerWorld/MATPOWER/PSS/E/PSLF formats | Synthetic; bears no relation to real assets. Free for any use; citation requested. Base for breaker-level synthesis | [ACTIVSg2000](https://electricgrids.engr.tamu.edu/electric-grid-test-cases/activsg2000/) (checked), [ACTIVSg time series](https://electricgrids.engr.tamu.edu/activsg-time-series-data/) (checked) |
| pandapower | Loads MATPOWER cases; power flow and simulation | The tool for synthetic topology and events | [pandapower](https://www.pandapower.org/) (checked) |

## Telemetry

| Candidate | What it gives | Caveat | Source |
|---|---|---|---|
| 60-Day SCED Disclosure Reports (NP3-965-ER) | Telemetered MW every 5 min per unit, base points, output limits (HSL/LSL), status | Published with a 60-day lag. Real unit names; the core source for unit trips and derates | [NP3-965-ER](https://www.ercot.com/mp/data-products/data-product-details?id=NP3-965-ER) (ID corroborated: ERCOT API spec + gridstatus) |
| Actual System Load by Weather Zone (NP6-345-CD) | Hourly load per weather zone | Public | [NP6-345-CD](https://www.ercot.com/mp/data-products/data-product-details?id=NP6-345-CD) (ID corroborated: ERCOT API spec) |
| Wind / solar actual 5-min values (NP4-733-CD, NP4-738-CD) | System wind and solar output every 5 min | Regional variants: NP4-743-CD, NP4-746-CD | [NP4-733-CD](https://www.ercot.com/mp/data-products/data-product-details?id=NP4-733-CD), [NP4-738-CD](https://www.ercot.com/mp/data-products/data-product-details?id=NP4-738-CD) (ID corroborated: ERCOT API spec) |
| Fuel mix report | 15-min generation by fuel | Monthly Excel | [ERCOT generation](https://www.ercot.com/gridinfo/generation) (checked (US)) |
| Settlement Point Prices at Resource Nodes, Hubs and Load Zones (NP6-905-CD) | 15-min price per node | A congestion signal | [NP6-905-CD](https://www.ercot.com/mp/data-products/data-product-details?id=NP6-905-CD) (ID corroborated: ERCOT API spec + gridstatus) |
| ERCOT Public API | Programmatic access to the above | Free registration and subscription key needed | [ercot/api-specs](https://github.com/ercot/api-specs) (checked), [API Explorer](https://apiexplorer.ercot.com/) (checked (US)) |
| `gridstatus` Python library | Open-source ERCOT and EIA fetchers | Reuse it instead of writing scrapers | [gridstatus](https://github.com/gridstatus/gridstatus) (checked) |
| EPA CEMS via CAMPD | Hourly gross MW per fossil unit | Public domain; cross-check for trips | [CAMPD](https://campd.epa.gov/) (checked) |
| EIA-930 Hourly Electric Grid Monitor (`ERCO`) | Hourly demand, generation by fuel, interchange | Public domain; also served by the EIA API | [Grid Monitor](https://www.eia.gov/electricity/gridmonitor/) (checked), [EIA Open Data API](https://www.eia.gov/opendata/) (checked) |
| FNET/GridEye | Frequency measurements and event lists | Partly public; not tied to named assets | [FNET/GridEye](https://fnetpublic.utk.edu/) (checked) |
| ORNL Grid Event Signature Library | Labelled PMU and waveform events | Not tied to ERCOT assets | [GESL](https://gesl.ornl.gov/) (checked) |
| ERCOT PDCWG frequency analyses | Frequency plots and event statistics | unknown: whether high-resolution frequency is archived publicly | [PDCWG](https://www.ercot.com/committees/ros/pdcwg) (checked (US)) |

## Alarms (no real SCADA alarms are public; build them from event records)

| Candidate | What it gives | Use | Source |
|---|---|---|---|
| Unplanned Resource Outages Report (NP1-346-ER) | Unit, start and end time, cause | Real events; reconstruct trip alarms from them | [NP1-346-ER](https://www.ercot.com/mp/data-products/data-product-details?id=NP1-346-ER) (ID corroborated: gridstatus) |
| Hourly Resource Outage Capacity (NP3-233-CD) | Aggregate outage MW, planned and forced | Context for outage alarms | [NP3-233-CD](https://www.ercot.com/mp/data-products/data-product-details?id=NP3-233-CD) (ID corroborated: ERCOT API spec) |
| ERCOT operations messages and notices (advisories, watches, emergency (EEA) levels, conservation calls) | Timestamped system-level notices | Map to system alarms | [Operations messages](https://www.ercot.com/services/comm/mkt_notices/opsmessages) (checked (US)) |
| ERCOT generation outages dashboard | Current outage view | Live only | [Generation outages](https://www.ercot.com/gridmktinfo/dashboards/generationoutages) (checked (US)) |
| SCED binding constraint activations (NP6-86-CD) | Time and element | Map to overload alarms | See Topology |
| DOE OE-417 | Structured incident records | Event-level labels; filter to Texas RE / ERCOT | [OE-417](https://doe417.pnnl.gov/) (checked) |
| Synthetic: pandapower simulations on ACTIVSg2000 | Breaker-state changes, voltage and frequency trips, protection operations | Coherent breaker-level alarms. Tag them as synthetic | See Topology |

## Technical documentation

| Candidate | Maps to | Source |
|---|---|---|
| ERCOT Operating Procedure Manuals (shift supervisor, transmission, frequency desks) | `paws` (operator procedures) | [Operating Procedures](https://www.ercot.com/mktrules/guides/procedures) (checked (US)) |
| ERCOT Nodal Protocols | Market and operating rules | [Nodal Protocols](https://www.ercot.com/mktrules/nprotocols) (checked (US)) |
| ERCOT Nodal Operating Guides | Operating rules | [Nodal Operating Guides](https://www.ercot.com/mktrules/guides/noperating) (checked (US)) |
| ERCOT Planning Guide | Planning rules | [Planning Guide](https://www.ercot.com/mktrules/guides/planning) (checked (US)) |
| NERC Reliability Standards (BAL, EOP, TOP, PRC-024/029) | Normative rules | [Standards](https://www.nerc.com/standards/reliability-standards) (checked), [complete set PDF](https://www.nerc.com/globalassets/standards/reliability-standards/rscompleteset.pdf) (checked) |
| NERC Reliability Guidelines (incl. inverter-based resource performance) | Lessons | [Reliability Guidelines](https://www.nerc.com/our-work/guidelines/reliability-guidelines) (checked) |
| NERC Alerts | Advisories | [Alerts](https://www.nerc.com/programs/bulk-power-system-awareness/alerts) (checked) |
| NERC Lessons Learned library, 2010–2026, incl. many SCADA/EMS alarm and monitoring failures | `nearhit` | [Lessons Learned](https://www.nerc.com/programs/event-analysis/lessons-learned) (checked) |
| NERC EMS assessments | EMS and alarm failure modes | [Loss of EMS Functions 2018–2020](https://www.nerc.com/globalassets/programs/event-analysis/analysis_and_risk_mitigations_2018-2020.pdf) (checked), [EMS Special Assessment 2021](https://www.nerc.com/globalassets/our-work/assessments/ems_special_assessment_march2021.pdf) (checked) |

## Incident reports

| Incident | Sources | Why | Source |
|---|---|---|---|
| Feb 2021 Winter Storm Uri | FERC-NERC report; UT Austin Energy Institute timeline (Jul 2021); ERCOT's own Feb 2021 materials | Richest data; overlaps the SCED disclosure, EIA-930 and CEMS | [FERC-NERC Feb 2021 Cold Weather Report](https://www.nerc.com/globalassets/our-work/reports/event-reports/february_2021_cold_weather_report.pdf) (checked), [UT Austin report](https://energy.utexas.edu/sites/default/files/UTAustin%20%282021%29%20EventsFebruary2021TexasBlackout%2020210714.pdf) (checked), [ERCOT Feb 2021](https://www.ercot.com/news/february2021) (checked (US)) |
| May 2021 Odessa disturbance | NERC disturbance report | A fault followed by inverter-based plants tripping, with a detailed sequence; plant names anonymised | [Odessa 2021](https://www.nerc.com/globalassets/our-work/reports/event-reports/odessa_disturbance_report.pdf) (checked) |
| June 2022 Odessa disturbance | NERC disturbance report | Repeat pattern; good comparison case | [Odessa 2022](https://www.nerc.com/globalassets/our-work/white-papers/nerc_2022_odessa_disturbance_report-1.pdf) (checked) |
| March 2022 Panhandle wind disturbance | NERC disturbance report | Wind plants tripping in the Texas Panhandle | [Panhandle wind](https://www.nerc.com/globalassets/our-work/reports/event-reports/panhandle_wind_disturbance_report.pdf) (checked) |
| Dec 2022 Winter Storm Elliott | FERC-NERC review | Mostly PJM/SERC; limited ERCOT impact | [Winter Storm Elliott](https://www.nerc.com/our-work/reports/winter-storm-elliott) (checked) |
| Aug 2003 Northeast blackout (not ERCOT) | US-Canada Task Force final report | The root cause included an EMS alarm failure; a strong alarm-investigation reference | [2003 blackout report](https://www.nerc.com/globalassets/our-work/reports/event-reports/august_2003_blackout_final_report.pdf) (checked) |
| NERC event analysis index | All major event reports | Source for further cases | [Event Analysis Reports](https://www.nerc.com/our-work/reports/event-analysis-reports) (checked) |
| ERCOT frequency events | Monthly PDCWG frequency-event analyses | Many small events with MW lost and frequency nadir; benchmark volume | [PDCWG](https://www.ercot.com/committees/ros/pdcwg) (checked (US)) |
| May 2024 Houston derecho / July 2024 Hurricane Beryl | PUCT and CenterPoint reports | Mostly distribution-level; lower fit | [PUCT](https://www.puc.texas.gov/) (checked (US)) |

Not located: the NERC review of 2023 ERCOT inverter-based resource events. It is not on the NERC event analysis
index; search NERC white papers or RSTC materials.

## Recommended core set

- **Topology:** EIA-860, NP4-160-SG and NP6-86-CD element names give the real skeleton; ACTIVSg2000 plus pandapower
  supply synthetic breaker detail.
- **Telemetry:** NP3-965-ER, EIA-930 and CAMPD, fetched through `gridstatus` or the ERCOT Public API.
- **Alarms:** reconstructed from NP1-346-ER and operations messages, plus synthetic alarms from pandapower
  simulations, tagged as synthetic.
- **Documentation:** ERCOT Operating Procedures, NERC standards, NERC Lessons Learned.
- **Incidents:** Uri as the flagship, the 2021 and 2022 Odessa events and the Panhandle event as focused
  investigations, PDCWG frequency events for volume.
