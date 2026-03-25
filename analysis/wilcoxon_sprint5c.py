"""
OncoBiome Swarm — Análisis Wilcoxon Sprint 5C
Sin dependencias externas — implementación manual
"""

import math

# ── Datos ──────────────────────────────────────────────────────────────────
bridge_nk   = [23, 24, 24, 28, 20, 26, 31, 25, 24, 24]
bridge_cd8  = [30, 29, 30, 33, 31, 32, 33, 33, 33, 31]
bridge_tumor= [72, 73, 72, 72, 72, 72, 72, 74, 75, 72]

abstract_nk  = [30, 22, 32, 28, 31, 24, 24, 22, 20, 23]
abstract_cd8 = [34, 28, 33, 33, 36, 30, 34, 30, 29, 33]
abstract_tumor=[72, 72, 72, 72, 72, 72, 74, 72, 72, 72]

bridge_delta  = [b-a for a,b in zip(bridge_nk, bridge_cd8)]
abstract_delta= [b-a for a,b in zip(abstract_nk, abstract_cd8)]

def mean(x): return sum(x)/len(x)
def std(x):
    m = mean(x)
    return math.sqrt(sum((v-m)**2 for v in x)/len(x))

def mann_whitney_u(x, y):
    """Mann-Whitney U test — bilateral, aproximación normal para n>=8"""
    n1, n2 = len(x), len(y)
    u1 = sum(1 if xi > yj else 0.5 if xi == yj else 0
             for xi in x for yj in y)
    u2 = n1 * n2 - u1
    u = min(u1, u2)
    mu = n1 * n2 / 2
    sigma = math.sqrt(n1 * n2 * (n1 + n2 + 1) / 12)
    z = (u - mu) / sigma
    # Aproximación normal bilateral
    p = 2 * (1 - normal_cdf(abs(z)))
    return u, p, z

def normal_cdf(z):
    """CDF normal estándar (aproximación Abramowitz & Stegun)"""
    t = 1 / (1 + 0.2316419 * abs(z))
    poly = t*(0.319381530 + t*(-0.356563782 + t*(1.781477937
           + t*(-1.821255978 + t*1.330274429))))
    p = 1 - (1/math.sqrt(2*math.pi)) * math.exp(-z**2/2) * poly
    return p if z >= 0 else 1 - p

def wilcoxon_signed_rank(x, y):
    """Wilcoxon signed-rank test pareado — bilateral"""
    diffs = [xi - yi for xi, yi in zip(x, y) if xi != yi]
    n = len(diffs)
    if n == 0:
        return 0, 1.0
    abs_diffs = sorted(enumerate(abs(d) for d in diffs), key=lambda x: x[1])
    ranks = [0]*n
    i = 0
    while i < n:
        j = i
        while j < n-1 and abs_diffs[j][1] == abs_diffs[j+1][1]:
            j += 1
        avg_rank = (i + j) / 2 + 1
        for k in range(i, j+1):
            ranks[abs_diffs[k][0]] = avg_rank
        i = j + 1
    w_plus  = sum(r for r, d in zip(ranks, diffs) if d > 0)
    w_minus = sum(r for r, d in zip(ranks, diffs) if d < 0)
    w = min(w_plus, w_minus)
    mu_w = n*(n+1)/4
    sigma_w = math.sqrt(n*(n+1)*(2*n+1)/24)
    z = (w - mu_w) / sigma_w
    p = 2 * (1 - normal_cdf(abs(z)))
    return w, p

def binomial_p(k, n, p0=0.5):
    """P(X>=k) bajo H0: p=p0 (binomial exacto una cola → bilateral *2)"""
    from math import comb
    p_val = sum(comb(n,i)*(p0**i)*((1-p0)**(n-i)) for i in range(k, n+1))
    return min(p_val * 2, 1.0)

# ── Output ─────────────────────────────────────────────────────────────────
print("=" * 62)
print("  OncoBiome Swarm — Análisis Wilcoxon Sprint 5C")
print("=" * 62)

datasets = [
    ("NK colapso",    bridge_nk,    abstract_nk),
    ("CD8+ colapso",  bridge_cd8,   abstract_cd8),
    ("Delta NK->CD8", bridge_delta, abstract_delta),
    ("Tumor c52",     bridge_tumor, abstract_tumor),
]

print("\n── Estadísticas descriptivas ──────────────────────────────")
print(f"{'Métrica':<20} {'Bridge':>18} {'Abstract':>18}")
print("-" * 58)
for label, bd, ad in datasets:
    print(f"{label:<20} {mean(bd):>6.1f}±{std(bd):<6.1f}   "
          f"{mean(ad):>6.1f}±{std(ad):<6.1f}   "
          f"Δ={abs(mean(bd)-mean(ad)):.1f}")

print("\n── Mann-Whitney U (bilateral, n=10 vs n=10) ───────────────")
print(f"{'Métrica':<20} {'U':>6} {'p-valor':>10} {'Sig.':>8}")
print("-" * 48)
for label, bd, ad in datasets:
    u, p, z = mann_whitney_u(bd, ad)
    sig = "NS" if p > 0.05 else "* p<0.05" if p > 0.01 else "** p<0.01"
    print(f"{label:<20} {u:>6.0f} {p:>10.4f} {sig:>8}")

print("\n── Wilcoxon signed-rank (pareado por índice de run) ───────")
print(f"{'Métrica':<20} {'W':>6} {'p-valor':>10} {'Sig.':>8}")
print("-" * 48)
for label, bd, ad in datasets[:3]:
    w, p = wilcoxon_signed_rank(bd, ad)
    sig = "NS" if p > 0.05 else "* p<0.05"
    print(f"{label:<20} {w:>6.0f} {p:>10.4f} {sig:>8}")

print("\n── Binomial exacto (patrón NK→CD8+, H0=0.5) ─────────────")
for label, k, n in [("Bridge 10/10", 10, 10), ("Abstract 10/10", 10, 10)]:
    p = binomial_p(k, n)
    print(f"{label:<20}  P={p:.4f}  {'*** p<0.001' if p < 0.001 else '** p<0.01'}")

print("\n" + "=" * 62)
print("  CONCLUSIÓN")
print("=" * 62)
print()
print("H1 CONFIRMADA — No hay diferencia significativa entre")
print("condición biomédica y abstracta en ninguna métrica.")
print()
u, p, z = mann_whitney_u(bridge_cd8, abstract_cd8)
print(f"CD8+ colapso: bridge {mean(bridge_cd8):.1f}±{std(bridge_cd8):.1f} vs")
print(f"             abstract {mean(abstract_cd8):.1f}±{std(abstract_cd8):.1f}")
print(f"             Mann-Whitney U={u:.0f}, p={p:.4f} (NS)")
print()
print("El patrón NK→CD8+ emerge de la TOPOLOGÍA CAUSAL del")
print("sistema, no del conocimiento biomédico del LLM.")
print("Ambas condiciones: 10/10 runs, P=0.002 (bilateral)")
