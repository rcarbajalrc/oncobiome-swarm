from __future__ import annotations

from pydantic import BaseModel


class CytokineSummary(BaseModel):
    mean: float
    max: float
    total: float


class AgentSummary(BaseModel):
    agent_id: str
    agent_type: str
    energy: float
    age: int
    position: tuple[float, float]
    metadata_summary: str = ""


class SwarmSnapshot(BaseModel):
    cycle: int
    population_counts: dict[str, int]
    cytokine_summary: dict[str, CytokineSummary]
    recent_events: list[str]
    agent_summaries: list[AgentSummary]

    def to_prompt_text(self) -> str:
        lines = [
            f"=== SWARM SNAPSHOT — Cycle {self.cycle} ===",
            "",
            "POPULATION:",
        ]
        for agent_type, count in self.population_counts.items():
            lines.append(f"  {agent_type}: {count}")

        lines.append("")
        lines.append("CYTOKINE FIELDS:")
        for ctype, summary in self.cytokine_summary.items():
            lines.append(
                f"  {ctype}: mean={summary.mean:.4f}  max={summary.max:.4f}  total={summary.total:.2f}"
            )

        if self.recent_events:
            lines.append("")
            lines.append("RECENT EVENTS (last 20):")
            for event in self.recent_events[-20:]:
                lines.append(f"  • {event}")

        if self.agent_summaries:
            lines.append("")
            lines.append(f"AGENT DETAILS (top {len(self.agent_summaries)} by relevance):")
            for a in self.agent_summaries:
                meta = f" [{a.metadata_summary}]" if a.metadata_summary else ""
                lines.append(
                    f"  [{a.agent_type}] id={a.agent_id}  energy={a.energy:.2f}"
                    f"  age={a.age}  pos=({a.position[0]:.1f},{a.position[1]:.1f}){meta}"
                )

        return "\n".join(lines)
