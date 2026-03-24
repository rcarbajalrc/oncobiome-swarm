"""scripts/utils.py — utilidades de diagnóstico del proyecto OncoBiome.

Uso:
    python3 scripts/utils.py opus          # historial de análisis Opus (archivo)
    python3 scripts/utils.py pop           # historial de población
    python3 scripts/utils.py cost          # coste de la última run + % LLM vs rule engine
    python3 scripts/utils.py analyze       # análisis post-run del CSV
    python3 scripts/utils.py compare       # comparación entre runs
    python3 scripts/utils.py experiments   # lista experimentos disponibles
    python3 scripts/utils.py clean_logs    # limpia logs antiguos
"""
import sys
import json
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

_OPUS_LOG = _ROOT / "logs" / "opus_history.json"


def cmd_opus():
    """Lee el historial de análisis Opus desde logs/opus_history.json."""
    if _OPUS_LOG.exists():
        try:
            history = json.loads(_OPUS_LOG.read_text())
            if not history:
                print("opus_history.json vacío.")
                return
            for entry in history:
                print(f"\n=== Opus ciclo {entry['cycle']} ===")
                print(entry.get("analysis", "[sin análisis]"))
            return
        except Exception:
            pass

    # Fallback: live_state
    state_file = _ROOT / "state" / "live_state.json"
    if not state_file.exists():
        print("No hay estado guardado ni historial Opus.")
        return
    s = json.loads(state_file.read_text())
    opus = s.get("last_opus_analysis", "Sin análisis Opus aún.")
    cycle = s.get("cycle", "?")
    print(f"\n=== Último análisis Opus (ciclo {cycle}) ===\n")
    print(opus)
    print()


def cmd_pop():
    state_file = _ROOT / "state" / "live_state.json"
    if not state_file.exists():
        print("No hay estado guardado.")
        return
    s = json.loads(state_file.read_text())
    history = s.get("population_history", [])
    print(f"\n=== Historial de población ({len(history)} ciclos) ===\n")
    for i, entry in enumerate(history, 1):
        parts = " | ".join(f"{k}: {v}" for k, v in entry.items())
        print(f"  Ciclo {i:>3}: {parts}")
    print()


def cmd_cost():
    token_log = _ROOT / "logs" / "token_usage.json"
    if not token_log.exists():
        print("No hay log de tokens.")
        return
    data = json.loads(token_log.read_text())
    if not data:
        print("Log de tokens vacío.")
        return

    total_input = sum(e.get("input", 0) for e in data)
    total_output = sum(e.get("output", 0) for e in data)
    total_calls = sum(e.get("calls", 0) for e in data)
    total_fallbacks = sum(e.get("batch_fallbacks", 0) for e in data)
    total_llm_dec = sum(e.get("llm_decisions", 0) for e in data)
    total_rule_dec = sum(e.get("rule_engine_decisions", 0) for e in data)
    n_cycles = len(data)

    cost_input = total_input * 1.0 / 1_000_000
    cost_output = total_output * 5.0 / 1_000_000
    total_cost = cost_input + cost_output

    total_dec = total_llm_dec + total_rule_dec
    llm_pct = round(total_llm_dec / total_dec * 100, 1) if total_dec > 0 else 0
    rule_pct = round(total_rule_dec / total_dec * 100, 1) if total_dec > 0 else 0

    print(f"\n=== Coste última run ({n_cycles} ciclos) ===\n")
    print(f"  Input:               {total_input:>10,} tokens → ${cost_input:.4f}")
    print(f"  Output:              {total_output:>10,} tokens → ${cost_output:.4f}")
    print(f"  Llamadas API:        {total_calls:>10,}")
    print(f"  Batch fallbacks:     {total_fallbacks:>10,}")
    print(f"  Decisiones LLM:      {total_llm_dec:>10,}  ({llm_pct}%)")
    print(f"  Decisiones RuleEng:  {total_rule_dec:>10,}  ({rule_pct}%)")
    print(f"  TOTAL:               {'':>25} ${total_cost:.4f}")
    print(f"  Coste/ciclo:         {'':>25} ${total_cost/n_cycles:.4f}")
    print()


def cmd_analyze():
    import subprocess
    result = subprocess.run(
        [sys.executable, str(_ROOT / "scripts" / "analyze_run.py")],
        capture_output=False,
    )
    sys.exit(result.returncode)


def cmd_compare():
    import subprocess
    result = subprocess.run(
        [sys.executable, str(_ROOT / "scripts" / "compare_runs.py")],
        capture_output=False,
    )
    sys.exit(result.returncode)


def cmd_experiments():
    from simulation.experiment_loader import list_experiments
    list_experiments()


def cmd_clean_logs():
    log_file = _ROOT / "oncobiome.log"
    if log_file.exists():
        size_mb = log_file.stat().st_size / 1_000_000
        log_file.write_text("")
        print(f"Log limpiado: {size_mb:.1f} MB eliminados.")
    else:
        print("No hay log que limpiar.")

    csv_file = _ROOT / "logs" / "decisions.csv"
    if csv_file.exists():
        size_kb = csv_file.stat().st_size / 1_000
        csv_file.unlink()
        print(f"decisions.csv eliminado: {size_kb:.1f} KB.")

    opus_file = _OPUS_LOG
    if opus_file.exists():
        opus_file.unlink()
        print("opus_history.json eliminado.")


COMMANDS = {
    "opus": cmd_opus,
    "pop": cmd_pop,
    "cost": cmd_cost,
    "analyze": cmd_analyze,
    "compare": cmd_compare,
    "experiments": cmd_experiments,
    "clean_logs": cmd_clean_logs,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(f"Uso: python3 scripts/utils.py [{' | '.join(COMMANDS)}]")
        sys.exit(1)
    COMMANDS[sys.argv[1]]()
