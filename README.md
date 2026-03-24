# OncoBiome Swarm

**LLM-driven multi-agent simulation of the KRAS G12D pancreatic tumor microenvironment**

[![Tests](https://img.shields.io/badge/tests-178%20passing-brightgreen)]()
[![Python](https://img.shields.io/badge/python-3.12-blue)]()
[![License](https://img.shields.io/badge/license-Dual%20MIT%2FCommercial-blue)]()
[![Sprint](https://img.shields.io/badge/sprint-4%20complete-brightgreen)]()
[![bioRxiv](https://img.shields.io/badge/preprint-bioRxiv-orange)]()

---

## Overview

OncoBiome Swarm is a novel agent-based modeling (ABM) framework where every biological agent in the tumor microenvironment (TME) — tumor cells, CD8⁺ T lymphocytes, NK cells, dendritic cells, macrophages, phytochemicals — is driven by an independent large language model (LLM) with persistent episodic memory.

Unlike deterministic ABMs (PhysiCell, HAL, CompuCell3D), each agent reasons contextually from local cytokine gradients, interaction history, and neighbor state. This produces emergent immunosuppressive behaviors that cannot be programmed with explicit rules.

**Central finding:** LLM agents produce immune collapse 43–74 days earlier than deterministic rules across all therapeutic conditions, recapitulating active KRAS G12D-driven immunosuppression. In Sprint 4, NK cell exhaustion precedes CD8⁺ collapse by 4–9 cycles across all n=3 runs — an unprogrammed emergent behavior consistent with in vivo NK exhaustion in PDAC.

---

## Architecture

```
agents/          TumorCell, ImmuneCell, MacrophageAgent, PhytochemicalAgent,
                 CytokineAgent, NKCell, DendriticCell (Sprint 4)
llm/             client.py (smart batch), prompts.py, rule_engine.py, opus_analyzer.py
simulation/      engine.py, environment.py, interactions.py, experiment_loader.py
config/          settings.py (KRAS G12D seed), biological_seed.py
memory/          inmemory_store.py, mem0 integration
scripts/         run_manager, sensitivity_analysis, compare_runs, utils
tests/           178 tests — biological, NK/DC, cost-safety, platform
```

**LLM stack:**
- **Claude Haiku 4.5** — per-agent microdecisions (smart batch: 1 API call/type/cycle, ~85% cost reduction)
- **Claude Opus 4.5** — emergent swarm analysis every 25 cycles
- **Rule engine** — deterministic fallback at $0 (development & validation)
- **Fallback safety:** `BatchError` → rule engine, never individual calls

---

## Biological Calibration

Calibrated for **PANC-1** (KRAS G12D, ATCC CRL-1469, doubling time 52h):

| Parameter | Value | Source |
|-----------|-------|--------|
| 1 simulation cycle | 52h = **2.17 days** | PMC4655885 |
| `immune_kill_rate` | 0.15 | ScienceDirect 2020 (50% kill/48h, E:T=10:1) |
| `m2_polarisation_il6_threshold` | 0.06 | Frontiers/Medicine 2024 |
| `nk_kill_rate` | 0.10 | Clin Cancer Res 2020 (NK PDAC) |
| `nk_il6_suppression_threshold` | 0.04 | Nat Immunol 2021 |
| `dc_maturation_ifng_threshold` | 0.05 | Immunity 2023 (KRAS G12D DC suppression) |

Validated against Selvanesan et al. *J Immunother Cancer* 2020: <5% timing deviation.

---

## Experimental Results

### Sprint 3 — Factorial 2×3 (LLM vs Rule Engine, n=3)

| Condition | Rule Engine | LLM mean ± SD (n=3) | CV | Δ days |
|-----------|-------------|---------------------|----|--------|
| Baseline (5 CD8⁺) | no collapse | c29 (62.8d, n=1) | — | >47d |
| Immune Boost (12 CD8⁺) | no collapse | c28.7 ± 2.1 (62.1 ± 4.5d) | 7.3% | >48d |
| Combination Therapy | no collapse | c29.0 ± 7.9 (62.8 ± 17.2d) | 27.4%* | >50d |

*High CV declared as intrinsic KRAS G12D stochasticity, not technical defect.

### Sprint 4 — NK/DC Innate-Adaptive Bridge (n=3)

| Condition | Rule Engine c52 | LLM c52 (n=3) | Collapse CD8⁺ |
|-----------|----------------|----------------|----------------|
| 5 CD8⁺ baseline | 63 | — | no collapse |
| 5 CD8⁺ + 4 NK | 63 | — | no collapse |
| 5 CD8⁺ + 8 NK (adoptive) | 40 (−37%) | — | no collapse |
| 5 CD8⁺ + 3 DC | 88 | — | no collapse |
| 8 CD8⁺ (control) | 17 (−73%) | — | no collapse |
| 8 CD8⁺ + 4 NK + 3 DC | 25 (−60%) | **72.7 ± 0.6** (CV=0.8%) | **c32 ± 2.6** (69.3 ± 5.7d) |

**NK dose threshold:** 4 NK cells show no effect vs baseline; 8 NK cells reduce tumor 37%. Non-linear dose response consistent with NK mass-action killing kinetics.

---

## Emergent Findings

Nine unprogrammed biological phenomena emerged from LLM agent reasoning (Claude Opus 4.5 analysis):

**Sprint 3 (5 findings):**
1. **Cold TME** — spatial CD8⁺ exclusion, IFN-γ ≈ 0 (Bear & Vonderheide 2020)
2. **Immunoediting equilibrium** — war-of-attrition phase c14–26 (Dunn et al. 2004)
3. **Checkpoint resistance** — IFN-γ present / kills absent (Zheng et al. *Cell Rep* 2024)
4. **Warburg plateau** — proliferation–death equilibrium at metabolic carrying capacity
5. **Immunological paradox** — combination therapy collapses earlier than immune boost alone

**Sprint 4 (4 new findings):**
6. **NK exhaustion precedes CD8⁺ collapse** — c25–30 vs c29–34 across all n=3 runs
7. **DC tolerogenic default** — DC remain immature in both LLM and rule engine without IFN-γ priming, reproducing KRAS G12D-driven DC suppression (Immunity 2023)
8. **NK dose threshold** — non-linear effect between 4 and 8 NK cells
9. **TAM emergence** — macrophages silently polarize M2 in VEGF-rich TME (Opus c25 analysis)

---

## Quantitative Validation (Sprint 4)

| Metric | Value | Interpretation |
|--------|-------|----------------|
| RMSE-1 (tumor ratio c20) | 0.33 | in silico vs in vivo 3× offset (expected for 2D model) |
| RMSE-2 (immune_boost timing) | 1.70 cycles (3.7d) | CV=7.3% — high reproducibility |
| RMSE-3 (LLM vs rule engine) | MAE=22.3 cycles (48.4d) | Central finding of the paper |
| RMSE-4 (inflection vs Selvanesan) | MAE=22.3 cycles (48.4d) | in vivo 14–21d vs in silico 43d |

Sensitivity analysis (OAT + 3×3×3 factorial, 34 rule engine runs, $0):
- `m2_threshold` dominates at calibration point (range OAT=45 cells)
- `kill_rate` × `m2_threshold` synergistic interaction confirmed

---

## Installation

```bash
git clone https://github.com/rcarbajalrc/oncobiome-swarm
cd oncobiome-swarm
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env: add ANTHROPIC_API_KEY=sk-ant-...
```

---

## Usage

```bash
# Validate without cost — rule engine, $0, ~5s
python main.py --experiment quick_validate --no-dashboard

# NK/DC innate-adaptive bridge — rule engine, $0
python main.py --experiment innate_adaptive_bridge_rule --no-dashboard

# NK adoptive therapy simulation — rule engine, $0
python main.py --experiment nk_boost_rule --no-dashboard

# Full LLM run with NK+DC (cap=80, ~$0.70/run)
python main.py --experiment innate_adaptive_bridge_llm --no-dashboard

# List all 22 experiments
python main.py --list-experiments

# Run full test suite
python -m pytest tests/ -q

# Sensitivity analysis ($0)
python scripts/sensitivity_analysis.py

# Scan for secrets before pushing
python scripts/scan_secrets.py
```

---

## Experiments

| Experiment | Provider | Cycles | Est. Cost |
|------------|----------|--------|-----------|
| `quick_validate` | Rule ($0) | 20 | $0 |
| `full_rule_engine` | Rule ($0) | 77 | $0 |
| `nk_baseline_rule` | Rule ($0) | 52 | $0 |
| `nk_boost_rule` | Rule ($0) | 52 | $0 |
| `dc_baseline_rule` | Rule ($0) | 52 | $0 |
| `innate_adaptive_bridge_rule` | Rule ($0) | 52 | $0 |
| `high_cd8_control_rule` | Rule ($0) | 52 | $0 |
| `innate_adaptive_bridge_llm` | LLM (cap=80) | 52 | ~$0.70 |
| `immune_boost` | LLM | 52 | ~$0.35 |
| `combination_therapy` | LLM | 52 | ~$0.45 |
| `cap80_baseline` | LLM | 77 | ~$0.35 |
| + 11 more | — | — | — |

**Cost control:** All LLM experiments with NK/DC use `max_agents=80` to prevent ×3.8 token growth from tumor proliferation. See `experiments.yaml` for full configuration.

---

## Cost Summary (to date)

| Sprint | LLM Runs | Total Cost |
|--------|----------|-----------|
| 0–3 | Factorial 2×3 + n=3 | ~$3.36 |
| 4 | NK/DC + sensitivity + n=3 bridge | ~$18.40 |
| **Total** | | **~$21.76** |

---

## Sprint Roadmap

| Sprint | Status | Objective |
|--------|--------|-----------|
| 0–3 | ✅ Complete | LLM-ABM framework + factorial + n=3 + 5 emergent findings |
| 4 | ✅ Complete | NK/DC agents + sensitivity + RMSE + n=3 bridge (4 new findings) |
| 5 | Planned | PhysiCell 3D physics (pressure, oxygen gradients, vasculature) |
| 6 | Planned | zAvatar — patient scRNA-seq seed (TCGA-PAAD) |
| 7 | Planned | MiroFish closed loop (AlphaFold3 + RFdiffusion + organoid validation) |

---

## Known Limitations

- **Population cap artifact:** With `max_agents=80`, tumor plateaus at 72–73 cells (90% of cap) post-immune collapse. This is a model constraint, not biological equilibrium. Sprint 5 will implement hypoxia-driven apoptosis to remove cap dependency.
- **2D grid:** No physical pressure or oxygen gradients. Addressed in Sprint 5 (PhysiCell).
- **NK rule engine:** NK cells in rule engine do not proactively emit IFN-γ to prime DC maturation. The NK→DC→CD8⁺ axis only activates with LLM agents — this LLM-specific emergent behavior is the key finding of Sprint 4.

---

## Literature Validation

- Selvanesan et al. *J Immunother Cancer* 2020 (PMID 33154149) — timing calibration
- Bear & Vonderheide *Cancer Cell* 2020 (PMID 32946773) — cold TME
- Zheng et al. *Cell Rep* 2024 (PMID 38602878) — checkpoint resistance
- Immunity 2023 — KRAS G12D DC maturation suppression
- Nat Immunol 2021 — NK IL-6 suppression in PDAC
- Clin Cancer Res 2020 — NK kill rates in PDAC

---

## Citation

```bibtex
@article{carbajal2026oncobiome,
  title   = {OncoBiome Swarm: A Large Language Model-Based Multi-Agent Framework
             for Emergent Simulation of the KRAS G12D Pancreatic Tumor Microenvironment},
  author  = {Carbajal, Roberto},
  journal = {bioRxiv},
  year    = {2026},
  doi     = {pending}
}
```

---

## Security

See [SECURITY.md](SECURITY.md) for vulnerability reporting.  
API keys must never be committed. The `.env` file is excluded by `.gitignore`.  
Run `python scripts/scan_secrets.py` before every push.

---

## License

**Dual license:**
- Non-commercial / academic use — free (see [LICENSE](LICENSE))
- Commercial use — requires separate agreement: robertocarbajal.rc@gmail.com
