"""ReportCollector — instrumentación de la simulación para análisis científico.

Captura por ciclo:
- Población por tipo
- Posiciones de cada agente
- Niveles de citoquinas
- Conteo de decisiones por tipo y acción
- Eventos destacados

Genera el reporte JSON en el ciclo indicado (por defecto 10).
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

from models.agent_state import AgentAction, AgentDecision, AgentType

if TYPE_CHECKING:
    from simulation.environment import Environment

logger = logging.getLogger(__name__)


class ReportCollector:
    def __init__(self, report_at_cycle: int = 10, output_dir: str = "reports") -> None:
        self.report_at_cycle = report_at_cycle
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

        # Datos que se acumulan ciclo a ciclo
        self.initial_params: dict = {}
        self.cytokine_history: list[dict] = []          # [{"cycle": N, "IL-6": x, ...}]
        self.population_history: list[dict] = []        # [{"cycle": N, "TumorCell": x, ...}]
        self.decision_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self.notable_events: list[str] = []
        self.opus_prediction: str = ""
        self.final_agent_states: list[dict] = []        # estado en report_at_cycle
        self._report_generated = False

    def record_initial_params(self, env: "Environment") -> None:
        """Captura parámetros iniciales antes del primer ciclo."""
        counts: dict[str, int] = defaultdict(int)
        for agent in env.agents.values():
            counts[agent.state.agent_type.value] += 1
        self.initial_params = {
            "grid_size": env.grid_size,
            "agents_by_type": dict(counts),
            "total_agents": len(env.agents),
        }

    def record_cycle(
        self,
        env: "Environment",
        decisions: dict[str, AgentDecision],
    ) -> None:
        """Llamado al final de cada ciclo para registrar estado y decisiones."""
        cycle = env.cycle

        # Población
        pop: dict[str, int] = defaultdict(int)
        for agent in env.agents.values():
            pop[agent.state.agent_type.value] += 1
        self.population_history.append({"cycle": cycle, **dict(pop)})

        # Citoquinas (media y max por campo)
        cyt_entry: dict = {"cycle": cycle}
        for cyt_name, field in env.cytokines.fields.items():
            cyt_entry[f"{cyt_name}_mean"] = round(float(field.mean()), 6)
            cyt_entry[f"{cyt_name}_max"] = round(float(field.max()), 6)
            cyt_entry[f"{cyt_name}_total"] = round(float(field.sum()), 4)
        self.cytokine_history.append(cyt_entry)

        # Decisiones
        for agent_id, decision in decisions.items():
            agent = env.agents.get(agent_id)
            if agent:
                atype = agent.state.agent_type.value
                self.decision_counts[atype][decision.action.value] += 1

        # Eventos nuevos desde el último ciclo
        # (env.events tiene todos; tomamos los del ciclo actual)
        cycle_prefix = f"[C{cycle:04d}]"
        new_events = [e for e in env.events if e.startswith(cycle_prefix)]
        self.notable_events.extend(new_events)

        # Snapshot completo en el ciclo objetivo
        if cycle == self.report_at_cycle and not self._report_generated:
            self._capture_agent_states(env)

    def _capture_agent_states(self, env: "Environment") -> None:
        """Captura posición y estado de cada agente en el ciclo objetivo."""
        for agent in env.agents.values():
            state = agent.state
            entry = {
                "agent_id": state.agent_id,
                "agent_type": state.agent_type.value,
                "position": {
                    "x": round(state.position[0], 2),
                    "y": round(state.position[1], 2),
                },
                "energy": round(state.energy, 3),
                "age": state.age,
                "alive": state.alive,
                "metadata": {k: v for k, v in state.metadata.items()},
            }
            self.final_agent_states.append(entry)

    def set_opus_prediction(self, analysis: str) -> None:
        self.opus_prediction = analysis

    def generate_report(self, env: "Environment") -> Path:
        """Genera el JSON final y lo guarda en disco."""
        cycle = self.report_at_cycle

        # Estado final de citoquinas en el ciclo del reporte
        cyt_at_report = next(
            (c for c in self.cytokine_history if c["cycle"] == cycle),
            self.cytokine_history[-1] if self.cytokine_history else {},
        )

        # Población en el ciclo del reporte
        pop_at_report = next(
            (p for p in self.population_history if p["cycle"] == cycle),
            self.population_history[-1] if self.population_history else {},
        )

        # Formatear decision_counts como dict normal (no defaultdict)
        decisions_clean = {
            atype: dict(actions)
            for atype, actions in self.decision_counts.items()
        }

        report = {
            "report_metadata": {
                "generated_at_cycle": cycle,
                "report_file": f"reports/cycle{cycle}_report.json",
            },
            "initial_parameters": self.initial_params,
            "state_at_cycle": {
                "cycle": cycle,
                "population_by_type": {k: v for k, v in pop_at_report.items() if k != "cycle"},
                "agents": self.final_agent_states,
            },
            "cytokine_levels_by_cycle": self.cytokine_history,
            "cytokine_state_at_report_cycle": {
                k: v for k, v in cyt_at_report.items() if k != "cycle"
            },
            "decisions_summary": decisions_clean,
            "notable_events": self.notable_events[:100],  # máx 100 eventos
            "opus_prediction": self.opus_prediction or "(análisis Opus aún no disponible en ciclo 10)",
        }

        output_path = self.output_dir / f"cycle{cycle}_report.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        logger.info("Reporte guardado: %s", output_path)
        self._report_generated = True
        return output_path
