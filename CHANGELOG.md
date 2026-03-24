# OncoBiome Swarm — CHANGELOG

All notable changes documented by sprint.

---

## Sprint 4 (2026-03-24) — NK/DC Agents + Validation — COMPLETE

### New agents
- `agents/nk_cell.py` — NKCell: kill_rate=0.10, IL-6 suppression (threshold 0.04), exhaustion at age>20/kills>3
- `agents/dendritic_cell.py` — DendriticCell: tolerogenic default, matures after 3 cycles IFN-γ>0.05

### New interactions (simulation/interactions.py)
- `_nk_attacks()` — NK kills tumor with IL-6 suppression factor
- `_dc_maturation()` — progressive DC maturation by IFN-γ
- `_dc_activates_cd8()` — mature DC boosts CD8⁺ kill_rate +20% in radius
- HIF-1α reference added to `_vegf_angiogenesis()` docstring

### Config (config/settings.py)
- Added: `il6_immune_suppression_threshold`, `il6_immune_suppression_factor`, `immune_exhaustion_age`
- Added: full NK parameter block (nk_kill_rate, nk_exhaustion_age, nk_il6_suppression_threshold/factor)
- Added: full DC parameter block (dc_maturation_ifng_threshold, dc_activation_boost, dc_activation_radius, dc_maturation_cycles)

### Experiment infrastructure
- `simulation/experiment_loader.py` — added N_NK_CELLS, N_DENDRITIC_CELLS to env mapping
- `experiments.yaml` — 7 new NK/DC experiments including high_cd8_control_rule
- `main.py` — build_initial_population() with NKCell and DendriticCell (n=0 default, backward compatible)
- `main.py` — load_dotenv(override=False) fix (no longer overwrites real API key)

### LLM
- `llm/prompts.py` — NK_CELL and DENDRITIC_CELL system prompts
- `llm/rule_engine.py` — _nk_rules() and _dc_rules()
- `llm/opus_analyzer.py` — fix: call_opus(prompt=...) instead of system+user kwargs

### Quantitative validation
- `scripts/sensitivity_analysis.py` — OAT (7 runs) + full factorial 3×3×3 (27 runs), $0
- `scripts/stats/rmse_validation.py` — 4 RMSE metrics: tumor ratio, timing, LLM vs rule MAE, inflection
- Results: `results/sensitivity_oat.csv`, `results/sensitivity_full_factorial.csv`, `results/rmse_validation.json`

### Tests
- `tests/test_nk_dc.py` — 50+ NK/DC tests (AgentType, config, rule engine, interactions)
- **178/178 tests passing** (up from 138 in Sprint 3)

### Experimental results
- `high_cd8_control_rule`: tumor c52=17 (decouples CD8⁺ count effect from NK/DC effect)
- `nk_boost_rule`: tumor c52=40 — NK dose threshold confirmed (4 NK: no effect; 8 NK: −37%)
- `innate_adaptive_bridge_llm` n=3: tumor 72.7±0.6 (CV=0.8%), collapse c32±2.6 (CV=8.3%)
- NK exhaustion precedes CD8⁺ collapse in all 3 runs: c25-30 vs c29-34
- DC remain tolerogenic in both LLM and rule engine — KRAS G12D phenotype confirmed
- TAM emergence: macrophages silently M2-polarized (Opus c25 emergent analysis)

### Cost
- Sprint 4 total: ~$18.40 (n=3 bridge LLM: $2.06, sensitivity: $0, all validation: $0)
- Cumulative project: ~$21.76

---

## Sprint 3 (2026-03-24) — Reproducibility & bioRxiv prep — COMPLETE

- Completed n=3 for all three LLM experiments:
  - `cap80_baseline`: c28.3 ± 3.2 cycles (61.4 ± 7.0d), CV=11.3% ✓
  - `immune_boost`: c28.7 ± 2.1 cycles (62.1 ± 4.5d), CV=7.3% ✓✓
  - `combination_therapy`: c29.0 ± 7.9 cycles (62.8 ± 17.2d), CV=27.4% ⚠ (biological stochasticity)
- High CV in combination_therapy declared as intrinsic, not technical defect
- Created `.gitignore` — protects .env, logs/, state/, runs/
- Cleaned `.env` — API keys replaced with placeholders
- Fixed `mcp_server.py` — hardcoded Python path → `sys.executable`
- Fixed `config/biological_seed.py` — 1 cycle = 2.17d (52h, PANC-1 DT)
- Total cost Sprint 3: ~$3.36

---

## Sprint 2 (2026-03-23) — Factorial design complete

- `combination_therapy` LLM run completed (c20 collapse, $1.76)
- Immunological paradox confirmed: combination collapses earlier than immune_boost
- Sequential innate/adaptive immunity collapse: macrophages c31–32 after CD8⁺ c30
- Clonal evolution subpopulation (division_count=2) identified by Opus at c50
- Factorial 2×3 fully closed: 6 conditions × LLM vs Rule Engine

---

## Sprint 1 (2026-03-23) — Biological calibration

- KRAS G12D seed calibrated against 5 primary literature parameters
- PANC-1 doubling time 52h → 1 cycle = 2.17 biological days
- Validation against Selvanesan 2020: <5% timing deviation
- 4 qualitative mechanisms validated: Cold TME, immunoediting, checkpoint resistance, Warburg plateau
- 14 biological seed tests added

---

## Sprint 0 (2026-03-21) — Framework

- LLM-ABM core: TumorCell, ImmuneCell, MacrophageAgent, PhytochemicalAgent, CytokineAgent
- Smart batching: 1 API call/agent-type/cycle (85% cost reduction)
- BatchError → rule engine fallback ($0)
- Rule engine: deterministic mirror of LLM prompts, 77 cycles in <5 seconds
- mem0 / InMemoryStore: per-agent episodic memory
- Plotly Dash dashboard (real-time population + cytokine visualization)
- MCP server for Claude Desktop integration
- 138 tests passing
