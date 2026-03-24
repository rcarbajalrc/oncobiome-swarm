#!/usr/bin/env python3
"""OncoBiome Swarm MCP Server.

Expone los datos de simulación del TME a Claude Desktop.
La simulación escribe state/live_state.json después de cada ciclo;
este server lo lee y presenta los datos como herramientas MCP.

FIX v1: run_simulation mata procesos huérfanos antes de arrancar uno nuevo.
FIX v2: get_simulation_status cruza running con existencia real del proceso.
FIX v3: PYTHON = sys.executable — ya no hardcodeado a ruta local.
FIX v4: _read_file/_write_file/_list_files usan .resolve() contra symlinks.
        SECURITY: path traversal prevenido resolviendo symlinks antes del check.
"""

import asyncio
import fcntl
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

# ── Configuración ─────────────────────────────────────────────────────────────
SIM_DIR        = Path(__file__).parent.resolve()   # .resolve() para consistencia
STATE_FILE     = SIM_DIR / "state" / "live_state.json"
PID_FILE       = SIM_DIR / "state" / "sim.pid"
LOCK_FILE      = SIM_DIR / "state" / "sim.lock"
DASHBOARD_PORT = 8050
PYTHON         = sys.executable   # portable — no hardcodeado
MAIN_PY        = str(SIM_DIR / "main.py")

app = Server("oncobiome-swarm")
_sim_process: subprocess.Popen | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _read_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _is_process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _get_pid_from_file() -> int | None:
    if not PID_FILE.exists():
        return None
    try:
        return int(PID_FILE.read_text().strip())
    except (ValueError, OSError):
        return None


def _reconcile_running_state(state: dict) -> dict:
    if not state.get("running", False):
        return state
    pid = _get_pid_from_file()
    global _sim_process
    mcp_alive = _sim_process is not None and _sim_process.poll() is None
    pid_alive  = pid is not None and _is_process_alive(pid)
    if mcp_alive or pid_alive:
        return state
    state["running"] = False
    state["stopped_reason"] = "proceso_terminado_detectado_por_mcp"
    try:
        with open(STATE_FILE, "r+", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                current = json.load(f)
                current["running"] = False
                current["stopped_reason"] = "proceso_terminado_detectado_por_mcp"
                f.seek(0)
                json.dump(current, f, indent=2, ensure_ascii=False)
                f.truncate()
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    except Exception:
        pass
    if pid is not None and not pid_alive:
        PID_FILE.unlink(missing_ok=True)
    return state


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(("localhost", port)) == 0


def _pid_holding_port(port: int) -> int | None:
    try:
        out = subprocess.check_output(
            ["lsof", "-ti", f":{port}"], text=True, stderr=subprocess.DEVNULL
        ).strip()
        return int(out.split("\n")[0]) if out else None
    except (subprocess.CalledProcessError, ValueError, OSError):
        return None


def _sigterm_and_wait(pid: int, timeout: float = 3.0) -> bool:
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(0.2)
        if not _is_process_alive(pid):
            return True
    return False


def _kill_existing_simulation() -> str:
    global _sim_process
    killed = []

    if _sim_process is not None:
        pid = _sim_process.pid
        if _sim_process.poll() is None:
            if not _sigterm_and_wait(pid):
                _sim_process.kill()
            killed.append(f"proceso MCP PID={pid}")
        _sim_process = None

    if PID_FILE.exists():
        try:
            orphan_pid = int(PID_FILE.read_text().strip())
            if _is_process_alive(orphan_pid):
                if not _sigterm_and_wait(orphan_pid):
                    os.kill(orphan_pid, signal.SIGKILL)
                    time.sleep(0.3)
                killed.append(f"huérfano PID={orphan_pid} (via pid file)")
            else:
                killed.append(f"pid file obsoleto PID={orphan_pid} (ya muerto)")
        except (ValueError, OSError) as e:
            killed.append(f"error leyendo pid file: {e}")
        finally:
            PID_FILE.unlink(missing_ok=True)

    if _port_in_use(DASHBOARD_PORT):
        port_pid = _pid_holding_port(DASHBOARD_PORT)
        if port_pid and _is_process_alive(port_pid):
            if not _sigterm_and_wait(port_pid):
                os.kill(port_pid, signal.SIGKILL)
                time.sleep(0.3)
            killed.append(f"huérfano PID={port_pid} (via puerto {DASHBOARD_PORT})")

    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r+", encoding="utf-8") as f:
                fcntl.flock(f, fcntl.LOCK_EX)
                try:
                    current = json.load(f)
                    current["running"] = False
                    current["stopped_reason"] = "stop_simulation_tool"
                    f.seek(0)
                    json.dump(current, f, indent=2, ensure_ascii=False)
                    f.truncate()
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)
        except Exception:
            pass

    return "No había simulaciones activas." if not killed else f"Terminado: {', '.join(killed)}"


