"""OncoBiome Swarm — Entry point.

Uso:
    python main.py [--cycles N] [--no-dashboard] [--no-llm]
    python main.py --experiment <nombre>
    python main.py --list-experiments
"""
from __future__ import annotations

import argparse
import asyncio
import fcntl
import json
import logging
import logging.handlers
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=False)  # No sobreescribir vars ya presentes en el entorno

_PROJECT_DIR = Path(__file__).parent
_LOG_FILE    = _PROJECT_DIR / "oncobiome.log"

# ── Logging con rotación automática ──────────────────────────────────────────
# RotatingFileHandler evita que oncobiome.log crezca sin límite (era 19MB).
# maxBytes=5MB, backupCount=3 → máximo ~20MB en disco total.
_file_handler = logging.handlers.RotatingFileHandler(
    _LOG_FILE,
    mode="a",
    maxBytes=5 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8",
)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout), _file_handler],
)
logger = logging.getLogger("main")

_PID_FILE   = _PROJECT_DIR / "state" / "sim.pid"
_LOCK_FILE  = _PROJECT_DIR / "state" / "sim.lock"
_STATE_FILE = _PROJECT_DIR / "state" / "live_state.json"
_TOKEN_LOG  = _PROJECT_DIR / "logs" / "token_usage.json"
_lock_fd: int | None = None


def _write_pid_file() -> None:
    global _lock_fd
    _PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(_LOCK_FILE), os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        try:
            existing_pid = int(_PID_FILE.read_text().strip()) if _PID_FILE.exists() else -1
        except (ValueError, OSError):
            existing_pid = -1
        logger.error("⛔  Ya hay una simulación en curso (PID %d).", existing_pid)
        sys.exit(1)
    _lock_fd = fd
    _PID_FILE.write_text(str(os.getpid()))
    logger.info("Lock adquirido. PID %d", os.getpid())


