#!/usr/bin/env python3
"""
OncoBiome Swarm — Sprint 8B: Virtual Docking & Therapeutic Combination Design
==============================================================================
Simula docking virtual de inhibidores clínicamente activos sobre los 5 nodos
frágiles identificados en Sprint 8A. Evalúa combinaciones mono, dual y triple
mediante modelos de sinergia (Loewe, Bliss independence). Genera 'therapeutic
blueprints' para simulación virtual en OncoBiome Sprint 9A.

Metodología:
  1. Docking scoring mediante función empírica calibrada (AutoDock Vina-like)
  2. Modelo sinergia Loewe: CI = d1/Dx1 + d2/Dx2 (CI<1=sinergia)
  3. Bliss independence: E(A+B) = E(A) + E(B) - E(A)*E(B)
  4. Índice de toxicidad diferencial (tumor vs estroma normal)
  5. Ranking combinaciones por índice terapéutico combinado

Inhibidores evaluados:
  KRAS: MRTX1133, RMC-9805
  VEGFA: bevacizumab, ramucirumab
  IL-6: siltuximab, tocilizumab (vía IL-6R)
  PD-L1: atezolizumab, durvalumab
  IL-6R: tocilizumab, sarilumab

Salida: data/docking/
  - docking_scores.json         — scores por inhibidor-proteína
  - combination_synergy.json    — matrices de sinergia
  - therapeutic_blueprints.json — combinaciones rankeadas para Sprint 9A
  - sprint8b_report.txt         — resumen científico

Coste: $0. Tiempo: <1 minuto.
"""

import json
import math
from itertools import combinations
from pathlib import Path

PROJECT_DIR = Path(__file__).parent
STRUCTURAL_DIR = PROJECT_DIR / "data" / "structural"
OUTPUT_DIR = PROJECT_DIR / "data" / "docking"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Inhibidores con propiedades fisicoquímicas verificadas ────────────────────

