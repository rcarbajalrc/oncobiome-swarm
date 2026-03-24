"""Funciones puras que generan figuras Plotly.

Todas las funciones reciben datos y devuelven go.Figure.
Sin estado, sin efectos secundarios.
"""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from models.agent_state import AgentType

# Paleta de colores por tipo de agente
_COLORS: dict[str, str] = {
    AgentType.TUMOR_CELL.value: "#e74c3c",
    AgentType.IMMUNE_CELL.value: "#2ecc71",
    AgentType.MACROPHAGE.value: "#f39c12",
    AgentType.PHYTOCHEMICAL.value: "#9b59b6",
    AgentType.CYTOKINE.value: "#3498db",
}

_SYMBOLS: dict[str, str] = {
    AgentType.TUMOR_CELL.value: "circle",
    AgentType.IMMUNE_CELL.value: "triangle-up",
    AgentType.MACROPHAGE.value: "square",
    AgentType.PHYTOCHEMICAL.value: "diamond",
    AgentType.CYTOKINE.value: "cross",
}


def make_scatter_figure(agents: dict, grid_size: int) -> go.Figure:
    """Scatter plot 2D de posiciones de agentes, coloreado por tipo."""
    fig = go.Figure()

    by_type: dict[str, list] = {}
    for agent in agents.values():
        t = agent.state.agent_type.value
        by_type.setdefault(t, []).append(agent)

    for agent_type, agent_list in by_type.items():
        xs = [a.state.position[0] for a in agent_list]
        ys = [a.state.position[1] for a in agent_list]
        energies = [a.state.energy for a in agent_list]
        ids = [a.state.agent_id for a in agent_list]
        hover_texts = [
            f"ID: {aid}<br>Energy: {e:.2f}<br>Age: {a.state.age}"
            + (f"<br>{list(a.state.metadata.items())[:2]}" if a.state.metadata else "")
            for aid, e, a in zip(ids, energies, agent_list)
        ]

        fig.add_trace(go.Scatter(
            x=xs,
            y=ys,
            mode="markers",
            name=agent_type,
            marker=dict(
                color=_COLORS.get(agent_type, "#95a5a6"),
                symbol=_SYMBOLS.get(agent_type, "circle"),
                size=[max(6, int(e * 14)) for e in energies],
                opacity=0.85,
                line=dict(width=0.5, color="white"),
            ),
            text=hover_texts,
            hovertemplate="%{text}<extra></extra>",
        ))

    fig.update_layout(
        title="Tumor Microenvironment — Agent Positions",
        xaxis=dict(range=[0, grid_size], title="X", showgrid=False),
        yaxis=dict(range=[0, grid_size], title="Y", showgrid=False, scaleanchor="x"),
        plot_bgcolor="#111111",
        paper_bgcolor="#1a1a2e",
        font=dict(color="white"),
        legend=dict(bgcolor="rgba(0,0,0,0.5)"),
        margin=dict(l=40, r=20, t=50, b=40),
    )
    return fig


def make_heatmap_figure(field: np.ndarray, cytokine_name: str) -> go.Figure:
    """Heatmap de concentración de citoquina."""
    fig = go.Figure(data=go.Heatmap(
        z=field,
        colorscale="Hot",
        showscale=True,
        colorbar=dict(title=dict(text="Concentration", side="right")),
        zmin=0,
        zmax=max(float(field.max()), 0.01),
    ))
    fig.update_layout(
        title=f"Cytokine Field: {cytokine_name}",
        xaxis=dict(title="X", showgrid=False),
        yaxis=dict(title="Y", showgrid=False),
        plot_bgcolor="#111111",
        paper_bgcolor="#1a1a2e",
        font=dict(color="white"),
        margin=dict(l=40, r=20, t=50, b=40),
    )
    return fig


def make_timeseries_figure(history: list[dict]) -> go.Figure:
    """Línea temporal de conteos por tipo de agente."""
    if not history:
        return go.Figure()

    # El history guarda dicts {agent_type: count} sin clave "cycle".
    # Usamos índice+1 como número de ciclo — corrección del bug original.
    cycles = [h.get("cycle", i + 1) for i, h in enumerate(history)]

    fig = go.Figure()
    agent_types = [t.value for t in AgentType if t != AgentType.CYTOKINE]
    for agent_type in agent_types:
        counts = [h.get(agent_type, 0) for h in history]
        fig.add_trace(go.Scatter(
            x=cycles,
            y=counts,
            mode="lines",
            name=agent_type,
            line=dict(color=_COLORS.get(agent_type, "#95a5a6"), width=2),
        ))

    fig.update_layout(
        title="Population Dynamics Over Time",
        xaxis=dict(title="Cycle", showgrid=True, gridcolor="#333"),
        yaxis=dict(title="Count", showgrid=True, gridcolor="#333"),
        plot_bgcolor="#111111",
        paper_bgcolor="#1a1a2e",
        font=dict(color="white"),
        legend=dict(bgcolor="rgba(0,0,0,0.5)"),
        margin=dict(l=40, r=20, t=50, b=40),
    )
    return fig