def _cleanup_pid_file() -> None:
    global _lock_fd
    try:
        _PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass
    if _lock_fd is not None:
        try:
            fcntl.flock(_lock_fd, fcntl.LOCK_UN)
            os.close(_lock_fd)
        except Exception:
            pass
        _lock_fd = None
    try:
        _LOCK_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def _mark_state_stopped(reason: str = "completed") -> None:
    if not _STATE_FILE.exists():
        return
    try:
        with open(_STATE_FILE, "r+", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                state = json.load(f)
                state["running"] = False
                state["stopped_reason"] = reason
                f.seek(0)
                json.dump(state, f, indent=2, ensure_ascii=False)
                f.truncate()
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    except Exception as exc:
        logger.warning("No se pudo marcar estado parada: %s", exc)


def _reset_token_log() -> None:
    try:
        _TOKEN_LOG.parent.mkdir(parents=True, exist_ok=True)
        _TOKEN_LOG.write_text("[]", encoding="utf-8")
    except Exception as exc:
        logger.warning("No se pudo reiniciar token log: %s", exc)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OncoBiome Swarm Simulation")
    parser.add_argument("--cycles", type=int, default=None)
    parser.add_argument("--no-dashboard", action="store_true")
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument("--experiment", type=str, default=None, metavar="NAME",
                        help="Nombre del experimento en experiments.yaml")
    parser.add_argument("--list-experiments", action="store_true",
                        help="Lista experimentos disponibles y sale")
    return parser.parse_args()


def apply_experiment(name: str, args: argparse.Namespace) -> None:
    """Carga parámetros del experimento y los aplica como variables de entorno."""
    from simulation.experiment_loader import apply_experiment_to_env, load_experiment
    params = load_experiment(name)
    apply_experiment_to_env(params)
    if "total_cycles" in params and args.cycles is None:
        args.cycles = params["total_cycles"]
    if params.get("llm_provider") == "rule_engine":
        args.no_llm = True
        logger.info("Experimento '%s': modo rule engine activado ($0)", name)
    logger.info("Experimento '%s' aplicado correctamente.", name)


def build_initial_population(env, memory_store, cfg) -> None:
    """Construye la población inicial de agentes.

    Orden: tumor (cluster central), CD8+, macrófagos, fitoquímicos en
    posiciones aleatorias libres. Sprint 4: NKCell y DendriticCell
    con default n=0 — backward compatible con todos los experimentos previos.
    """
    import numpy as np
    from agents.dendritic_cell import DendriticCell
    from agents.immune_cell import ImmuneCell
    from agents.macrophage_agent import MacrophageAgent
    from agents.nk_cell import NKCell
    from agents.phytochemical_agent import PhytochemicalAgent
    from agents.tumor_cell import TumorCell

    created = {"tumor": 0, "immune": 0, "macro": 0, "phyto": 0, "nk": 0, "dc": 0}
    center = cfg.grid_size / 2

    for _ in range(cfg.n_tumor_cells):
        pos = (
            float(np.clip(center + np.random.normal(0, 15), 0, cfg.grid_size - 1)),
            float(np.clip(center + np.random.normal(0, 15), 0, cfg.grid_size - 1)),
        )
        if env.add_agent(TumorCell(position=pos, memory_store=memory_store)):
            created["tumor"] += 1

    for _ in range(cfg.n_immune_cells):
        pos = env.find_free_random_position()
        if pos and env.add_agent(ImmuneCell(position=pos, memory_store=memory_store)):
            created["immune"] += 1

    for _ in range(cfg.n_macrophages):
        pos = env.find_free_random_position()
        if pos and env.add_agent(MacrophageAgent(position=pos, memory_store=memory_store)):
            created["macro"] += 1

    for _ in range(cfg.n_phytochemicals):
        pos = env.find_free_random_position()
        if pos and env.add_agent(PhytochemicalAgent(position=pos, memory_store=memory_store)):
            created["phyto"] += 1

    # Sprint 4: NK cells (default n=0, no rompe experimentos previos)
    for _ in range(cfg.n_nk_cells):
        pos = env.find_free_random_position()
        if pos and env.add_agent(NKCell(position=pos, memory_store=memory_store)):
            created["nk"] += 1

    # Sprint 4: Dendritic cells (default n=0, backward compatible)
    for _ in range(cfg.n_dendritic_cells):
        pos = env.find_free_random_position()
        if pos and env.add_agent(DendriticCell(position=pos, memory_store=memory_store)):
            created["dc"] += 1

    base_msg = (
        "Población inicial: %d tumor, %d CD8+, %d macrófago, %d fitoquímico"
    )
    args = (created["tumor"], created["immune"], created["macro"], created["phyto"])
    if created["nk"] > 0 or created["dc"] > 0:
        base_msg += ", %d NK, %d DC"
        args += (created["nk"], created["dc"])
    logger.info(base_msg, *args)


async def run_simulation(args: argparse.Namespace) -> None:
    from config import get_config
    from llm.client import LLMClient
    from memory.factory import MemoryFactory
    from simulation.engine import SimulationEngine
    from simulation.environment import Environment

    cfg = get_config()
    llm_client = LLMClient()

    logger.info(
        "=== OncoBiome Swarm === PID:%d | Ciclos:%d | LLM:%s | mem0:%s",
        os.getpid(),
        args.cycles or cfg.total_cycles,
        "OFF (rule-engine)" if args.no_llm else llm_client.provider_info(),
        "mem0ai" if cfg.use_mem0 else "in-memory",
    )

    memory_store = MemoryFactory.create(cfg.mem0_api_key)
    env = Environment()
    build_initial_population(env, memory_store, cfg)

    if not args.no_dashboard:
        from viz.dashboard import OncobiomeDashboard
        dashboard = OncobiomeDashboard(env)
        dashboard.start()
        logger.info("Dashboard iniciado en http://localhost:%d", cfg.dashboard_port)

    engine = SimulationEngine(env=env, no_llm=args.no_llm)

    try:
        await engine.run(cycles=args.cycles)
    except asyncio.CancelledError:
        logger.info("Simulación cancelada.")
        _mark_state_stopped("cancelled")
        raise
    except Exception as exc:
        logger.exception("Error en simulación: %s", exc)
        _mark_state_stopped("error")
        raise

    _mark_state_stopped("completed")
    logger.info("Simulación completada. Ciclos: %d", env.cycle)


def main() -> None:
    args = parse_args()

    if args.list_experiments:
        from simulation.experiment_loader import list_experiments
        list_experiments()
        sys.exit(0)

    if args.experiment:
        apply_experiment(args.experiment, args)

    # Validar API key antes de hacer nada — fail fast, mensaje claro
    from config import get_config
    get_config.cache_clear()
    cfg = get_config()
    cfg.validate_api_key(no_llm=args.no_llm)

    _write_pid_file()
    _reset_token_log()

    try:
        asyncio.run(run_simulation(args))
    except KeyboardInterrupt:
        logger.info("Interrupción manual recibida.")
        _mark_state_stopped("interrupted")
    except SystemExit:
        raise
    except Exception:
        _mark_state_stopped("error")
        raise
    finally:
        _cleanup_pid_file()


if __name__ == "__main__":
    main()