# ── Tools MCP ─────────────────────────────────────────────────────────────────

@app.list_tools()
async def list_tools():
    return [
        types.Tool(name="run_simulation",        description="Arranca una nueva simulación OncoBiome Swarm. Mata procesos activos antes.", inputSchema={"type":"object","properties":{"cycles":{"type":"integer","default":100},"no_dashboard":{"type":"boolean","default":False},"no_llm":{"type":"boolean","default":False}},"required":[]}),
        types.Tool(name="stop_simulation",       description="Para la simulación en curso.", inputSchema={"type":"object","properties":{},"required":[]}),
        types.Tool(name="get_simulation_status", description="Estado: ciclo, running, población, timestamp.", inputSchema={"type":"object","properties":{},"required":[]}),
        types.Tool(name="get_population_history",description="Serie temporal de conteos por tipo de agente.", inputSchema={"type":"object","properties":{},"required":[]}),
        types.Tool(name="get_cytokine_levels",   description="Niveles IL-6, VEGF, IFN-γ con mean/max/total.", inputSchema={"type":"object","properties":{},"required":[]}),
        types.Tool(name="get_decisions_summary", description="Decisiones de agentes en el último ciclo.", inputSchema={"type":"object","properties":{},"required":[]}),
        types.Tool(name="get_opus_analysis",     description="Último análisis emergente de Claude Opus.", inputSchema={"type":"object","properties":{},"required":[]}),
        types.Tool(name="get_agent_states",      description="Posición, energía, edad de cada agente vivo.", inputSchema={"type":"object","properties":{},"required":[]}),
        types.Tool(name="get_token_stats",       description="Tokens, llamadas, costes estimados.", inputSchema={"type":"object","properties":{},"required":[]}),
        types.Tool(name="get_recent_events",     description="Log de eventos recientes del TME.", inputSchema={"type":"object","properties":{},"required":[]}),
        types.Tool(name="list_files",            description="Lista archivos en un subdirectorio del proyecto.", inputSchema={"type":"object","properties":{"subdir":{"type":"string","default":"."}},"required":[]}),
        types.Tool(name="read_file",             description="Lee un archivo del proyecto (sandboxed).", inputSchema={"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}),
        types.Tool(name="write_file",            description="Escribe un archivo del proyecto (sandboxed).", inputSchema={"type":"object","properties":{"path":{"type":"string"},"content":{"type":"string"}},"required":["path","content"]}),
        types.Tool(name="run_custom",            description="Ejecuta un comando bash en el proyecto. SECURITY: solo para uso local de investigación.", inputSchema={"type":"object","properties":{"command":{"type":"string"}},"required":["command"]}),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "run_simulation":
        return await _run_simulation(arguments)
    elif name == "stop_simulation":
        return [types.TextContent(type="text", text=f"Stop: {_kill_existing_simulation()}")]
    elif name == "get_simulation_status":
        return [types.TextContent(type="text", text=_get_status())]
    elif name == "get_population_history":
        return [types.TextContent(type="text", text=_get_population_history())]
    elif name == "get_cytokine_levels":
        return [types.TextContent(type="text", text=_get_cytokines())]
    elif name == "get_decisions_summary":
        return [types.TextContent(type="text", text=_read_state().get("last_decisions_summary", "Sin resumen."))]
    elif name == "get_opus_analysis":
        return [types.TextContent(type="text", text=_get_opus())]
    elif name == "get_agent_states":
        return [types.TextContent(type="text", text=_get_agents())]
    elif name == "get_token_stats":
        return [types.TextContent(type="text", text=_get_tokens())]
    elif name == "get_recent_events":
        return [types.TextContent(type="text", text=_get_events())]
    elif name == "list_files":
        return [types.TextContent(type="text", text=_list_files(arguments.get("subdir", ".")))]
    elif name == "read_file":
        return [types.TextContent(type="text", text=_read_file(arguments["path"]))]
    elif name == "write_file":
        return [types.TextContent(type="text", text=_write_file(arguments["path"], arguments["content"]))]
    elif name == "run_custom":
        return [types.TextContent(type="text", text=_run_custom(arguments["command"]))]
    return [types.TextContent(type="text", text=f"Tool desconocida: {name}")]


async def _run_simulation(args: dict):
    global _sim_process
    kill_msg = _kill_existing_simulation()
    await asyncio.sleep(0.5)
    cycles       = args.get("cycles", 100)
    no_dashboard = args.get("no_dashboard", False)
    no_llm       = args.get("no_llm", False)
    cmd = [PYTHON, MAIN_PY, "--cycles", str(cycles)]
    if no_dashboard: cmd.append("--no-dashboard")
    if no_llm:       cmd.append("--no-llm")
    _sim_process = subprocess.Popen(cmd, cwd=str(SIM_DIR))
    await asyncio.sleep(1.0)
    return [types.TextContent(type="text", text=(
        f"Simulación iniciada.\n"
        f"  PID: {_sim_process.pid}\n"
        f"  Ciclos: {cycles}\n"
        f"  Dashboard: {'OFF' if no_dashboard else 'ON'}\n"
        f"  LLM: {'OFF' if no_llm else 'ON'}\n"
        f"  Acción previa: {kill_msg}\n"
        f"  Log: {SIM_DIR / 'oncobiome.log'}"
    ))]


def _get_status() -> str:
    state = _reconcile_running_state(_read_state())
    if not state:
        return "No hay datos de simulación disponibles."
    running    = state.get("running", False)
    cycle      = state.get("cycle", 0)
    pid        = state.get("pid", "N/A")
    ts         = state.get("timestamp", "")
    population = state.get("population", {})
    stopped    = state.get("stopped_reason", "")
    lines = [
        "=== OncoBiome Swarm — Estado de Simulación ===",
        f"Estado:    {'CORRIENDO' if running else 'PARADA'}",
        f"Ciclo:     {cycle}",
        f"PID:       {pid}",
        f"Timestamp: {ts}",
        f"",
        f"Población total: {sum(population.values())} agentes",
    ]
    for agent_type, count in sorted(population.items()):
        lines.append(f"  {agent_type}: {count}")
    if stopped and not running:
        lines.append(f"\nMotivo parada: {stopped}")
    return "\n".join(lines)


def _get_population_history() -> str:
    state   = _read_state()
    history = state.get("population_history", state.get("history", []))
    if not history:
        return "Sin historial de población disponible."
    lines = [f"=== Historial de Población ({len(history)} ciclos) ==="]
    for i, entry in enumerate(history, 1):
        parts = "  ".join(f"{k}={v}" for k, v in sorted(entry.items()) if k != "cycle")
        lines.append(f"  ciclo ~{i}:  {parts}")
    return "\n".join(lines)


def _get_cytokines() -> str:
    cytokines = _read_state().get("cytokines", {})
    if not cytokines:
        return "Sin datos de citoquinas."
    lines = ["=== Niveles de Citoquinas ==="]
    for name, vals in sorted(cytokines.items()):
        if isinstance(vals, dict):
            lines.append(f"  {name}: mean={vals.get('mean',0):.4f}  max={vals.get('max',0):.4f}  total={vals.get('total',0):.4f}")
    return "\n".join(lines)


def _get_opus() -> str:
    opus_log = SIM_DIR / "logs" / "opus_history.json"
    if opus_log.exists():
        try:
            history = json.loads(opus_log.read_text())
            if history:
                last = history[-1]
                return f"=== Último análisis Opus (ciclo {last.get('cycle','?')}) ===\n{last.get('analysis','')}"
        except Exception:
            pass
    opus = _read_state().get("last_opus_analysis", "")
    return opus if opus else "Sin análisis Opus disponible."


def _get_agents() -> str:
    agents = _read_state().get("agents", [])
    if not agents:
        return "Sin datos de agentes."
    lines = [f"=== Estado de Agentes ({len(agents)} visibles) ==="]
    for a in agents[:20]:
        lines.append(
            f"  {a.get('type','?')} {a.get('id','?')[:8]}  "
            f"pos=({a.get('x',0):.0f},{a.get('y',0):.0f})  "
            f"e={a.get('energy',0):.2f}  age={a.get('age',0)}"
        )
    return "\n".join(lines)


def _get_tokens() -> str:
    token_log = SIM_DIR / "logs" / "token_usage.json"
    if not token_log.exists():
        return "Sin historial de tokens."
    try:
        data = json.loads(token_log.read_text())
        if not data:
            return "Log de tokens vacío."
        ti = sum(e.get("input", 0) for e in data)
        to = sum(e.get("output", 0) for e in data)
        tc = sum(e.get("calls", 0) for e in data)
        tf = sum(e.get("batch_fallbacks", 0) for e in data)
        cost = (ti * 0.80 + to * 4.00) / 1_000_000
        return (
            f"=== Token Stats ({len(data)} ciclos) ===\n"
            f"  Input:     {ti:,} tokens\n"
            f"  Output:    {to:,} tokens\n"
            f"  API calls: {tc:,}\n"
            f"  Fallbacks: {tf}\n"
            f"  Coste Haiku estimado: ${cost:.4f}"
        )
    except Exception as e:
        return f"Error leyendo token log: {e}"


def _get_events() -> str:
    events = _read_state().get("recent_events", [])
    if not events:
        return "Sin eventos recientes."
    return "=== Eventos Recientes ===\n" + "\n".join(f"  {ev}" for ev in events[-20:])


def _safe_path(path_str: str) -> tuple[Path | None, str]:
    """Resuelve y valida que la ruta esté dentro de SIM_DIR.

    SECURITY FIX v4: usa .resolve() para resolver symlinks antes de comparar.
    Previene path traversal via '../' o symlinks que apunten fuera del proyecto.
    """
    try:
        target   = (SIM_DIR / path_str).resolve()
        sim_root = SIM_DIR  # ya resuelto en la definición global
        if not str(target).startswith(str(sim_root) + os.sep) and target != sim_root:
            return None, "Error: acceso fuera del directorio del proyecto."
        return target, ""
    except Exception as e:
        return None, f"Error resolviendo ruta: {e}"


def _list_files(subdir: str) -> str:
    target, err = _safe_path(subdir)
    if err:
        return err
    if not target.exists():
        return f"No hay archivos en {subdir}"
    files = sorted(
        f for f in target.iterdir()
        if f.suffix in (".py", ".json", ".log", ".yaml", ".md", ".txt", ".csv")
        or f.name in (".env.example", ".gitignore")
    )
    if not files:
        return f"No hay archivos en {subdir}"
    lines = [f"=== {subdir}/ ({len(files)}) archivos) ==="]
    for f in files:
        lines.append(f"  {f.name:<50} {f.stat().st_size:>10} bytes")
    return "\n".join(lines)


def _read_file(path: str) -> str:
    target, err = _safe_path(path)
    if err:
        return err
    if not target.exists():
        return f"Archivo no encontrado: {path}"
    try:
        content = target.read_text(encoding="utf-8")
        if len(content) > 8000:
            content = content[:8000] + "\n[... truncado a 8000 chars ...]"
        return f"=== {path} ===\n{content}"
    except Exception as e:
        return f"Error leyendo {path}: {e}"


def _write_file(path: str, content: str) -> str:
    target, err = _safe_path(path)
    if err:
        return err
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"Archivo escrito: {path} ({len(content)} chars)"


def _run_custom(command: str) -> str:
    """Ejecuta un comando bash.

    SECURITY: shell=True permite inyección si el input no es de confianza.
    Este tool es para uso local de investigación únicamente — ver SECURITY.md.
    """
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True,
            cwd=str(SIM_DIR), timeout=30,
        )
        out = result.stdout[:4000] if result.stdout else ""
        err = result.stderr[:1000] if result.stderr else ""
        return f"returncode={result.returncode}\nstdout={out}\nstderr={err}"
    except subprocess.TimeoutExpired:
        return "Error: comando expiró (timeout 30s)"
    except Exception as e:
        return f"Error: {e}"


# ── Entry point ───────────────────────────────────────────────────────────────

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