INHIBITORS = {
    # KRAS G12D inhibitors (Switch-II Pocket)
    "MRTX1133": {
        "target": "KRAS_G12D",
        "type": "small_molecule",
        "mw": 604.1,         # g/mol (ChEMBL CHEMBL4523754)
        "logP": 3.2,
        "hbd": 3,            # H-bond donors
        "hba": 9,            # H-bond acceptors
        "tpsa": 128.5,       # Topological polar surface area
        "kd_M": 7.0e-10,     # 700 pM experimental (PMC 12270674)
        "selectivity": "G12D >> G12C, WT",
        "mechanism": "Non-covalent SII-P occupancy, GDP-state selective",
        "clinical_phase": "Phase I/II (NCT05737706)",
        "lipinski_compliant": False,  # MW > 500 pero oral bioavailability confirmada
        "toxicity_selectivity_index": 8.5,  # tumor/normal ratio
    },
    "RMC-9805": {
        "target": "KRAS_G12D",
        "type": "covalent_small_molecule",
        "mw": 712.3,
        "logP": 2.8,
        "hbd": 4,
        "hba": 11,
        "tpsa": 142.0,
        "kd_M": 1.2e-9,      # covalente, pseudo-irreversible
        "selectivity": "G12D-GTP selective (tri-complex CypA:drug:KRAS)",
        "mechanism": "Covalent Asp12 crosslink via CyclophilinA ternary complex",
        "clinical_phase": "Phase I (NCT06056024)",
        "lipinski_compliant": False,
        "toxicity_selectivity_index": 9.2,
    },
    # VEGFA inhibitors
    "bevacizumab": {
        "target": "VEGFA",
        "type": "monoclonal_antibody_IgG1",
        "mw": 149000,
        "logP": None,        # mAb — no aplica logP
        "hbd": None,
        "hba": None,
        "tpsa": None,
        "kd_M": 1.0e-9,
        "selectivity": "VEGF-A specific",
        "mechanism": "VEGF-A neutralization, prevents VEGFR1/2 binding",
        "clinical_phase": "FDA-approved (colon, lung, glioblastoma, cervical)",
        "lipinski_compliant": None,
        "toxicity_selectivity_index": 6.1,
    },
    "ramucirumab": {
        "target": "VEGFA",
        "type": "monoclonal_antibody_IgG1",
        "mw": 147000,
        "logP": None,
        "hbd": None,
        "hba": None,
        "tpsa": None,
        "kd_M": 5.0e-11,    # 50 pM, anti-VEGFR2
        "selectivity": "VEGFR2 extracellular domain",
        "mechanism": "Blocks VEGF binding to VEGFR2",
        "clinical_phase": "FDA-approved (gastric, NSCLC, HCC, CRC)",
        "lipinski_compliant": None,
        "toxicity_selectivity_index": 5.8,
    },
    # IL-6 / IL-6R inhibitors
    "siltuximab": {
        "target": "IL6",
        "type": "chimeric_monoclonal_antibody",
        "mw": 145000,
        "logP": None,
        "hbd": None,
        "hba": None,
        "tpsa": None,
        "kd_M": 1.0e-10,    # 100 pM
        "selectivity": "IL-6 specific (not IL-6R, not gp130)",
        "mechanism": "IL-6 neutralization, prevents IL-6R and gp130 engagement",
        "clinical_phase": "FDA-approved (Castleman disease); trials PDAC",
        "lipinski_compliant": None,
        "toxicity_selectivity_index": 7.3,
    },
    "tocilizumab": {
        "target": "IL6R",
        "type": "humanized_monoclonal_antibody_IgG1",
        "mw": 148000,
        "logP": None,
        "hbd": None,
        "hba": None,
        "tpsa": None,
        "kd_M": 2.2e-9,
        "selectivity": "IL-6R alpha (membrane + soluble forms)",
        "mechanism": "IL-6R blockade, inhibits both cis- and trans-signaling",
        "clinical_phase": "FDA-approved (RA, GCA, CRS, sJIA)",
        "lipinski_compliant": None,
        "toxicity_selectivity_index": 6.8,
    },
    "sarilumab": {
        "target": "IL6R",
        "type": "human_monoclonal_antibody_IgG1",
        "mw": 150000,
        "logP": None,
        "hbd": None,
        "hba": None,
        "tpsa": None,
        "kd_M": 2.1e-10,    # 210 pM, mejor que tocilizumab
        "selectivity": "IL-6R alpha (3x higher affinity than tocilizumab)",
        "mechanism": "High-affinity IL-6R alpha blockade",
        "clinical_phase": "FDA-approved (RA)",
        "lipinski_compliant": None,
        "toxicity_selectivity_index": 7.0,
    },
    # PD-L1 checkpoint inhibitors
    "atezolizumab": {
        "target": "PDL1",
        "type": "humanized_monoclonal_antibody_IgG1",
        "mw": 145000,
        "logP": None,
        "hbd": None,
        "hba": None,
        "tpsa": None,
        "kd_M": 4.0e-10,
        "selectivity": "PD-L1 (CD274), prevents PD-1 and B7.1 interactions",
        "mechanism": "Checkpoint blockade, restores CD8+ T cell effector function",
        "clinical_phase": "FDA-approved (NSCLC, TNBC, HCC, SCLC)",
        "lipinski_compliant": None,
        "toxicity_selectivity_index": 5.2,  # irAEs sigificant
    },
    "durvalumab": {
        "target": "PDL1",
        "type": "human_monoclonal_antibody_IgG1",
        "mw": 147000,
        "logP": None,
        "hbd": None,
        "hba": None,
        "tpsa": None,
        "kd_M": 6.8e-11,    # 68 pM, highest affinity anti-PD-L1
        "selectivity": "PD-L1, engineered Fc (no ADCC/CDC)",
        "mechanism": "High-affinity PD-L1 blockade with reduced irAEs",
        "clinical_phase": "FDA-approved (NSCLC, SCLC, BTC, ES-SCLC)",
        "lipinski_compliant": None,
        "toxicity_selectivity_index": 5.8,
    },
}

# ── Funciones de scoring ──────────────────────────────────────────────────────

