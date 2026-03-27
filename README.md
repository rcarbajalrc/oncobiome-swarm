# OncoBiome Swarm

**LLM-driven multi-agent simulation of the KRAS G12D pancreatic tumor microenvironment**

[![Tests](https://img.shields.io/badge/tests-210%20passing-brightgreen)]()
[![Python](https://img.shields.io/badge/python-3.12-blue)]()
[![License](https://img.shields.io/badge/license-Dual%20MIT%2FCommercial-blue)]()
[![Sprint](https://img.shields.io/badge/sprint-6%20complete-brightgreen)]()
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19226380.svg)](https://doi.org/10.5281/zenodo.19226380)
[![Cost](https://img.shields.io/badge/total%20cost-%2462%20USD-lightgrey)]()

---

## Overview

OncoBiome Swarm is a novel agent-based modeling (ABM) framework where every biological agent in the tumor microenvironment (TME) — tumor cells, CD8⁺ T lymphocytes, NK cells, dendritic cells, macrophages, phytochemicals — is driven by an independent large language model (LLM) with persistent episodic memory.

Unlike deterministic ABMs (PhysiCell, HAL, CompuCell3D), each agent reasons contextually from local cytokine gradients, interaction history, and neighbor state. This produces emergent immunosuppressive behaviors that cannot be programmed with explicit rules.

**Central finding (Sprint 5C — confirmed):** NK cell exhaustion precedes CD8⁺ collapse in 20/20 runs across semantic ablation conditions (Mann-Whitney U p=0.52 NS between biomedical and abstract labels), demonstrating that the pattern emerges from causal topology, not LLM biomedical prior knowledge.

**Sprint 6 — zAvatar TCGA-PAAD:** Biological seeds personalized from real patient expression data (177 samples, cBioPortal). HOT tumor profile (IFNG p90) shows tumor control at c6: 14 cells vs 47–53 in COLD/MEDIAN — emergent personalized response confirmed.

---

## Architecture

```
agents/          TumorCell, ImmuneCell, MacrophageAgent, PhytochemicalAgent,
                 CytokineAgent, NKCell, DendriticCell
llm/             client.py (smart batch), prompts.py, prompts_abstract.py,
                 rule_engine.py, opus_analyzer.py
simulation/      engine.py, environment.py, interactions.py, experiment_loader.py
config/          settings.py (KRAS G12D seed), biological_seed.py
memory/          inmemory_store.py, null_store.py (ablation), mem0 integration
analysis/        sprint6_tcga_download.py, sprint6_zavatar_builder.py,
                 wilcoxon_sprint5c.py, sensitivity_analysis.py
data/            tcga_paad/tme_expression.json (177 samples)
                 avatars/zavatar_profiles.json (MEDIAN/COLD/HOT)
results/         sprint6_zavatar_results.txt, ablation_r1-3_notes.txt
tests/           210 tests — biological, NK/DC, ablation, zAvatar, cost-safety
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
| Baseline (5 CD8⁺) | no collapse | c29 (62.8d) | — | >47d |
| Immune Boost (12 CD8⁺) | no collapse | c28.7 ± 2.1 (62.1 ± 4.5d) | 7.3% | >48d |
| Combination Therapy | no collapse | c29.0 ± 7.9 (62.8 ± 17.2d) | 27.4%* | >50d |

### Sprint 4 — NK/DC Innate-Adaptive Bridge (n=3)

| Condition | Rule Engine c52 | LLM c52 (n=3) | Collapse CD8⁺ |
|-----------|----------------|----------------|----------------|
| 8 CD8⁺ + 4 NK + 3 DC (bridge) | 25 (−60%) | **72.7 ± 0.6** (CV=0.8%) | **c32 ± 2.6** (69.3 ± 5.7d) |

### Sprint 5A — Memory Ablation (n=3)

NK→CD8⁺ pattern persists without episodic memory: NK c30.0±1.7 vs c26.7±2.9 with memory (Δ=2.3 cycles, less than natural run-to-run variability). CV CD8⁺ = 1.8% without memory vs 8.3% with memory — more reproducible, not less.

### Sprint 5C — Semantic Ablation (n=10, Wilcoxon formal)

Labels replaced: NK→Agent_A, CD8⁺→Agent_B, IFN-γ→Signal_X, VEGF→Signal_Y. Causal topology preserved explicitly in prompts.

| Metric | Biomedical n=10 | Abstract n=10 | Mann-Whitney U | p-value |
|--------|----------------|--------------|----------------|---------|
| NK collapse (cycle) | 24.9 ± 2.8 | 25.6 ± 4.1 | U=49 | 0.94 NS |
| CD8⁺ collapse | 31.5 ± 1.4 | 32.0 ± 2.4 | U=42 | 0.52 NS |
| Delta NK→CD8⁺ | 6.6 ± 2.3 | 6.4 ± 2.7 | U=47 | 0.82 NS |
| Pattern present | 10/10 | 10/10 | — | P=0.002 bilateral |

**H1 confirmed:** emergent dynamics arise from causal topology, not semantic associations in LLM weights.

### Sprint 6 — zAvatar TCGA-PAAD (1 run per avatar)

177 TCGA-PAAD samples downloaded via cBioPortal API. Z-scores of CD8A, NCAM1, IFNG, VEGFA, IL6, ITGAE translated to biological parameters.

| Avatar | Profile | immune_kill | nk_kill | Tumor c6 | NK collapse | CD8⁺ collapse |
|--------|---------|-------------|---------|----------|-------------|----------------|
| MEDIAN | 177-sample median | 0.142 (−5%) | 0.095 (−5%) | 53 | c25 | c33 |
| COLD | IFNG p10, VEGFA p90, IL6 p90 | 0.095 (−36%) | 0.067 (−33%) | 47 | c25 | c33 |
| HOT | IFNG p90, VEGFA p10, IL6 p10 | 0.198 (+32%) | 0.131 (+31%) | **14** | c29 | c30 |

**Key finding — emergent adaptive compensation:** COLD avatar with immune_kill_rate reduced 36% produces identical collapse timing to MEDIAN. LLM agents exhibit emergent homeostasis under parametric perturbation — not explicitly programmed.

---

## Emergent Findings

15 unprogrammed biological phenomena from LLM agent reasoning (Claude Opus 4.5):

**Sprints 0–3:** Cold TME · Immunoediting equilibrium · Checkpoint resistance · Warburg plateau · Immunological paradox

**Sprint 4:** NK exhaustion precedes CD8⁺ (Δ4–9 cycles) · DC tolerogenic default · NK dose threshold · TAM emergence

**Sprint 5:** Synchronous c46 apoptosis cascade · Ferroptosis-like pattern · Darwinian clonal editing · NK functional anergy VEGF-mediated

**Sprint 6:** DC-mediated cytotoxic burst despite unfavorable E:T ratio · Paradoxical VEGF:IFN-γ ~58:1 in HOT profile

---

## zAvatar — Patient-Personalized Simulation

Sprint 6 introduces **zAvatar**: biological seeds derived from real patient expression data.

```bash
# Download TCGA-PAAD expression data (177 samples, free API)
python3 analysis/sprint6_tcga_download.py

# Build patient avatars from z-scores
python3 analysis/sprint6_zavatar_builder.py

# Run personalized simulation
python main.py --experiment zavatar_hot_35c_llm --no-dashboard
```

Gene → parameter translation:
- `CD8A↑` → `immune_kill_rate↑`
- `NCAM1↑` → `nk_kill_rate↑`
- `IFNG↑` → `dc_maturation_ifng_threshold↓`
- `VEGFA↑` → `cytokine_decay↓`
- `IL6↑` → `m2_polarisation_il6_threshold↓`
- `CD274↑` → `immune_exhaustion_age↓`

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

# Semantic ablation — Agent_A/B abstract labels
python main.py --experiment ablation_abstract_semantics_llm --no-dashboard

# zAvatar HOT — personalized TCGA-PAAD
python main.py --experiment zavatar_hot_35c_llm --no-dashboard

# zAvatar COLD — immunosuppressed profile
python main.py --experiment zavatar_cold_35c_llm --no-dashboard

# List all 40+ experiments
python main.py --list-experiments

# Full test suite
python -m pytest tests/ -q

# Statistical analysis Sprint 5C
python3 analysis/wilcoxon_sprint5c.py
```

---

## Cost Summary

| Sprint | Content | Cost |
|--------|---------|------|
| 0–3 | Factorial 2×3, n=3, calibration | ~$3.36 |
| 4 | NK/DC bridge, sensitivity, n=3 | ~$18.40 |
| 5A | Memory ablation n=3 | ~$2.26 |
| 5B | Semantic ablation infrastructure | ~$0.70 |
| 5C | Wilcoxon n=10 bridge + abstract | ~$14.95 |
| 6 | zAvatar TCGA-PAAD (3 avatars) | ~$1.54 |
| **Total** | **Sprints 0–6** | **~$62 USD** |

Reproducible by any researcher with an Anthropic API key.

---

## Roadmap

| Sprint | Status | Content |
|--------|--------|---------|
| 0–6 | ✅ Complete | Framework + ablation + Wilcoxon + zAvatar |
| 7A | Planned | Multi-LLM (Haiku vs Sonnet vs base model) |
| 7B | Future | PhysiCell 3D + oxygen gradients |
| 8 | Future | AlphaFold3 + RFdiffusion loop |
| Wet lab | Collaboration needed | Co-culture / organoid validation |

---

## Citation

```bibtex
@misc{carbajal2026oncobiome,
  title={OncoBiome Swarm: An LLM-Agent-Based Model of the Pancreatic Tumor
         Microenvironment Reveals Emergent Immune Exhaustion Modulated by
         LLM Reasoning Capacity},
  author={Carbajal, Roberto},
  year={2026},
  doi={10.5281/zenodo.19226380},
  url={https://doi.org/10.5281/zenodo.19226380},
  note={Independent Researcher, Barcelona, Spain. Preprint v2.5, March 2026}
}
```

### Version history

| Version | DOI | Date | Notes |
|---------|-----|------|-------|
| v2.5 (current) | [10.5281/zenodo.19254913](https://doi.org/10.5281/zenodo.19254913) | March 27, 2026 | 23 emergent phenomena, TCGA-PAAD n=177 external consistency, ablation-validated |
| v2.0 | [10.5281/zenodo.19226380](https://doi.org/10.5281/zenodo.19226380) | March 26, 2026 | Initial public release |

---

## License

Dual license: MIT for academic/research use · Commercial license required for proprietary applications. See LICENSE.md.
