# OncoBiome Swarm — Estado del Proyecto (Sprint 4)

Framework de simulación multi-agente oncológica (paradigma MiroFish) aplicado
al microambiente tumoral (TME). Agentes biológicos con LLM como cerebro individual,
memoria persistente por agente, y seed biológico calibrado contra literatura
primaria KRAS G12D PDAC.

---

## Stack

- Python 3.12
- Claude Haiku 4.5 — microdecisiones de agentes (smart batch: 1 llamada/tipo/ciclo)
- Claude Opus 4.5 — análisis emergente del enjambre cada 25 ciclos
- Rule engine — decisiones biológicas deterministas $0 (validación y desarrollo)
- Plotly Dash — dashboard en tiempo real (puerto 8051)
- InMemoryStore — memoria in-process por agente (mem0 opcional)

---

## Agentes implementados

| Agente | Kill rate | Parámetros clave | Sprint |
|---|---|---|---|
| TumorCell | — | tumor_initial_energy=0.75 | 0 |
| ImmuneCell (CD8+) | 0.15 | immune_exhaustion_age=15 | 0 |
| MacrophageAgent | 0.08 (M1) | m2_threshold=0.06 | 0 |
| PhytochemicalAgent | 0.06 | phytochemical_ttl=28 | 0 |
| CytokineAgent | — | decay=0.04, sigma=1.8 | 0 |
| NKCell | 0.10 | nk_il6_threshold=0.04, exhaustion_age=20 | 4 |
| DendriticCell | — | dc_maturation_cycles=3, ifng_threshold=0.05 | 4 |

---

## Experimentos completados — Tabla maestra

### Sprint 3 — Factorial 2×3 (n=3)

| Experimento | Tipo | Ciclos | Colapso inmune (mean±SD) | CV | Coste |
|---|---|---|---|---|---|
| full_rule_engine | rule | 52 | no colapso | — | $0 |
| immune_boost_rule | rule | 52 | no colapso | — | $0 |
| combination_therapy_rule | rule | 52 | no colapso | — | $0 |
| cap80_baseline | LLM | 77 | c28.3±3.2 (61.4±7.0d) | 11.3% | ~$4.35 |
| immune_boost | LLM | 52 | c28.7±2.1 (62.1±4.5d) | 7.3% | ~$4.35 |
| combination_therapy | LLM | 52 | c29.0±7.9 (62.8±17.2d) | 27.4%* | ~$5.28 |

### Sprint 4 — NK/DC + control (n=1 rule, n=3 LLM)

| Experimento | Tipo | c52 tumor | Colapso | Coste |
|---|---|---|---|---|
| high_cd8_control_rule | rule | 17 | no colapso | $0 |
| nk_baseline_rule | rule | 63 | no colapso | $0 |
| nk_boost_rule | rule | 40 | no colapso | $0 |
| dc_baseline_rule | rule | 88 | no colapso | $0 |
| innate_adaptive_bridge_rule | rule | 25 | no colapso | $0 |
| innate_adaptive_bridge_llm | LLM n=3 | 72.7±0.6 | c32±2.6 (69.3±5.7d) CV=8.3% | ~$2.06 |

---

## 9 Hallazgos emergentes (Opus) — validados

| # | Hallazgo | Literatura | Sprint |
|---|---|---|---|
| 1 | Cold TME — exclusión espacial CD8+, IFN-γ ≈ 0 | Bear & Vonderheide 2020 | 3 |
| 2 | Immunoediting equilibrium c14–26 | Dunn et al. 2004 | 3 |
| 3 | Checkpoint resistance — "signaling into void" | Zheng Cell Rep 2024 | 3 |
| 4 | Warburg plateau — equilibrio proliferación/muerte | Efecto Warburg | 3 |
| 5 | Paradoja inmunológica — combination < immune_boost | Mecanismo M2 | 3 |
| 6 | NK exhaustion precede CD8+ (c25-30 vs c29-34, n=3) | Nat Immunol 2021 | 4 |
| 7 | DC tolerogénicas KRAS G12D (ambos paradigmas) | Immunity 2023 | 4 |
| 8 | NK dose threshold (4→8 NK: 0%→37% reducción) | Clin Cancer Res 2020 | 4 |
| 9 | TAM emergentes (Opus c25: M2 silente por VEGF) | Frontiers/Medicine 2024 | 4 |

---

## Seed biológico KRAS G12D

| Parámetro | Valor | Fuente |
|---|---|---|
| `immune_kill_rate` | 0.15 | ScienceDirect 2020 |
| `nk_kill_rate` | 0.10 | Clin Cancer Res 2020 |
| `nk_il6_suppression_threshold` | 0.04 | Nat Immunol 2021 |
| `dc_maturation_ifng_threshold` | 0.05 | Immunity 2023 |
| `m2_polarisation_il6_threshold` | 0.06 | Frontiers/Medicine 2024 |
| `cytokine_decay` | 0.04 | Estroma desmoplásico PDAC |
| Referencia celular | PANC-1 | Doubling time 52h (ATCC CRL-1469) |
| Escala biológica | 1 ciclo = 2.17 días | 52h / 24h |

---

## Tests

```bash
python3 -m pytest tests/ -q   # 178/178, ~4.5s, $0
```

---

## Seguridad pre-push

```bash
python3 scripts/_audit_pregithub.py   # auditoría completa
```

---

## Roadmap de sprints

| Sprint | Estado | Objetivo |
|---|---|---|
| 0–3 | ✅ | Framework + factorial + n=3 + 5 hallazgos |
| 4 | ✅ | NK/DC + sensitivity + RMSE + n=3 bridge (4 hallazgos nuevos) |
| 5 | Pendiente | PhysiCell 3D + apoptosis hipoxia |
| 6 | Pendiente | zAvatar scRNA-seq (TCGA-PAAD) |
| 7 | Pendiente | MiroFish closed loop (AlphaFold3 + RFdiffusion) |