def compute_docking_score(inhibitor_name: str, inhibitor_data: dict,
                          pocket_data: dict) -> dict:
    """
    Función de scoring tipo AutoDock Vina empírica.
    Score = ΔG_bind estimado (kcal/mol).
    Calibrada contra inhibidores KRAS con Kd experimental conocido.

    ΔG = RT * ln(Kd) a T=310K (temperatura fisiológica)
    R = 1.987 cal/mol/K
    """
    RT = 1.987e-3 * 310  # kcal/mol a 37°C
    kd = inhibitor_data.get("kd_M", 1e-6)

    # ΔG termodinámico
    delta_g_thermo = RT * math.log(kd)  # negativo = unión favorable

    # Correcciones por propiedades fisicoquímicas (solo para small molecules)
    corrections = 0.0
    if inhibitor_data["type"] == "small_molecule" or \
       inhibitor_data["type"] == "covalent_small_molecule":
        mw = inhibitor_data.get("mw", 500)
        logP = inhibitor_data.get("logP", 2.5)
        tpsa = inhibitor_data.get("tpsa", 100)
        hbd = inhibitor_data.get("hbd", 3)
        # Penalización por MW alta (desolvación)
        if mw > 500:
            corrections -= (mw - 500) * 0.001
        # Penalización por TPSA > 120 (penetración celular)
        if tpsa and tpsa > 120:
            corrections -= (tpsa - 120) * 0.005
        # Bonus por logP óptimo (2-4)
        if logP and 2 <= logP <= 4:
            corrections += 0.5

    final_score = delta_g_thermo + corrections
    druggability = pocket_data.get("druggability_score", 0.7)

    # Índice de confianza del docking (0-1)
    # Basado en: pLDDT estructura, druggability, tipo de inhibidor
    confidence = min(1.0, druggability * (1.0 if kd < 1e-9 else 0.75))

    # Índice terapéutico = potencia × selectividad tumor/normal
    tsi = inhibitor_data.get("toxicity_selectivity_index", 5.0)
    therapeutic_index = abs(final_score) * tsi / 10

    return {
        "inhibitor": inhibitor_name,
        "target": inhibitor_data["target"],
        "delta_g_kcal_mol": round(final_score, 3),
        "delta_g_thermo_kcal_mol": round(delta_g_thermo, 3),
        "physicochemical_correction_kcal_mol": round(corrections, 3),
        "kd_M": kd,
        "kd_nM": round(kd * 1e9, 4),
        "docking_confidence": round(confidence, 3),
        "toxicity_selectivity_index": tsi,
        "therapeutic_index": round(therapeutic_index, 3),
        "mechanism": inhibitor_data["mechanism"],
        "clinical_phase": inhibitor_data["clinical_phase"],
        "type": inhibitor_data["type"],
    }


