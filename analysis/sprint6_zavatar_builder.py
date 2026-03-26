"""
OncoBiome Sprint 6 — zAvatar Builder
Traduce perfil de expresión génica TCGA-PAAD → parámetros OncoBiome
Crea avatares personalizados por paciente (o cohort median)
"""

import json
import math
import os

# ── Cargar datos TCGA descargados ─────────────────────────────
with open("data/tcga_paad/tme_expression.json") as f:
    tcga = json.load(f)

gene_expr = tcga["gene_expression"]

def mean(x): return sum(x)/len(x) if x else 0
def std(x):
    if not x: return 0
    m = mean(x)
    return math.sqrt(sum((v-m)**2 for v in x)/len(x))
def percentile(x, p):
    s = sorted(x)
    idx = (len(s)-1) * p / 100
    lo, hi = int(idx), min(int(idx)+1, len(s)-1)
    return s[lo] + (s[hi]-s[lo]) * (idx-lo)

# ── Parámetros base OncoBiome (seed Sprint 4) ─────────────────
BASE_PARAMS = {
    "immune_kill_rate":             0.15,
    "nk_kill_rate":                 0.10,
    "nk_il6_suppression_threshold": 0.04,
    "dc_maturation_ifng_threshold": 0.05,
    "m2_polarisation_il6_threshold":0.06,
    "cytokine_decay":               0.04,
    "tumor_initial_energy":         0.75,
    "immune_exhaustion_age":        15,
    "dc_maturation_cycles":         3,
}

# ── Función de traducción z-score → parámetro ─────────────────
def zscore_to_param(zscore, base, scale=0.3, min_val=None, max_val=None):
    """
    Modula el parámetro base según el z-score del gen.
    zscore > 0: gen sobre-expresado → efecto biológico potenciado
    zscore < 0: gen sub-expresado → efecto biológico reducido
    scale: magnitud del cambio por unidad de z (default 30%)
    """
    factor = 1 + (zscore * scale)
    factor = max(0.3, min(3.0, factor))  # clamp 30%-300% del base
    val = base * factor
    if min_val is not None: val = max(min_val, val)
    if max_val is not None: val = min(max_val, val)
    return round(val, 4)

