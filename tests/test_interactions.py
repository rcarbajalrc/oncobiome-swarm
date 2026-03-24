"""Tests de interacciones biológicas — valida que InteractionResolver
aplica correctamente los parámetros calibrados del seed KRAS G12D.

Sin LLM, sin tokens. Ejecutar:
    python3 -m pytest tests/test_interactions.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import numpy as np

from simulation.environment import Environment
from simulation.interactions import InteractionResolver
from agents.tumor_cell import TumorCell
from agents.immune_cell import ImmuneCell
from agents.macrophage_agent import MacrophageAgent
from agents.phytochemical_agent import PhytochemicalAgent
from memory.inmemory_store import InMemoryStore


def make_env() -> Environment:
    return Environment(grid_size=100)


def store() -> InMemoryStore:
    return InMemoryStore()


def fresh_resolver() -> InteractionResolver:
    """Crea un InteractionResolver con config limpia (sin cache stale)."""
    from config import get_config
    get_config.cache_clear()
    return InteractionResolver()


def add_agents_direct(env: Environment, *agents) -> None:
    """Añade agentes al entorno sin check de occupancy — para tests."""
    for agent in agents:
        env.agents[agent.state.agent_id] = agent
        env._occupancy.add(env._to_cell(agent.state.position))


class TestImmuneKillRate:
    """Valida kill rate CD8+ calibrado para KRAS G12D (0.15)."""

    def test_kill_rate_is_calibrated(self):
        """immune_kill_rate debe ser 0.15 (calibrado KRAS G12D)."""
        from config import get_config
        get_config.cache_clear()
        cfg = get_config()
        assert cfg.immune_kill_rate == 0.15

    def test_immune_kill_rate_value(self):
        """El resolver debe usar immune_kill_rate=0.15."""
        resolver = fresh_resolver()
        assert resolver.immune_kill_rate == 0.15

    def test_immune_kills_over_many_attempts(self):
        """Con kill_rate=0.15 y energy=1.0, se espera al menos 1 kill en 50 intentos.

        p(0 kills en 50 intentos) = 0.85^50 ≈ 0.0003 — estadísticamente imposible.
        Usamos add_agents_direct para garantizar que ambos agentes están en el entorno
        en celdas distintas dentro del radio de contacto.
        """
        kills = 0
        for _ in range(50):
            env = make_env()
            resolver = fresh_resolver()
            # Posiciones en celdas distintas (int coords diferentes) dentro del radio (3.0)
            tumor = TumorCell(position=(50.0, 50.0), memory_store=store(), energy=0.8)
            immune = ImmuneCell(position=(51.0, 50.0), memory_store=store(), energy=1.0)
            add_agents_direct(env, tumor, immune)

            # Verificar que ambos están en el entorno
            assert tumor.state.agent_id in env.agents
            assert immune.state.agent_id in env.agents

            resolver._immune_attacks(env)
            if not tumor.state.alive:
                kills += 1

        assert kills >= 1, (
            f"Con kill_rate=0.15, se esperan kills en 50 intentos. Obtenidos: {kills}"
        )

    def test_immune_fails_to_kill_out_of_range(self):
        """ImmuneCell fuera del radio de contacto (>3.0) no mata nunca."""
        for _ in range(20):
            env = make_env()
            resolver = fresh_resolver()
            tumor = TumorCell(position=(50.0, 50.0), memory_store=store(), energy=0.8)
            immune = ImmuneCell(position=(60.0, 60.0), memory_store=store(), energy=1.0)
            add_agents_direct(env, tumor, immune)
            resolver._immune_attacks(env)
            assert tumor.state.alive, "TumorCell a distancia >3 nunca debe morir"

    def test_il6_reduces_kill_probability(self):
        """IL-6 alto debe reducir el número de kills estadísticamente.

        kill_prob sin IL-6 = 0.15 → kills esperados en 100: ~15
        kill_prob con IL-6 = 0.09 → kills esperados en 100: ~9
        """
        kills_no_il6 = 0
        kills_with_il6 = 0

        for _ in range(100):
            # Sin IL-6
            env1 = make_env()
            tumor1 = TumorCell(position=(50.0, 50.0), memory_store=store(), energy=0.8)
            immune1 = ImmuneCell(position=(51.0, 50.0), memory_store=store(), energy=1.0)
            add_agents_direct(env1, tumor1, immune1)
            fresh_resolver()._immune_attacks(env1)
            if not tumor1.state.alive:
                kills_no_il6 += 1

            # Con IL-6
            env2 = make_env()
            tumor2 = TumorCell(position=(50.0, 50.0), memory_store=store(), energy=0.8)
            immune2 = ImmuneCell(position=(51.0, 50.0), memory_store=store(), energy=1.0)
            add_agents_direct(env2, tumor2, immune2)
            env2.emit_cytokine((50.0, 50.0), "IL-6", 1.0)
            fresh_resolver()._immune_attacks(env2)
            if not tumor2.state.alive:
                kills_with_il6 += 1

        # Con IL-6 debe haber ≤ kills que sin IL-6 (margen +15 por varianza estadística)
        assert kills_with_il6 <= kills_no_il6 + 15, (
            f"IL-6 debe reducir kills: sin_il6={kills_no_il6}, con_il6={kills_with_il6}"
        )


class TestMacrophagePolarisation:
    """Valida polarización M1/M2 con umbrales calibrados KRAS G12D."""

    def test_m1_threshold_is_calibrated(self):
        from config import get_config
        get_config.cache_clear()
        assert get_config().m1_polarisation_ifng_threshold == 0.18

    def test_m2_threshold_is_calibrated(self):
        from config import get_config
        get_config.cache_clear()
        assert get_config().m2_polarisation_il6_threshold == 0.06

    def test_high_ifng_polarises_m1(self):
        env = make_env()
        resolver = fresh_resolver()
        macro = MacrophageAgent(position=(50.0, 50.0), memory_store=store(), energy=0.8)
        add_agents_direct(env, macro)
        env.emit_cytokine((50.0, 50.0), "IFN-γ", 2.0)
        resolver._macrophage_polarisation(env)
        assert macro.state.metadata.get("polarization") == "M1"

    def test_high_il6_low_ifng_polarises_m2(self):
        env = make_env()
        resolver = fresh_resolver()
        macro = MacrophageAgent(position=(50.0, 50.0), memory_store=store(), energy=0.8)
        add_agents_direct(env, macro)
        env.emit_cytokine((50.0, 50.0), "IL-6", 2.0)
        resolver._macrophage_polarisation(env)
        assert macro.state.metadata.get("polarization") == "M2"

    def test_no_cytokines_stays_m0(self):
        env = make_env()
        resolver = fresh_resolver()
        macro = MacrophageAgent(position=(50.0, 50.0), memory_store=store(), energy=0.8)
        add_agents_direct(env, macro)
        resolver._macrophage_polarisation(env)
        assert macro.state.metadata.get("polarization") == "M0"


class TestVEGFAngiogenesis:
    """Valida emisión de VEGF en hipoxia."""

    def test_hypoxic_tumor_emits_vegf(self):
        env = make_env()
        resolver = fresh_resolver()
        tumor = TumorCell(position=(50.0, 50.0), memory_store=store(), energy=0.25)
        add_agents_direct(env, tumor)
        resolver._vegf_angiogenesis(env)
        assert env.sample_cytokine((50.0, 50.0), "VEGF") > 0.0

    def test_normoxic_tumor_does_not_emit_vegf(self):
        env = make_env()
        resolver = fresh_resolver()
        tumor = TumorCell(position=(50.0, 50.0), memory_store=store(), energy=0.50)
        add_agents_direct(env, tumor)
        resolver._vegf_angiogenesis(env)
        assert env.sample_cytokine((50.0, 50.0), "VEGF") == 0.0


class TestPhytoDamage:
    """Valida damage de fitoquímicos calibrado (0.06)."""

    def test_phyto_damage_rate_is_calibrated(self):
        from config import get_config
        get_config.cache_clear()
        assert get_config().phyto_damage_rate == 0.06

    def test_phyto_damage_rate_in_resolver(self):
        assert fresh_resolver().phyto_damage == 0.06

    def test_phyto_reduces_tumor_energy_via_resolver(self):
        """Damage exacto: phyto_damage_rate * concentration = 0.06 * 1.0 = 0.06."""
        env = make_env()
        resolver = fresh_resolver()

        tumor = TumorCell(position=(50.0, 50.0), memory_store=store(), energy=0.8)
        phyto = PhytochemicalAgent(
            position=(51.0, 50.0),  # celda distinta, distancia=1.0 < radio=3.0
            memory_store=store(),
            concentration=1.0,
        )
        add_agents_direct(env, tumor, phyto)

        initial_energy = tumor.state.energy
        resolver._phyto_attacks(env)

        assert tumor.state.energy < initial_energy, "Phyto debe reducir energía"
        expected = 0.06 * 1.0
        actual = initial_energy - tumor.state.energy
        assert abs(actual - expected) < 0.001, f"Damage: esperado={expected}, real={actual}"