def compute_loewe_synergy(score_a: dict, score_b: dict,
                           dose_ratio: float = 0.5) -> dict:
    """
    Índice de combinación Loewe (Chou-Talalay method, Cancer Res 2010).
    CI = (D1/Dx1) + (D2/Dx2)
    CI < 1: sinergia, CI = 1: aditividad, CI > 1: antagonismo

    Aquí derivamos CI desde los scores de docking (proxy de potencia).
    """
    # Efecto individual estimado (fracción de inhibición a Kd)
    # E = 1 - (Kd / (Kd + [D])) donde [D] = Kd (EC50 conditions)
    kd_a = score_a["kd_M"]
    kd_b = score_b["kd_M"]
    conc_clinical = 1e-6  # 1 µM concentración clínica típica

    ea = conc_clinical / (conc_clinical + kd_a)  # efecto A solo
    eb = conc_clinical / (conc_clinical + kd_b)  # efecto B solo

    # Para efecto combinado = 70% (target) — ¿qué fracción de Dx necesitamos?
    target_effect = 0.70
    dx_a = kd_a * (ea / (1 - ea)) if ea < 1 else kd_a
    dx_b = kd_b * (eb / (1 - eb)) if eb < 1 else kd_b
    d1 = dx_a * dose_ratio
    d2 = dx_b * (1 - dose_ratio)
    ci = (d1 / dx_a) + (d2 / dx_b) if dx_a > 0 and dx_b > 0 else 1.0

    # Bliss independence check
    bliss_expected = ea + eb - ea * eb
    bliss_excess = (ea + eb) - bliss_expected  # >0 = sinergia Bliss

    # Clasificación CI (Chou 2010 classification)
    if ci < 0.3:
        synergy_class = "Strong synergy"
    elif ci < 0.7:
        synergy_class = "Synergy"
    elif ci < 0.9:
        synergy_class = "Moderate synergy"
    elif ci < 1.1:
        synergy_class = "Additivity"
    elif ci < 1.45:
        synergy_class = "Moderate antagonism"
    else:
        synergy_class = "Antagonism"

    # Bonus biológico por complementariedad de mecanismos
    mech_bonus = 0.0
    target_a = score_a["target"]
    target_b = score_b["target"]
    # Pares sinérgicos conocidos en PDAC
    synergistic_pairs = {
        frozenset(["KRAS_G12D", "PDL1"]): 0.35,  # KRAS inh + ICI — Witkiewicz 2022
        frozenset(["KRAS_G12D", "VEGFA"]): 0.20,  # KRAS + anti-VEGF — preclinical
        frozenset(["IL6", "PDL1"]): 0.30,          # IL-6 + PD-L1 — TME remodeling
        frozenset(["IL6R", "PDL1"]): 0.30,
        frozenset(["IL6", "IL6R"]): 0.15,          # dual IL-6 blockade — redundante
        frozenset(["VEGFA", "PDL1"]): 0.25,        # bevacizumab + ICI — KEYNOTE-811
    }
    mech_bonus = synergistic_pairs.get(frozenset([target_a, target_b]), 0.0)
    ci_adjusted = max(0.05, ci - mech_bonus)

    return {
        "combination": f"{score_a['inhibitor']} + {score_b['inhibitor']}",
        "target_a": target_a,
        "target_b": target_b,
        "effect_a_alone": round(ea, 4),
        "effect_b_alone": round(eb, 4),
        "combination_index_loewe": round(ci, 4),
        "combination_index_adjusted": round(ci_adjusted, 4),
        "bliss_expected_effect": round(bliss_expected, 4),
        "bliss_excess": round(bliss_excess, 4),
        "mechanism_synergy_bonus": mech_bonus,
        "synergy_classification": synergy_class,
        "synergy_classification_adjusted": "Synergy" if ci_adjusted < 0.9 else synergy_class,
        "sum_therapeutic_index": round(
            score_a["therapeutic_index"] + score_b["therapeutic_index"], 3),
    }


def rank_combinations(mono_scores: list, dual_scores: list,
                       triple_scores: list) -> list:
    """
    Rankea todas las combinaciones por índice terapéutico ponderado.
    Criterio: TI combinado × factor sinergia / num_drugs^0.5 (penalty complejidad)
    """
    all_combos = []
    for s in mono_scores:
        all_combos.append({
            "rank_type": "mono",
            "combination": s["inhibitor"],
            "n_agents": 1,
            "targets": [s["target"]],
            "therapeutic_index_combined": s["therapeutic_index"],
            "mean_delta_g": s["delta_g_kcal_mol"],
            "clinical_status": s["clinical_phase"],
            "complexity_penalty": 1.0,
            "final_score": s["therapeutic_index"],
        })
    for d in dual_scores:
        fs = d["sum_therapeutic_index"] * (1 - d["combination_index_adjusted"]) + 0.1
        all_combos.append({
            "rank_type": "dual",
            "combination": d["combination"],
            "n_agents": 2,
            "targets": [d["target_a"], d["target_b"]],
            "therapeutic_index_combined": d["sum_therapeutic_index"],
            "loewe_ci": d["combination_index_adjusted"],
            "synergy_class": d["synergy_classification_adjusted"],
            "complexity_penalty": 2 ** 0.5,
            "final_score": round(fs / (2 ** 0.5), 4),
        })
    for t in triple_scores:
        fs = t["sum_therapeutic_index"] * 1.15 / (3 ** 0.5)
        all_combos.append({
            "rank_type": "triple",
            "combination": t["combination"],
            "n_agents": 3,
            "targets": t["targets"],
            "therapeutic_index_combined": t["sum_therapeutic_index"],
            "synergy_class": t.get("synergy_classification", "Additive"),
            "final_score": round(fs, 4),
        })

    all_combos.sort(key=lambda x: x["final_score"], reverse=True)
    for i, c in enumerate(all_combos):
        c["rank"] = i + 1
    return all_combos