def build_zavatar(patient_zscores, patient_id="COHORT_MEDIAN"):
    """
    Construye un avatar personalizado a partir de z-scores de expresión génica.
    
    Lógica de traducción:
    - IFNG↑ → immune_kill_rate↑ (CD8+ más activos), dc_threshold↓ (DCs se maturan antes)
    - CD8A↑ → immune_kill_rate↑
    - NCAM1↑ → nk_kill_rate↑
    - VEGFA↑ → cytokine_decay↓ (VEGF persiste), m2_threshold↓ (M2 más fácil)
    - IL6↑   → m2_threshold↓, nk_il6_suppression↓ (NK más suprimidas)
    - ITGAE↑ → dc_maturation_cycles↓ (DCs maduran más rápido)
    - CD274↑ → immune_exhaustion_age↓ (agotamiento más rápido)
    - HAVCR2↑→ immune_exhaustion_age↓ (TIM-3, agotamiento)
    """
    gz = patient_zscores
    
    ifng   = gz.get("IFNG",   0)
    vegfa  = gz.get("VEGFA",  0)
    il6    = gz.get("IL6",    0)
    cd8a   = gz.get("CD8A",   0)
    ncam1  = gz.get("NCAM1",  0)
    itgae  = gz.get("ITGAE",  0)
    cd274  = gz.get("CD274",  0)
    havcr2 = gz.get("HAVCR2", 0)

    # immune_kill_rate: combinación IFNG + CD8A (ambos potencian citotoxicidad)
    immune_signal = (ifng + cd8a) / 2
    immune_kill = zscore_to_param(immune_signal, BASE_PARAMS["immune_kill_rate"],
                                  scale=0.25, min_val=0.05, max_val=0.35)

    # nk_kill_rate: NCAM1 (marcador NK) + IFNG
    nk_signal = (ncam1 + ifng * 0.5) / 1.5
    nk_kill = zscore_to_param(nk_signal, BASE_PARAMS["nk_kill_rate"],
                              scale=0.25, min_val=0.03, max_val=0.25)

    # nk_il6_suppression_threshold: IL6↑ → threshold↓ (NK se suprimen antes)
    nk_il6 = zscore_to_param(-il6, BASE_PARAMS["nk_il6_suppression_threshold"],
                              scale=0.2, min_val=0.01, max_val=0.10)

    # dc_maturation_ifng_threshold: IFNG↑ → threshold↓ (DCs maduran antes)
    dc_ifng = zscore_to_param(-ifng, BASE_PARAMS["dc_maturation_ifng_threshold"],
                               scale=0.2, min_val=0.01, max_val=0.12)

    # m2_polarisation: IL6↑ + VEGFA↑ → threshold↓ (M2 más fácil)
    m2_signal = (il6 + vegfa) / 2
    m2_thresh = zscore_to_param(-m2_signal, BASE_PARAMS["m2_polarisation_il6_threshold"],
                                 scale=0.2, min_val=0.02, max_val=0.15)

    # cytokine_decay: VEGFA↑ → decay↓ (VEGF persiste más)
    cyt_decay = zscore_to_param(-vegfa, BASE_PARAMS["cytokine_decay"],
                                 scale=0.2, min_val=0.01, max_val=0.10)

    # immune_exhaustion_age: CD274↑ + HAVCR2↑ → age↓ (agotamiento más rápido)
    exhaust_signal = (cd274 + havcr2) / 2
    exhaust_age = int(zscore_to_param(-exhaust_signal, BASE_PARAMS["immune_exhaustion_age"],
                                      scale=0.2, min_val=5, max_val=30))

    # dc_maturation_cycles: ITGAE↑ → cycles↓ (DCs más activas)
    dc_cycles = max(1, int(zscore_to_param(-itgae, BASE_PARAMS["dc_maturation_cycles"],
                                           scale=0.2, min_val=1, max_val=6)))

    avatar = {
        "patient_id": patient_id,
        "source": "TCGA-PAAD",
        "gene_zscores": gz,
        "params": {
            "immune_kill_rate":              immune_kill,
            "nk_kill_rate":                  nk_kill,
            "nk_il6_suppression_threshold":  nk_il6,
            "dc_maturation_ifng_threshold":  dc_ifng,
            "m2_polarisation_il6_threshold": m2_thresh,
            "cytokine_decay":                cyt_decay,
            "tumor_initial_energy":          BASE_PARAMS["tumor_initial_energy"],
            "immune_exhaustion_age":         exhaust_age,
            "dc_maturation_cycles":          dc_cycles,
        },
        "delta_from_base": {}
    }

    # Calcular deltas vs base
    for k, v in avatar["params"].items():
        base = BASE_PARAMS.get(k, v)
        delta_pct = ((v - base) / base * 100) if base != 0 else 0
        avatar["delta_from_base"][k] = round(delta_pct, 1)

    return avatar

# ── Crear avatares ─────────────────────────────────────────────
print("=" * 65)
print("  OncoBiome Sprint 6 — zAvatar Builder")
print("=" * 65)

# 1. Avatar cohort median (todos los KRAS G12D TCGA-PAAD)
print("\n[1] Avatar COHORT_MEDIAN (177 pacientes TCGA-PAAD)...")
median_scores = {
    gene: percentile(vals, 50)
    for gene, vals in gene_expr.items()
    if vals
}
avatar_median = build_zavatar(median_scores, "TCGA_PAAD_MEDIAN")

