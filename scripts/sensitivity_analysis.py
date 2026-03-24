"""
Sprint 4 — Análisis de sensibilidad paramétrica ($0, rule engine).

Varía ±20% los 3 parámetros más influyentes del seed biológico KRAS G12D:
  1. immune_kill_rate       (0.15 ± 20% → 0.12, 0.15, 0.18)
  2. m2_polarisation_il6_threshold (0.06 ± 20% → 0.048, 0.06, 0.072)
  3. max_agents             (150 ± 20% → 120, 150, 180)

Para cada combinación, corre full_rule_engine 52 ciclos y registra:
  - Tumor final en c52
  - Ciclo de colapso inmune (si ocurre)
  - Coeficiente de variación de la curva tumoral

Produce tabla de sensibilidad para el paper (Methods section).

USO:
    python scripts/sensitivity_analysis.py              # OAT (7 runs, ~30s)
    python scripts/sensitivity_analysis.py --full       # 3x3x3 = 27 runs (~2min)

FIXES aplicados vs versión anterior:
  - BUG #1: population_history no tiene campo 'cycle' — se usa enumerate(history, 1)
  - BUG #2: logs/ puede no existir — mkdir antes de write_text
  - BUG #3: timeout aumentado a 180s + manejo de TimeoutExpired
  - BUG #4: guardado parcial de resultados en factorial para no perder runs
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from itertools import product
from pathlib import Path

PROJECT = Path(__file__).parent.parent

DPC = 2.167  # días por ciclo (PANC-1 52h doubling time)

# ── Parámetros y variaciones ±20% ────────────────────────────────────────────
# NOTA: los nombres de env deben coincidir con los campos de SimulationConfig
# (pydantic-settings convierte IMMUNE_KILL_RATE → immune_kill_rate automáticamente)
PARAMS = {
    "immune_kill_rate": {
        "base":  0.15,
        "low":   round(0.15 * 0.80, 4),   # 0.12
        "high":  round(0.15 * 1.20, 4),   # 0.18
        "env":   "IMMUNE_KILL_RATE",
        "label": "kill_rate",
    },
    "m2_polarisation_il6_threshold": {
        "base":  0.06,
        "low":   round(0.06 * 0.80, 4),   # 0.048
        "high":  round(0.06 * 1.20, 4),   # 0.072
        "env":   "M2_POLARISATION_IL6_THRESHOLD",
        "label": "m2_thresh",
    },
    "max_agents": {
        "base":  150,
        "low":   120,
        "high":  180,
        "env":   "MAX_AGENTS",
        "label": "cap",
    },
}


def run_rule_engine(env_overrides: dict, cycles: int = 52) -> dict:
    """Lanza una run del rule engine con los parámetros dados.

    El subprocess hereda el entorno del proceso padre más los overrides.
    pydantic-settings carga .env al inicio del proceso hijo, pero los
    env_overrides del padre tienen prioridad porque se pasan directamente
    en el dict env del subprocess (override=True en pydantic-settings).
    """
    env = os.environ.copy()

    # Configuración fija para todas las runs de sensibilidad
    env.update({
        "LLM_PROVIDER":           "rule_engine",
        "TOTAL_CYCLES":           str(cycles),
        "N_TUMOR_CELLS":          "12",
        "N_IMMUNE_CELLS":         "5",
        "N_MACROPHAGES":          "3",
        "N_PHYTOCHEMICALS":       "2",
        "OPUS_ANALYSIS_INTERVAL": "999",
        "LOG_DECISIONS":          "false",   # no CSV — más rápido
    })

    # Aplicar overrides del parámetro que se está variando
    env.update(env_overrides)

    # FIX #2: asegurar que logs/ existe antes de escribir
    token_log = PROJECT / "logs" / "token_usage.json"
    token_log.parent.mkdir(parents=True, exist_ok=True)
    token_log.write_text("[]")

    try:
        result = subprocess.run(
            [sys.executable, str(PROJECT / "main.py"), "--no-dashboard", "--no-llm"],
            env=env,
            cwd=str(PROJECT),
            capture_output=True,
            text=True,
            timeout=180,   # FIX #3: aumentado de 120s a 180s
        )
    except subprocess.TimeoutExpired:
        print("  ⚠ TIMEOUT — run expiró después de 180s")
        return {"error": "timeout"}

    if result.returncode != 0:
        # Mostrar solo las últimas líneas del stderr para diagnóstico
        err_lines = result.stderr.strip().splitlines()
        print(f"  ⚠ ERROR (code {result.returncode}): {err_lines[-1] if err_lines else 'sin stderr'}")
        return {"error": f"returncode={result.returncode}"}

    # Leer population_history desde live_state
    live_state = PROJECT / "state" / "live_state.json"
    if not live_state.exists():
        print("  ⚠ live_state.json no encontrado")
        return {"error": "no_live_state"}

    with open(live_state) as f:
        state = json.load(f)

    # FIX #1: population_history NO tiene campo 'cycle' — usar enumerate(history, 1)
    history = state.get("population_history", [])
    if not history:
        print("  ⚠ population_history vacío en live_state")
        return {"error": "empty_history"}

    # Métricas
    tumor_final = history[-1].get("TumorCell", 0)

    # Colapso inmune: primer índice (1-based) donde ImmuneCell == 0
    immune_collapse = None
    for cycle_idx, entry in enumerate(history, 1):
        if entry.get("ImmuneCell", 1) == 0:
            immune_collapse = cycle_idx
            break

    # CV de la curva tumoral
    tumor_values = [h.get("TumorCell", 0) for h in history]
    if len(tumor_values) > 1:
        import statistics as st
        mean_t = st.mean(tumor_values)
        cv = st.stdev(tumor_values) / mean_t * 100 if mean_t > 0 else 0.0
    else:
        cv = 0.0

    return {
        "tumor_final":          tumor_final,
        "immune_collapse":      immune_collapse,
        "immune_collapse_days": round(immune_collapse * DPC, 1) if immune_collapse else None,
        "tumor_cv":             round(cv, 1),
        "cycles_completed":     len(history),
    }


def _print_result(r: dict) -> None:
    if "error" in r:
        print(f"  → ERROR: {r['error']}")
        return
    collapse = (
        f"c{r['immune_collapse']} ({r['immune_collapse_days']}d)"
        if r.get("immune_collapse") else "no collapse"
    )
    print(f"  → tumor={r['tumor_final']}  collapse={collapse}  "
          f"cv={r['tumor_cv']}%  ciclos={r['cycles_completed']}")


def one_at_a_time_analysis() -> list[dict]:
    """OAT: varía 1 parámetro a la vez manteniendo el resto en valor base.
    7 runs: 1 baseline + 2 variaciones × 3 parámetros.
    """
    results = []

    # Baseline
    print("\n[1/7] Baseline (todos en valor base)...")
    base_result = run_rule_engine({})
    results.append({"run": "baseline", "param": "—", "value": "base", **base_result})
    _print_result(results[-1])

    n = 2
    for param_name, cfg in PARAMS.items():
        for variant, val in [("low", cfg["low"]), ("high", cfg["high"])]:
            n += 1
            label = f"{cfg['label']}={val} ({variant})"
            print(f"\n[{n}/7] {label}...")
            overrides = {cfg["env"]: str(val)}
            result = run_rule_engine(overrides)
            results.append({
                "run":     label,
                "param":   param_name,
                "value":   val,
                "variant": variant,
                **result,
            })
            _print_result(results[-1])

    return results


def full_factorial_analysis() -> list[dict]:
    """3×3×3 = 27 combinaciones — análisis factorial completo."""
    results = []
    partial_path = PROJECT / "results" / "sensitivity_partial.json"
    partial_path.parent.mkdir(exist_ok=True)

    param_names = list(PARAMS.keys())
    combos = list(product(*[
        [cfg["low"], cfg["base"], cfg["high"]]
        for cfg in PARAMS.values()
    ]))
    total = len(combos)
    print(f"\nAnálisis factorial: {total} combinaciones")

    for i, combo in enumerate(combos, 1):
        overrides = {
            PARAMS[p]["env"]: str(v)
            for p, v in zip(param_names, combo)
        }
        label = " ".join(
            f"{PARAMS[p]['label']}={v}"
            for p, v in zip(param_names, combo)
        )
        print(f"\n[{i}/{total}] {label}...", end=" ", flush=True)
        result = run_rule_engine(overrides)
        results.append({"run": label, **result})
        _print_result(results[-1])

        # FIX #4: guardar parciales para no perder trabajo si hay error
        partial_path.write_text(json.dumps(results, indent=2))

    # Limpiar parciales al terminar correctamente
    if partial_path.exists():
        partial_path.unlink()

    return results


def save_results(results: list[dict], filename: str = "sensitivity_oat.json") -> None:
    out_dir = PROJECT / "results"
    out_dir.mkdir(exist_ok=True)

    # JSON
    json_path = out_dir / filename
    json_path.write_text(json.dumps(results, indent=2))
    print(f"\n✓ JSON: results/{filename}")

    # CSV
    csv_path = out_dir / filename.replace(".json", ".csv")
    keys = ["run", "param", "value", "variant",
            "tumor_final", "immune_collapse", "immune_collapse_days",
            "tumor_cv", "cycles_completed", "error"]
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write(",".join(keys) + "\n")
        for r in results:
            f.write(",".join(str(r.get(k, "")) for k in keys) + "\n")
    print(f"✓ CSV:  results/{filename.replace('.json', '.csv')}")


def print_summary_table(results: list[dict]) -> None:
    DPC_val = DPC
    print(f"\n{'═'*72}")
    print("TABLA DE SENSIBILIDAD PARAMÉTRICA — OncoBiome Swarm")
    print(f"Escala: 1 ciclo = {DPC_val} días (PANC-1 52h doubling time)")
    print(f"{'═'*72}")
    print(f"{'Run':<32} {'Tumor':>7} {'Collapse':>18} {'CV%':>6}")
    print(f"{'─'*72}")

    for r in results:
        if "error" in r:
            print(f"{r['run'][:32]:<32} {'ERROR':>7} {r['error']:>18} {'—':>6}")
            continue
        collapse_str = (
            f"c{r['immune_collapse']} ({r['immune_collapse_days']}d)"
            if r.get("immune_collapse") else "no collapse"
        )
        flag = " ⚠" if r.get("tumor_cv", 0) > 20 else ""
        print(f"{r['run'][:32]:<32} {r.get('tumor_final','?'):>7} "
              f"{collapse_str:>18} {str(r.get('tumor_cv','?')) + flag:>8}")
    print(f"{'═'*72}")


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(
        description="OncoBiome Swarm — Sensitivity Analysis ($0, rule engine)")
    parser.add_argument("--full", action="store_true",
                        help="Análisis factorial completo 3×3×3 = 27 runs (~2 min)")
    args = parser.parse_args()

    print("OncoBiome Swarm — Análisis de Sensibilidad Paramétrica")
    print(f"Coste: $0 (rule engine determinista)")
    print(f"Escala: 1 ciclo = {DPC} días biológicos (PANC-1)")
    print(f"Modo: {'factorial 3×3×3 (27 runs)' if args.full else 'OAT (7 runs)'}")

    if args.full:
        results = full_factorial_analysis()
        save_results(results, "sensitivity_full_factorial.json")
    else:
        results = one_at_a_time_analysis()
        save_results(results, "sensitivity_oat.json")

    print_summary_table(results)


if __name__ == "__main__":
    main()
