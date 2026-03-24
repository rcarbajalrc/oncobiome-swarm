"""Experiment loader — carga configuración de experimentos desde YAML."""
from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_DIR = Path(__file__).parent.parent
_EXPERIMENTS_FILE = _PROJECT_DIR / "experiments.yaml"


def load_experiment(name: str) -> dict:
    """Carga los parámetros de un experimento por nombre."""
    try:
        import yaml
    except ImportError:
        print("PyYAML no instalado. Ejecuta: pip install pyyaml")
        sys.exit(1)

    if not _EXPERIMENTS_FILE.exists():
        print(f"No se encontró experiments.yaml en {_PROJECT_DIR}")
        sys.exit(1)

    with open(_EXPERIMENTS_FILE) as f:
        data = yaml.safe_load(f)

    experiments = data.get("experiments", {})

    if name not in experiments:
        available = list(experiments.keys())
        print(f"Experimento '{name}' no encontrado.")
        print(f"Experimentos disponibles: {', '.join(available)}")
        sys.exit(1)

    params = dict(experiments[name])
    description = params.pop("description", "")

    print(f"\n{'='*50}")
    print(f"Experimento: {name}")
    print(f"Descripción: {description}")
    print(f"Parámetros:")
    for k, v in params.items():
        print(f"  {k}: {v}")
    print(f"{'='*50}\n")

    return params


def list_experiments() -> None:
    """Imprime todos los experimentos disponibles."""
    try:
        import yaml
    except ImportError:
        print("PyYAML no instalado.")
        return

    if not _EXPERIMENTS_FILE.exists():
        print("No se encontró experiments.yaml")
        return

    with open(_EXPERIMENTS_FILE) as f:
        data = yaml.safe_load(f)

    experiments = data.get("experiments", {})
    print(f"\nExperimentos disponibles ({len(experiments)}):\n")
    for name, params in experiments.items():
        desc = params.get("description", "Sin descripción")
        provider = params.get("llm_provider", "anthropic")
        memory = " [NO-MEM]" if params.get("memory_mode") == "null" else ""
        print(f"  {name:<35} {desc}{memory}")
    print()


def apply_experiment_to_env(params: dict) -> None:
    """Aplica los parámetros del experimento como variables de entorno."""
    import os

    mapping = {
        "max_agents":             "MAX_AGENTS",
        "total_cycles":           "TOTAL_CYCLES",
        "opus_analysis_interval": "OPUS_ANALYSIS_INTERVAL",
        "n_tumor_cells":          "N_TUMOR_CELLS",
        "n_immune_cells":         "N_IMMUNE_CELLS",
        "n_macrophages":          "N_MACROPHAGES",
        "n_phytochemicals":       "N_PHYTOCHEMICALS",
        "n_nk_cells":             "N_NK_CELLS",
        "n_dendritic_cells":      "N_DENDRITIC_CELLS",
        "llm_concurrency":        "LLM_CONCURRENCY",
        "haiku_max_tokens":       "HAIKU_MAX_TOKENS",
        "memory_mode":            "MEMORY_MODE",   # Sprint 5: ablation support
    }

    for param_key, env_key in mapping.items():
        if param_key in params and param_key != "llm_provider":
            os.environ[env_key] = str(params[param_key])
