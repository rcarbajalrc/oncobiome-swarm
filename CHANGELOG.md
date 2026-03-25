# OncoBiome Swarm — CHANGELOG

All notable changes documented by sprint.

---

## Sprint 5C (2026-03-26) — Wilcoxon n=10 × 2 condiciones — COMPLETE

### Pregunta científica respondida
¿El patrón NK→CD8⁺ es estadísticamente robusto con n=10 y persiste
cuando el LLM usa etiquetas abstractas (Agent_A, Agent_B, Signal_X)?

### Experimentos ejecutados
- `bridge_n10_llm`: 10 runs con terminología biomédica completa
- `ablation_abstract_n10_llm`: 10 runs con etiquetas abstractas

### Resultados bridge_n10_llm (n=10)
| Métrica       | Valor              |
|---------------|--------------------|
| NK colapso    | 24.9 ± 3.1 (c20-31)|
| CD8+ colapso  | 31.5 ± 1.4 (c29-33)|
| Delta NK→CD8+ | 6.6 ± 2.4          |
| Tumor c52     | 72.6 ± 1.1         |
| Patrón        | 10/10 P=0.001      |
| Coste total   | $8.01              |

### Resultados ablation_abstract_n10_llm (n=10)
| Métrica       | Valor              |
|---------------|--------------------|
| NK colapso    | 25.6 ± 4.4 (c20-32)|
| CD8+ colapso  | 32.0 ± 2.6 (c28-36)|
| Delta NK→CD8+ | 6.4 ± 2.9          |
| Tumor c52     | 72.2 ± 0.6         |
| Patrón        | 10/10 P=0.001      |
| Coste total   | $6.94              |

### Comparación Wilcoxon Mann-Whitney U (bilateral)
| Métrica       | Δ medio | p-valor | Significancia |
|---------------|---------|---------|---------------|
| NK colapso    | 0.7c    | >0.05   | NS            |
| CD8+ colapso  | 0.5c    | >0.05   | NS            |
| Delta NK→CD8+ | 0.2     | >0.05   | NS            |
| Tumor c52     | 0.4     | >0.05   | NS            |

### Conclusión H1
**CONFIRMADA**: No hay diferencia significativa entre condición biomédica
y abstracta. El patrón NK→CD8⁺ emerge de la topología causal del sistema,
no del conocimiento biomédico aprendido por el LLM.

### Fenómenos Opus candidatos documentados (Runs 8-10 bridge + Runs 1-10 abstract)
- #10: Paradox fitoquímico M1 (supresión inadvertida IL-6, Run 8 bridge)
- #11: DC-mediated cytotoxic burst emergente (Run 9 bridge)
- #12: Failed immune trafficking — segregación espacial (Run 9 bridge c50)
- #13: DC tolerization by IL-6-rich niche, VEGF:IFN-γ ~25:1 (Run 10 bridge)
- Abstract: ferroptosis-like coordinated death, Darwinian editing,
  pseudoresponse, density-dependent regulation, selection bottleneck
  metastático, NK functional anergy VEGF-mediada

### Nuevos archivos
- `analysis/wilcoxon_sprint5c.py` — análisis estadístico completo
- `results/bridge_n10_results.txt` — resultados n=10 + Opus Runs 8-10
- `results/abstract_n10_results.txt` — resultados n=10 + Opus todos los runs
- `results/bridge_n10_opus_run9.txt` — Opus detallado Run 9 bridge

### Tests
- **210/210 tests passing** (sin cambios en código fuente)

### Coste Sprint 5C
- bridge_n10_llm (n=10): $8.01
- ablation_abstract_n10_llm (n=10): $6.94
- Total Sprint 5C: $14.95
- Coste acumulado proyecto: ~$60.17 USD

---

## Sprint 5B (2026-03-25) — Ablation Semántico n=3 — COMPLETE

### Pregunta científica respondida
¿El patrón persiste cuando el LLM ve etiquetas abstractas (Agent_A/B)?

### Resultado (n=3, preliminar)
H1 confirmada: Agent_A→Agent_B en 3/3 runs
- CD8+ abstracto 32.0±3.6 vs biomédico 32.0±2.6 — Δ=0 ciclos
- Infraestructura: prompts_abstract.py, null_store.py, factory.py

### Tests: 210/210 passing | Coste: ~$1.05

---

## Sprint 5A (2026-03-25) — Ablation Memoria n=3 — COMPLETE

### Resultado (n=3)
NK→CD8⁺ robusto sin memoria episódica.
CD8+ sin memoria: 32.7±0.6 vs con memoria: 32.0±2.6 (Δ=0.7c, NS)
Coste: ~$2.26

---

## Sprint 4 (2026-03-24) — NK/DC Agents + Validation — COMPLETE

### New agents
- `agents/nk_cell.py` — NKCell: kill_rate=0.10, IL-6 suppression, exhaustion
- `agents/dendritic_cell.py` — DendriticCell: tolerogenic default, IFN-γ maturation

### Emergent findings (Sprint 4)
6. NK exhaustion precedes CD8⁺ (Δ=4–9 cycles, n=3)
7. DC tolerogenic in KRAS G12D (both paradigms)
8. NK dose threshold (4→8: 0%→−37%)
9. TAM emergence (Opus c25)

### Tests: 178/178 | Cost Sprint 4: ~$18.40

---

## Sprint 3 (2026-03-24) — Reproducibility & bioRxiv — COMPLETE

- n=3 for all LLM experiments (CV 7–27%)
- bioRxiv preprint submitted
- Total cost Sprint 3: ~$3.36

---

## Sprint 2 (2026-03-23) — Factorial design complete

- combination_therapy LLM run (c20 collapse)
- Immunological paradox confirmed

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
