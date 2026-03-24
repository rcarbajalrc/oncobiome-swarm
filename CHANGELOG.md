# OncoBiome Swarm — CHANGELOG

All notable changes documented by sprint.

---

## Sprint 5 (2026-03-25) — Ablation Study: Memory Episódica — COMPLETE

### Pregunta científica respondida
¿Los fenómenos emergentes identificados en Sprint 4 dependen de la memoria
episódica de los agentes, o son robustos sin ella?

### Resultado (n=3, directional)
NK exhaustion precede a CD8⁺ collapse en 3/3 runs sin memoria:
- NK colapso: c26/c29/c32 → media 29.0±3.0
- CD8⁺ colapso: c33/c33/c32 → media 32.7±0.6 (CV=1.8%)
- Tumor c52: 72/72/72 → media 72.0±0.0

Comparación con Sprint 4 (con memoria, n=3):
- NK colapso con memoria: c26.7±2.9 → sin memoria: c29.0±3.0 (Δ=2.3c)
- CD8⁺ colapso con memoria: c32.0±2.6 → sin memoria: c32.7±0.6 (Δ=0.7c)
- Diferencia menor que variabilidad natural → fenómenos ROBUSTOS

### Conclusión
Los fenómenos emergentes emergen del contexto local inmediato (citoquinas,
vecinos, energía del ciclo actual), no de la historia acumulada.
Responde directamente a la crítica del revisor sobre "plausibilidad narrativa".

### Nuevos archivos
- `memory/null_store.py` — NullMemoryStore: descarta toda memoria
- `memory/factory.py` — soporte MEMORY_MODE=null
- `tests/test_ablation_memory.py` — 14 tests del ablation
- `experiments.yaml` — 3 experimentos ablation añadidos
- `simulation/experiment_loader.py` — mapping memory_mode → MEMORY_MODE env
- `results/ablation_r1_notes.txt` — resultados R1
- `results/ablation_r2_notes.txt` — resultados R1+R2 comparados

### Tests
- **192/192 tests passing** (14 nuevos tests ablation)

### Coste Sprint 5
- ablation_no_memory_llm R1: ~$0.66
- ablation_no_memory_llm R2: ~$0.90
- ablation_no_memory_llm R3: ~$0.70
- Total Sprint 5: ~$2.26
- Coste acumulado proyecto: ~$23.76

---

## Sprint 4 (2026-03-24) — NK/DC Agents + Validation — COMPLETE

### New agents
- `agents/nk_cell.py` — NKCell: kill_rate=0.10, IL-6 suppression, exhaustion
- `agents/dendritic_cell.py` — DendriticCell: tolerogenic default, IFN-γ maturation

### New interactions
- `_nk_attacks()`, `_dc_maturation()`, `_dc_activates_cd8()`

### Config
- NK/DC parameter blocks in settings.py
- N_NK_CELLS, N_DENDRITIC_CELLS env mapping

### Experiments
- 7 new NK/DC experiments including high_cd8_control_rule
- innate_adaptive_bridge_llm n=3: tumor 72.7±0.6, collapse c32±2.6 (CV=8.3%)

### Quantitative validation
- sensitivity_analysis.py: OAT + 3×3×3 factorial (34 runs, $0)
- rmse_validation.py: 4 RMSE metrics

### Tests
- 178/178 tests passing (Sprint 4)

### Emergent findings (Sprint 4)
6. NK exhaustion precedes CD8⁺ (Δ=4–9 cycles, n=3)
7. DC tolerogenic in KRAS G12D (both paradigms)
8. NK dose threshold (4→8: 0%→−37%)
9. TAM emergence (Opus c25)

### Cost Sprint 4: ~$18.40

---

## Sprint 3 (2026-03-24) — Reproducibility & bioRxiv — COMPLETE

- n=3 for all LLM experiments (CV 7–27%)
- bioRxiv preprint submitted
- .gitignore, scan_secrets.py, load_dotenv fix
- Total cost Sprint 3: ~$3.36

---

## Sprint 2 (2026-03-23) — Factorial design complete

- combination_therapy LLM run (c20 collapse)
- Immunological paradox confirmed
- Factorial 2×3 fully closed

---

## Sprint 1 (2026-03-23) — Biological calibration

- KRAS G12D seed calibrated (5 parameters)
- PANC-1 doubling time 52h → 1 cycle = 2.17 days
- Validation vs Selvanesan 2020: <5% timing deviation

---

## Sprint 0 (2026-03-21) — Framework

- LLM-ABM core agents
- Smart batching (85% cost reduction)
- Rule engine fallback ($0)
- Plotly Dash dashboard
- MCP server
- 138 tests