# 2. Avatar "cold tumor" (IFNG bajo, VEGFA alto, IL6 alto)
print("[2] Avatar COLD_TUMOR (IFNG p10, VEGFA p90, IL6 p90)...")
cold_scores = {
    "IFNG":  percentile(gene_expr["IFNG"],  10),
    "VEGFA": percentile(gene_expr["VEGFA"], 90),
    "IL6":   percentile(gene_expr["IL6"],   90),
    "CD8A":  percentile(gene_expr["CD8A"],  10),
    "NCAM1": percentile(gene_expr["NCAM1"], 10),
    "ITGAE": percentile(gene_expr["ITGAE"], 10),
    "CD274": percentile(gene_expr["CD274"], 90),
    "HAVCR2":percentile(gene_expr["HAVCR2"],90),
    "KRAS":  percentile(gene_expr["KRAS"],  75),
}
avatar_cold = build_zavatar(cold_scores, "COLD_TUMOR_PROFILE")

# 3. Avatar "hot tumor" (IFNG alto, VEGFA bajo, IL6 bajo)
print("[3] Avatar HOT_TUMOR (IFNG p90, VEGFA p10, IL6 p10)...")
hot_scores = {
    "IFNG":  percentile(gene_expr["IFNG"],  90),
    "VEGFA": percentile(gene_expr["VEGFA"], 10),
    "IL6":   percentile(gene_expr["IL6"],   10),
    "CD8A":  percentile(gene_expr["CD8A"],  90),
    "NCAM1": percentile(gene_expr["NCAM1"], 90),
    "ITGAE": percentile(gene_expr["ITGAE"], 90),
    "CD274": percentile(gene_expr["CD274"], 10),
    "HAVCR2":percentile(gene_expr["HAVCR2"],10),
    "KRAS":  percentile(gene_expr["KRAS"],  75),
}
avatar_hot = build_zavatar(hot_scores, "HOT_TUMOR_PROFILE")

# ── Imprimir comparativa ───────────────────────────────────────
avatars = [avatar_median, avatar_cold, avatar_hot]
param_names = list(BASE_PARAMS.keys())

print("\n── Parámetros OncoBiome por avatar ──────────────────────────")
print(f"{'Parámetro':<35} {'BASE':>8} {'MEDIAN':>10} {'COLD':>10} {'HOT':>10}")
print("-" * 75)
for p in param_names:
    base = BASE_PARAMS[p]
    vals = [a["params"].get(p, base) for a in avatars]
    print(f"{p:<35} {base:>8.4f} "
          f"{vals[0]:>10.4f} {vals[1]:>10.4f} {vals[2]:>10.4f}")

print("\n── Delta % vs parámetros base ────────────────────────────────")
print(f"{'Parámetro':<35} {'MEDIAN':>10} {'COLD':>10} {'HOT':>10}")
print("-" * 65)
for p in param_names:
    deltas = [a["delta_from_base"].get(p, 0) for a in avatars]
    markers = ["↑" if d > 5 else "↓" if d < -5 else "=" for d in deltas]
    print(f"{p:<35} "
          f"{deltas[0]:>+7.1f}%{markers[0]} "
          f"{deltas[1]:>+7.1f}%{markers[1]} "
          f"{deltas[2]:>+7.1f}%{markers[2]}")

# ── Guardar avatares ───────────────────────────────────────────
os.makedirs("data/avatars", exist_ok=True)
all_avatars = {
    "TCGA_PAAD_MEDIAN":   avatar_median,
    "COLD_TUMOR_PROFILE": avatar_cold,
    "HOT_TUMOR_PROFILE":  avatar_hot,
}
with open("data/avatars/zavatar_profiles.json", "w") as f:
    json.dump(all_avatars, f, indent=2)

print(f"\n✓ 3 avatares guardados: data/avatars/zavatar_profiles.json")
print("\n── Interpretación biológica ──────────────────────────────────")
print("COLD_TUMOR: immune_kill↓, nk↓, m2_thresh↓, exhaust↑")
print("  → Simulará TME inmunosupresor: NK/CD8 colapsan más rápido")
print("HOT_TUMOR:  immune_kill↑, nk↑, m2_thresh↑, exhaust↓")
print("  → Simulará TME inmuno-activo: posible control tumoral")
print("MEDIAN:     perfil representativo paciente PDAC típico TCGA")
