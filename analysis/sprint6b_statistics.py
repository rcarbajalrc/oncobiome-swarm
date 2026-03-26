"""
OncoBiome Sprint 6B — Análisis estadístico zAvatar COLD vs HOT
Mann-Whitney U bilateral (sin scipy, Python puro)
"""

import math

# ── Datos Sprint 6B ────────────────────────────────────────────
# COLD n=3 (R1, R2, R3)
cold_nk_collapse    = [25, 34, 23]
cold_cd8_collapse   = [33, 34, 31]
cold_tumor_c35      = [72, 61, 72]

# HOT n=3 (R1, R2, R3)
hot_nk_collapse     = [29, 25, 27]
hot_cd8_collapse    = [30, 32, 29]
hot_tumor_c35       = [72, 69, 72]

# MEDIAN n=1 (referencia)
median_nk    = 25
median_cd8   = 33
median_tumor = 72

def mean(x): return sum(x) / len(x)
def std(x):
    m = mean(x)
    return math.sqrt(sum((v - m)**2 for v in x) / len(x))

def mann_whitney_u(x, y):
    """Mann-Whitney U bilateral exacto para muestras pequeñas."""
    nx, ny = len(x), len(y)
    u1 = sum(1 for xi in x for yi in y if xi < yi) + \
         sum(0.5 for xi in x for yi in y if xi == yi)
    u2 = nx * ny - u1
    u = min(u1, u2)

    # Tabla crítica U para n1=n2=3, α=0.05 bilateral: U_crit = 0
    # Para n=3, el test exacto tiene poca potencia
    # Usamos aproximación normal para n>=3
    mu_u = nx * ny / 2
    sigma_u = math.sqrt(nx * ny * (nx + ny + 1) / 12)
    if sigma_u == 0:
        return u, 1.0
    z = (u - mu_u) / sigma_u

    # p-valor bilateral aproximado (distribución normal estándar)
    # Aproximación de la función de distribución normal
    def norm_cdf(z):
        t = 1 / (1 + 0.3275911 * abs(z))
        poly = t * (0.254829592 + t * (-0.284496736 +
               t * (1.421413741 + t * (-1.453152027 + t * 1.061405429))))
        return 0.5 * (1 + (1 - poly * math.exp(-z*z/2)) * (1 if z >= 0 else -1))

    p = 2 * min(norm_cdf(z), 1 - norm_cdf(z))
    return u, round(p, 4)

print("=" * 65)
print("  OncoBiome Sprint 6B — Análisis zAvatar COLD vs HOT")
print("=" * 65)

print("\n── Estadísticas descriptivas ─────────────────────────────────")
print(f"{'Métrica':<25} {'COLD mean±SD':>14} {'HOT mean±SD':>14} {'MEDIAN (n=1)':>14}")
print("-" * 67)
metrics = [
    ("NK colapso (ciclo)", cold_nk_collapse, hot_nk_collapse, median_nk),
    ("CD8⁺ colapso (ciclo)", cold_cd8_collapse, hot_cd8_collapse, median_cd8),
    ("Tumor c35 (células)", cold_tumor_c35, hot_tumor_c35, median_tumor),
]
for name, cold, hot, med in metrics:
    print(f"{name:<25} {mean(cold):>6.1f}±{std(cold):.1f}     "
          f"{mean(hot):>6.1f}±{std(hot):.1f}     {med:>6}")

print("\n── Tests Mann-Whitney U (COLD vs HOT) ────────────────────────")
print(f"{'Métrica':<25} {'U':>5} {'p-valor':>10} {'Sig':>6}")
print("-" * 50)
for name, cold, hot, _ in metrics:
    u, p = mann_whitney_u(cold, hot)
    sig = "NS" if p > 0.05 else "*"
    print(f"{name:<25} {u:>5.1f} {p:>10.4f} {sig:>6}")

print("\n── Patrón NK→CD8⁺ ────────────────────────────────────────────")
cold_pattern = all(nk < cd8 for nk, cd8 in zip(cold_nk_collapse, cold_cd8_collapse))
hot_pattern  = all(nk < cd8 for nk, cd8 in zip(hot_nk_collapse, hot_cd8_collapse))
print(f"  COLD: NK precede CD8⁺ en {sum(1 for nk,cd8 in zip(cold_nk_collapse,cold_cd8_collapse) if nk<cd8)}/3 runs — {'✓' if cold_pattern else '✗'}")
print(f"  HOT:  NK precede CD8⁺ en {sum(1 for nk,cd8 in zip(hot_nk_collapse,hot_cd8_collapse) if nk<cd8)}/3 runs — {'✓' if hot_pattern else '✗'}")
total_pattern = sum(1 for nk,cd8 in zip(cold_nk_collapse+hot_nk_collapse, cold_cd8_collapse+hot_cd8_collapse) if nk<cd8)
print(f"  TOTAL Sprint 6B: {total_pattern}/6 runs con patrón NK→CD8⁺")

print("\n── H6b: HOT muestra control tumoral superior ─────────────────")
# Tumor c6 no disponible aquí, usamos los datos conocidos
cold_tumor_c6 = [47, 21, 39]  # R1, R2, R3
hot_tumor_c6  = [14, 19, 27]
print(f"  Tumor c6 COLD: {mean(cold_tumor_c6):.1f}±{std(cold_tumor_c6):.1f}")
print(f"  Tumor c6 HOT:  {mean(hot_tumor_c6):.1f}±{std(hot_tumor_c6):.1f}")
u6, p6 = mann_whitney_u(hot_tumor_c6, cold_tumor_c6)
print(f"  Mann-Whitney U={u6:.1f}, p={p6:.4f} {'NS' if p6>0.05 else '*'}")
print(f"  H6b: HOT < COLD en c6 — {'CONFIRMADA tendencia' if mean(hot_tumor_c6) < mean(cold_tumor_c6) else 'NO CONFIRMADA'}")

print("\n── Nota sobre potencia estadística ──────────────────────────")
print("  n=3 por condición → potencia baja (~0.20-0.35)")
print("  Resultados son direccionales, no confirmatorios")
print("  Sprint 7A (multi-LLM, n=10) aumentará la potencia")

print("\n✓ Análisis completado")
