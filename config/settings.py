from __future__ import annotations

import sys
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class SimulationConfig(BaseSettings):
    """Configuración calibrada para KRAS G12D PDAC/CRC.

    Parámetros derivados de fuentes primarias verificadas.
    Ver config/biological_seed.py para referencias completas.

    SECURITY: anthropic_api_key se valida en validate_api_key().
    La validación ocurre en main.py antes de cualquier llamada LLM.

    Sprint 4: añadidos parámetros NK y DC.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # API keys
    anthropic_api_key: str = ""
    mem0_api_key:      str = ""

    # ── LLM Provider ──────────────────────────────────────────────────────────
    llm_provider:       str = "anthropic"
    ollama_base_url:    str = "http://localhost:11434"
    ollama_agent_model: str = "llama3.1:8b"

    # Models
    haiku_model: str = "claude-haiku-4-5-20251001"
    sonnet_model: str = "claude-sonnet-4-5-20250929"  # Sprint 7A: multi-LLM
    opus_model:  str = "claude-opus-4-5-20251101"

    # Grid
    grid_size:            int   = 100
    interaction_radius:   float = 10.0
    proliferation_radius: float = 3.0

    # ── Población inicial — KRAS G12D PDAC seed ───────────────────────────────
    n_tumor_cells:      int = 12
    n_immune_cells:     int = 5
    n_macrophages:      int = 3
    n_phytochemicals:   int = 2
    n_nk_cells:         int = 0   # Sprint 4: NK cells (default 0 = backward compatible)
    n_dendritic_cells:  int = 0   # Sprint 4: DC cells (default 0 = backward compatible)

    # Simulation
    total_cycles:           int = 77
    opus_analysis_interval: int = 25

    # LLM concurrency & rate limiting
    llm_concurrency:      int   = 6
    llm_max_retries:      int   = 3
    llm_inter_call_delay: float = 0.0
    llm_rps_window:       float = 60.0
    llm_rps_max:          int   = 0

    # Token limits
    haiku_max_tokens: int = 50
    opus_max_tokens:  int = 800

    # Smart LLM skip
    llm_skip_enabled:    bool  = True
    llm_skip_energy_min: float = 0.35
    llm_skip_energy_max: float = 0.95

    # ── Citoquinas — TME denso PDAC ───────────────────────────────────────────
    cytokine_decay:           float = 0.04
    cytokine_diffusion_sigma: float = 1.8
    cytokine_emit_amount:     float = 0.30

    # ── Energética — PANC-1 KRAS G12D ─────────────────────────────────────────
    tumor_initial_energy:                float = 0.75
    immune_initial_energy:               float = 0.85
    macrophage_initial_energy:           float = 0.80
    phytochemical_initial_concentration: float = 1.0
    phytochemical_ttl:                   int   = 28
    cytokine_ttl:                        int   = 10

    # ── Kill probabilities ────────────────────────────────────────────────────
    immune_kill_rate:       float = 0.15
    macrophage_m1_kill_rate: float = 0.08
    phyto_damage_rate:      float = 0.06

    # ── CD8+ exhaustion ───────────────────────────────────────────────────────
    # Calibrado: CD8+ en TME KRAS G12D se agotan antes que NK (Nat Immunol 2021)
    immune_exhaustion_age:   int = 15   # ciclos → agotamiento funcional CD8+
    immune_exhaustion_kills: int = 2    # muertes → agotamiento funcional CD8+

    # ── IL-6 immunosuppression (CD8+) ─────────────────────────────────────────
    # KRAS G12D activa IL-6/JAK-STAT3 → suprime citotoxicidad CD8+
    # Fuente: Frontiers/Medicine 2024
    il6_immune_suppression_threshold: float = 0.06   # umbral IL-6 para suprimir CD8+
    il6_immune_suppression_factor:    float = 0.60   # kill_prob × 0.60 cuando IL-6 > umbral

    # ── Natural Killer cell parameters (Sprint 4) ─────────────────────────────
    # Kill 20-30% en condiciones ideales (Clin Cancer Res 2020),
    # reducido a 0.10 en TME KRAS G12D por supresión IL-6.
    # Fuente: Nat Immunol 2021.
    nk_kill_rate:                 float = 0.10   # < CD8+ (0.15): mayor resistencia KRAS G12D
    nk_initial_energy:            float = 0.80
    nk_exhaustion_age:            int   = 20     # más resistente que CD8+ (15)
    nk_exhaustion_kills:          int   = 3      # kills antes del agotamiento funcional
    nk_il6_suppression_threshold: float = 0.04  # más sensible a IL-6 que CD8+ (0.06)
    nk_il6_suppression_factor:    float = 0.60  # supresión del 40% por IL-6

    # ── Dendritic cell parameters (Sprint 4) ──────────────────────────────────
    # DC maduras activan CD8+ y NK (Immunity 2023).
    # KRAS G12D suprime maduración DC → umbral más alto.
    dc_initial_energy:            float = 0.80
    dc_maturation_ifng_threshold: float = 0.05  # IFN-γ > 0.05 → DC inicia maduración
    dc_activation_boost:          float = 0.20  # +20% kill_rate CD8+/NK en radio
    dc_activation_radius:         float = 12.0  # radio de activación
    dc_maturation_cycles:         int   = 3     # ciclos con IFN-γ para completar maduración

    # ── Polarización macrófagos ───────────────────────────────────────────────
    # Umbral M1 alto (0.18): más difícil activar M1 en TME rico en IL-6
    # Umbral M2 bajo (0.06): sesgo pro-tumoral temprano KRAS G12D
    # Fuente: Frontiers/Medicine 2024
    m1_polarisation_ifng_threshold: float = 0.18
    m2_polarisation_il6_threshold:  float = 0.06

    # Population cap
    max_agents: int = 150

    # Radio para contexto LLM
    llm_context_radius:   float = 12.0
    llm_bootstrap_cycles: int   = 5

    # Dashboard
    dashboard_port:       int = 8051
    dashboard_refresh_ms: int = 2000

    @property
    def use_mem0(self) -> bool:
        return bool(self.mem0_api_key)

    @property
    def use_ollama(self) -> bool:
        return self.llm_provider.lower() == "ollama"

    def validate_api_key(self, no_llm: bool = False) -> None:
        """Fuerza SystemExit si la API key es necesaria pero está vacía."""
        if no_llm:
            return

        if self.use_ollama:
            if not self.ollama_base_url:
                print("ERROR: OLLAMA_BASE_URL no configurada.", file=sys.stderr)
                sys.exit(1)
            if not self.anthropic_api_key:
                import logging
                logging.getLogger(__name__).warning(
                    "ANTHROPIC_API_KEY vacía — análisis Opus desactivado."
                )
            return

        if not self.anthropic_api_key:
            print(
                "ERROR: ANTHROPIC_API_KEY no está configurada.\n"
                "  1. Copia .env.example a .env\n"
                "  2. Añade tu clave: ANTHROPIC_API_KEY=sk-ant-...\n"
                "  Alternativa sin coste: python main.py --no-llm",
                file=sys.stderr,
            )
            sys.exit(1)

        if not self.anthropic_api_key.startswith("sk-ant-"):
            print(
                "ERROR: ANTHROPIC_API_KEY no tiene el formato esperado "
                "(debe empezar por 'sk-ant-').",
                file=sys.stderr,
            )
            sys.exit(1)


@lru_cache(maxsize=1)
def get_config() -> SimulationConfig:
    return SimulationConfig()
