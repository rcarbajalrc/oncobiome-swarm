"""Dashboard Plotly Dash en tiempo real.

Se ejecuta en un daemon thread para no bloquear asyncio.
El estado se comparte vía referencia al Environment con threading.Lock.

SECURITY: el dashboard escucha en 127.0.0.1 (localhost only).
No exponer a 0.0.0.0 — no tiene autenticación.
"""
from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

import dash
from dash import dcc, html
from dash.dependencies import Input, Output

from config import get_config
from models.cytokine_state import CytokineType
from viz.figures import make_heatmap_figure, make_scatter_figure, make_timeseries_figure

if TYPE_CHECKING:
    from simulation.environment import Environment

logger = logging.getLogger(__name__)


class OncobiomeDashboard:
    def __init__(self, env: "Environment") -> None:
        self._env = env
        self._lock = threading.Lock()
        self._cfg = get_config()
        self._app = self._build_app()
        self._thread: threading.Thread | None = None

    def _build_app(self) -> dash.Dash:
        app = dash.Dash(
            __name__,
            title="OncoBiome Swarm",
            suppress_callback_exceptions=True,
        )

        cytokine_options = [{"label": ct.value, "value": ct.value} for ct in CytokineType]

        app.layout = html.Div(
            style={"backgroundColor": "#0d0d1a", "minHeight": "100vh", "padding": "20px"},
            children=[
                html.H1(
                    "OncoBiome Swarm — TME Simulation",
                    style={"color": "#e0e0ff", "textAlign": "center", "fontFamily": "monospace"},
                ),
                dcc.Interval(
                    id="interval",
                    interval=self._cfg.dashboard_refresh_ms,
                    n_intervals=0,
                ),
                html.Div(
                    style={"display": "flex", "gap": "10px"},
                    children=[
                        html.Div(style={"flex": "1"}, children=[dcc.Graph(id="scatter-plot", style={"height": "450px"})]),
                        html.Div(
                            style={"flex": "1"},
                            children=[
                                dcc.Dropdown(
                                    id="cytokine-selector",
                                    options=cytokine_options,
                                    value=CytokineType.IL6.value,
                                    style={"backgroundColor": "#1a1a2e", "color": "#e0e0ff", "marginBottom": "5px"},
                                    clearable=False,
                                ),
                                dcc.Graph(id="heatmap-plot", style={"height": "410px"}),
                            ],
                        ),
                    ],
                ),
                html.Div(
                    style={"display": "flex", "gap": "10px", "marginTop": "10px"},
                    children=[
                        html.Div(style={"flex": "1"}, children=[dcc.Graph(id="timeseries-plot", style={"height": "350px"})]),
                        html.Div(
                            style={"flex": "1"},
                            children=[
                                html.H3("Opus Analysis", style={"color": "#9b59b6", "fontFamily": "monospace"}),
                                html.Div(
                                    id="opus-analysis",
                                    style={
                                        "color": "#c0c0e0", "fontFamily": "monospace", "fontSize": "13px",
                                        "backgroundColor": "#111130", "padding": "15px", "borderRadius": "8px",
                                        "height": "280px", "overflowY": "auto", "whiteSpace": "pre-wrap",
                                    },
                                ),
                            ],
                        ),
                    ],
                ),
                html.Div(
                    id="status-bar",
                    style={"color": "#666", "fontFamily": "monospace", "fontSize": "12px",
                           "textAlign": "center", "marginTop": "10px"},
                ),
            ],
        )

        self._register_callbacks(app)
        return app

    def _register_callbacks(self, app: dash.Dash) -> None:
        @app.callback(
            Output("scatter-plot", "figure"),
            Output("heatmap-plot", "figure"),
            Output("timeseries-plot", "figure"),
            Output("opus-analysis", "children"),
            Output("status-bar", "children"),
            Input("interval", "n_intervals"),
            Input("cytokine-selector", "value"),
        )
        def update_all(n_intervals: int, cytokine: str):
            with self._lock:
                env = self._env
                agents = dict(env.agents)
                grid_size = env.grid_size
                history = list(env.history)
                opus = env.last_opus_analysis
                cycle = env.cycle
                field = env.cytokines.fields.get(cytokine, None)
                import numpy as np
                field_copy = field.copy() if field is not None else np.zeros((grid_size, grid_size))

            scatter = make_scatter_figure(agents, grid_size)
            heatmap = make_heatmap_figure(field_copy, cytokine)
            timeseries = make_timeseries_figure(history)
            status = f"Cycle: {cycle}  |  Agents: {len(agents)}  |  Refresh: {n_intervals}"
            return scatter, heatmap, timeseries, opus, status

    def start(self) -> None:
        """Lanza el servidor Dash en un daemon thread.

        SECURITY: host='127.0.0.1' — accesible solo desde localhost.
        No usar '0.0.0.0' — el dashboard no tiene autenticación.
        """
        port = self._cfg.dashboard_port

        def _run():
            logger.info("Dashboard disponible en http://localhost:%d", port)
            self._app.run(
                debug=False,
                use_reloader=False,
                port=port,
                host="127.0.0.1",  # localhost only — SECURITY
            )

        self._thread = threading.Thread(target=_run, daemon=True, name="DashThread")
        self._thread.start()


def start_dashboard(env: "Environment", port: int | None = None) -> "OncobiomeDashboard":
    """Convenience function usada desde main.py."""
    dash_app = OncobiomeDashboard(env)
    dash_app.start()
    return dash_app