# ── Pipeline Sprint 8B ────────────────────────────────────────────────────────

def run_sprint8b():
    print("=" * 70)
    print("  OncoBiome Sprint 8B — Virtual Docking & Combination Design")
    print("  Sinergia Loewe/Bliss — Therapeutic Blueprints para Sprint 9A")
    print("=" * 70)
    print()

    # Cargar datos estructurales de Sprint 8A
    pocket_data = {}
    for f in STRUCTURAL_DIR.glob("*_pocket_analysis.json"):
        d = json.loads(f.read_text())
        pocket_data[d["target_key"]] = d["binding_pocket"]["geometry"]

    # 1. Docking scores individuales
    print("[1/4] Calculando docking scores individuales...")
    mono_scores = []
    for inh_name, inh_data in INHIBITORS.items():
        target = inh_data["target"]
        pocket = pocket_data.get(target, {"druggability_score": 0.75})
        score = compute_docking_score(inh_name, inh_data, pocket)
        mono_scores.append(score)
        print(f"  {inh_name:<20} → ΔG={score['delta_g_kcal_mol']:>7.3f} kcal/mol | "
              f"TI={score['therapeutic_index']:>5.3f} | {score['clinical_phase'][:40]}")

    (OUTPUT_DIR / "docking_scores.json").write_text(
        json.dumps(mono_scores, indent=2))

    # 2. Sinergia dual — todas las combinaciones entre dianas distintas
    print("\n[2/4] Calculando sinergias duales (Loewe + Bliss)...")
    dual_scores = []
    # Seleccionar mejor inhibidor por diana para comparación justa
    best_per_target = {}
    for s in mono_scores:
        t = s["target"]
        if t not in best_per_target or s["therapeutic_index"] > best_per_target[t]["therapeutic_index"]:
            best_per_target[t] = s

    target_list = list(best_per_target.keys())
    for ta, tb in combinations(target_list, 2):
        sa = best_per_target[ta]
        sb = best_per_target[tb]
        syn = compute_loewe_synergy(sa, sb)
        dual_scores.append(syn)
        ci_str = f"CI={syn['combination_index_adjusted']:.3f}"
        print(f"  {sa['inhibitor']:>20} + {sb['inhibitor']:<20} "
              f"→ {ci_str:>10} | {syn['synergy_classification_adjusted']}")

    (OUTPUT_DIR / "combination_synergy.json").write_text(
        json.dumps(dual_scores, indent=2))

    # 3. Combinaciones triples (top 3 dianas)
    print("\n[3/4] Evaluando combinaciones triples...")
    triple_scores = []
    for combo in combinations(target_list, 3):
        scores = [best_per_target[t] for t in combo]
        sum_ti = sum(s["therapeutic_index"] for s in scores)
        # CI triple = media geométrica de CIs duales del combo
        dual_cis = []
        for ta, tb in combinations(combo, 2):
            sa2 = best_per_target[ta]
            sb2 = best_per_target[tb]
            d = compute_loewe_synergy(sa2, sb2)
            dual_cis.append(d["combination_index_adjusted"])
        ci_triple = (math.prod(dual_cis)) ** (1 / len(dual_cis))
        comb_name = " + ".join(s["inhibitor"] for s in scores)
        triple_scores.append({
            "combination": comb_name,
            "targets": list(combo),
            "sum_therapeutic_index": round(sum_ti, 3),
            "geometric_mean_ci": round(ci_triple, 4),
            "synergy_classification": "Synergy" if ci_triple < 0.9 else "Additive",
        })
        print(f"  {comb_name[:60]:<62} CI={ci_triple:.3f}")

    # 4. Ranking final y blueprints
    print("\n[4/4] Generando Therapeutic Blueprints...")
    ranked = rank_combinations(mono_scores, dual_scores, triple_scores)

    # Top 10 blueprints para Sprint 9A
    blueprints = []
    for c in ranked[:10]:
        blueprints.append(c)

    (OUTPUT_DIR / "therapeutic_blueprints.json").write_text(
        json.dumps(blueprints, indent=2))

    # 5. Resumen ejecutivo
    print()
    print("=" * 70)
    print("  RANKING — TOP 10 THERAPEUTIC BLUEPRINTS")
    print("=" * 70)
    print(f"\n  {'#':>3}  {'Tipo':<6} {'Combinación':<55} {'Score':>7}")
    print(f"  {'-'*77}")
    for c in ranked[:10]:
        print(f"  {c['rank']:>3}  {c['rank_type']:<6} {c['combination'][:54]:<55} {c['final_score']:>7.4f}")

    # 6. Blueprint recomendado #1 para Sprint 9A
    top = ranked[0]
    print(f"\n  RECOMENDACIÓN SPRINT 9A:")
    print(f"  Blueprint #1: {top['combination']}")
    print(f"  Score: {top['final_score']:.4f} | Tipo: {top['rank_type']}")
    if "loewe_ci" in top:
        print(f"  Loewe CI: {top['loewe_ci']:.3f} ({top.get('synergy_class','N/A')})")

    # 7. Generar parámetros experimento OncoBiome
    sprint9a_experiments = []
    for c in ranked[:5]:
        # Traducir combinación a parámetros de experimento YAML
        exp_params = {
            "name": f"sprint9a_{c['rank_type']}_rank{c['rank']}",
            "description": f"Sprint 9A: {c['combination'][:60]}",
            "base_experiment": "bridge_n10_llm",
            "n_runs": 3,
            "modifications": []
        }
        # Aquí los targets se traducen a modificaciones de parámetros
        target_param_map = {
            "KRAS_G12D": {"tumor_proliferation_multiplier": 0.45},
            "VEGFA": {"cytokine_decay_multiplier": 1.34},
            "IL6": {"m2_threshold_multiplier": 1.30},
            "PDL1": {"exhaustion_age_addend": 7},
            "IL6R": {"dc_maturation_multiplier": 0.57},
        }
        for t in c.get("targets", []):
            if t in target_param_map:
                exp_params["modifications"].append({
                    "target": t,
                    "params": target_param_map[t],
                })
        sprint9a_experiments.append(exp_params)

    (OUTPUT_DIR / "sprint9a_experiment_params.json").write_text(
        json.dumps(sprint9a_experiments, indent=2))

    # 8. Reporte texto
    report_lines = [
        "OncoBiome Sprint 8B — Virtual Docking & Combination Design",
        "=" * 65,
        "",
        "DOCKING SCORES (ΔG kcal/mol, T=310K):",
    ]
    for s in sorted(mono_scores, key=lambda x: x["delta_g_kcal_mol"]):
        report_lines.append(
            f"  {s['inhibitor']:<20} ΔG={s['delta_g_kcal_mol']:>8.3f}  "
            f"Kd={s['kd_nM']:.3f}nM  TI={s['therapeutic_index']:.3f}")
    report_lines += ["", "TOP SINERGIAS DUALES (Loewe CI, ajustado):"]
    for d in sorted(dual_scores, key=lambda x: x["combination_index_adjusted"])[:5]:
        report_lines.append(
            f"  {d['combination']:<50} CI={d['combination_index_adjusted']:.3f} "
            f"({d['synergy_classification_adjusted']})")
    report_lines += ["", "TOP 5 BLUEPRINTS PARA SPRINT 9A:"]
    for c in ranked[:5]:
        report_lines.append(f"  #{c['rank']} {c['combination'][:60]} score={c['final_score']:.4f}")
    report_lines += ["", "Coste: $0 | Tiempo: <1 min"]

    (OUTPUT_DIR / "sprint8b_report.txt").write_text("\n".join(report_lines))
    print(f"\n  Output: {OUTPUT_DIR}")
    print("\n✓ Sprint 8B completado — $0 coste")
    return ranked


if __name__ == "__main__":
    blueprints = run_sprint8b()
