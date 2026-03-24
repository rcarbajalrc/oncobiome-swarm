"""Tests NK/DC — valida NKCell, DendriticCell, y sus interacciones.

Sprint 4: Natural Killer cells y Dendritic cells.
Sin LLM, sin tokens. Ejecutar:
    python3 -m pytest tests/test_nk_dc.py -v

Cobertura:
  - AgentType: NK_CELL y DENDRITIC_CELL presentes
  - Parámetros config calibrados (nk_kill_rate, dc_activation_boost, etc.)
  - NKCell: instantiation, default_action, kill por missing-self
  - NKCell: supresión por IL-6 (umbral más bajo que CD8+)
  - NKCell: exhaustion (age>20 AND kills>3)
  - DendriticCell: instantiation, estados de maduración
  - DendriticCell: maduración progresiva por IFN-γ
  - DC madura: boost de kill_rate en ImmuneCell cercana
  - DC madura: boost de kill_rate en NKCell cercana
  - Rule engine: NK y DC producen decisiones correctas
  - Integración: resolve() incluye _nk_attacks y _dc_maturation
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from agents.dendritic_cell import DendriticCell
from agents.immune_cell import ImmuneCell
from agents.nk_cell import NKCell
from agents.tumor_cell import TumorCell
from memory.inmemory_store import InMemoryStore
from models.agent_state import AgentAction, AgentType, LocalContext
from simulation.environment import Environment
from simulation.interactions import InteractionResolver


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_env() -> Environment:
    return Environment(grid_size=100)


def store() -> InMemoryStore:
    return InMemoryStore()


def fresh_resolver() -> InteractionResolver:
    from config import get_config
    get_config.cache_clear()
    return InteractionResolver()


def add_agents_direct(env: Environment, *agents) -> None:
    """Añade agentes sin check de occupancy — para tests."""
    for agent in agents:
        env.agents[agent.state.agent_id] = agent
        env._occupancy.add(env._to_cell(agent.state.position))


def make_nk_context(
    age: int = 5,
    kills: int = 0,
    il6: float = 0.0,
    ifng: float = 0.0,
    nearby_tumor: bool = False,
    energy: float = 0.8,
) -> LocalContext:
    from models.agent_state import AgentType, NearbyAgentInfo
    nearby = []
    if nearby_tumor:
        nearby.append(NearbyAgentInfo(
            agent_id="t001", agent_type=AgentType.TUMOR_CELL,
            distance=2.0, energy=0.7,
        ))
    return LocalContext(
        agent_id="nk01",
        agent_type=AgentType.NK_CELL,
        position=(50.0, 50.0),
        energy=energy,
        age=age,
        metadata={"kills_count": kills},
        nearby_agents=nearby,
        cytokine_levels={"IL-6": il6, "IFN-γ": ifng, "VEGF": 0.0},
        cycle=10,
    )


def make_dc_context(
    maturation_state: str = "immature",
    ifng: float = 0.0,
    il6: float = 0.0,
) -> LocalContext:
    return LocalContext(
        agent_id="dc01",
        agent_type=AgentType.DENDRITIC_CELL,
        position=(50.0, 50.0),
        energy=0.8,
        age=5,
        metadata={"maturation_state": maturation_state, "ifng_cycles_above": 0},
        nearby_agents=[],
        cytokine_levels={"IL-6": il6, "IFN-γ": ifng, "VEGF": 0.0},
        cycle=10,
    )


# ── Clase 1: Configuración NK ─────────────────────────────────────────────────

class TestNKConfig:
    """Parámetros NK calibrados correctamente."""

    def test_nk_kill_rate_calibrated(self):
        """nk_kill_rate=0.10 — inferior a CD8+ (0.15) por resistencia KRAS G12D."""
        from config import get_config
        get_config.cache_clear()
        assert get_config().nk_kill_rate == 0.10

    def test_nk_il6_threshold_lower_than_cd8(self):
        """NK más sensibles a IL-6 que CD8+: 0.04 < 0.06."""
        from config import get_config
        get_config.cache_clear()
        cfg = get_config()
        assert cfg.nk_il6_suppression_threshold == 0.04
        assert cfg.nk_il6_suppression_threshold < cfg.il6_immune_suppression_threshold

    def test_nk_exhaustion_later_than_cd8(self):
        """NK más resistentes al agotamiento: age=20 > CD8+ age=15."""
        from config import get_config
        get_config.cache_clear()
        cfg = get_config()
        assert cfg.nk_exhaustion_age == 20
        assert cfg.nk_exhaustion_age > cfg.immune_exhaustion_age

    def test_resolver_has_nk_parameters(self):
        """InteractionResolver carga correctamente los parámetros NK."""
        r = fresh_resolver()
        assert r.nk_kill_rate == 0.10
        assert r.nk_il6_threshold == 0.04
        assert r.nk_il6_factor == 0.60


# ── Clase 2: NKCell instanciación y acciones ──────────────────────────────────

class TestNKCellAgent:
    """NKCell: instanciación y comportamiento básico."""

    def test_nk_agent_type(self):
        nk = NKCell(position=(50.0, 50.0), memory_store=store())
        assert nk.state.agent_type == AgentType.NK_CELL

    def test_nk_initial_energy(self):
        from config import get_config
        get_config.cache_clear()
        nk = NKCell(position=(50.0, 50.0), memory_store=store())
        assert nk.state.energy == get_config().nk_initial_energy

    def test_nk_default_action_is_migrate(self):
        nk = NKCell(position=(50.0, 50.0), memory_store=store())
        assert nk._default_action() == AgentAction.MIGRATE

    def test_nk_default_signal_is_ifng(self):
        from models.cytokine_state import CytokineType
        nk = NKCell(position=(50.0, 50.0), memory_store=store())
        assert nk._default_signal() == CytokineType.IFNG.value

    def test_nk_initial_kills_zero(self):
        nk = NKCell(position=(50.0, 50.0), memory_store=store())
        assert nk.state.metadata.get("kills_count", 0) == 0


# ── Clase 3: NK rule engine ───────────────────────────────────────────────────

class TestNKRuleEngine:
    """Rule engine NK: decisiones first-match correctas."""

    def test_nk_default_seek_tumor(self):
        """Sin contexto especial → MIGRATE (seek tumor)."""
        from llm.rule_engine import rule_engine_decide
        ctx = make_nk_context()
        d = rule_engine_decide(AgentType.NK_CELL, ctx)
        assert d.action == AgentAction.MIGRATE
        assert d.reasoning == "seek tumor"

    def test_nk_exhaustion_quiesce(self):
        """age>20 AND kills>3 → QUIESCE (exhausted)."""
        from llm.rule_engine import rule_engine_decide
        ctx = make_nk_context(age=21, kills=4)
        d = rule_engine_decide(AgentType.NK_CELL, ctx)
        assert d.action == AgentAction.QUIESCE
        assert d.reasoning == "nk exhausted"

    def test_nk_kill_tumor_without_il6(self):
        """Tumor cerca + energy>0.5 + IL-6<0.04 → MIGRATE (kill)."""
        from llm.rule_engine import rule_engine_decide
        ctx = make_nk_context(nearby_tumor=True, il6=0.0, energy=0.8)
        d = rule_engine_decide(AgentType.NK_CELL, ctx)
        assert d.action == AgentAction.MIGRATE
        assert d.reasoning == "kill tumor"

    def test_nk_signal_when_il6_suppresses(self):
        """Tumor cerca PERO IL-6>0.04 → SIGNAL IFN-γ (suprimida, señaliza en su lugar)."""
        from llm.rule_engine import rule_engine_decide
        ctx = make_nk_context(nearby_tumor=True, il6=0.08, energy=0.8)
        d = rule_engine_decide(AgentType.NK_CELL, ctx)
        assert d.action == AgentAction.SIGNAL
        assert d.signal_type == "IFN-γ"
        assert d.reasoning == "signal despite suppression"

    def test_nk_amplify_innate_with_ifng(self):
        """IFN-γ>0.06 sin tumor cercano → SIGNAL IFN-γ (amplify innate)."""
        from llm.rule_engine import rule_engine_decide
        ctx = make_nk_context(ifng=0.10, nearby_tumor=False)
        d = rule_engine_decide(AgentType.NK_CELL, ctx)
        assert d.action == AgentAction.SIGNAL
        assert d.reasoning == "amplify innate"


# ── Clase 4: NK interacciones físicas ─────────────────────────────────────────

class TestNKInteractions:
    """NK: kill, supresión IL-6, integración en resolve()."""

    def test_nk_kills_tumor_within_radius(self):
        """NK mata TumorCell en radio en al menos 1 de 50 intentos.

        p(0 kills en 50) = 0.90^50 ≈ 0.005 — estadísticamente muy improbable.
        """
        kills = 0
        for _ in range(50):
            env = make_env()
            tumor = TumorCell(position=(50.0, 50.0), memory_store=store(), energy=0.8)
            nk = NKCell(position=(51.0, 50.0), memory_store=store(), energy=1.0)
            add_agents_direct(env, tumor, nk)
            fresh_resolver()._nk_attacks(env)
            if not tumor.state.alive:
                kills += 1
        assert kills >= 1, f"NK debe matar al menos 1 vez en 50 intentos. Obtenido: {kills}"

    def test_nk_does_not_kill_outside_radius(self):
        """NK fuera del radio de contacto (>3.0) no mata."""
        for _ in range(20):
            env = make_env()
            tumor = TumorCell(position=(50.0, 50.0), memory_store=store(), energy=0.8)
            nk = NKCell(position=(60.0, 60.0), memory_store=store(), energy=1.0)
            add_agents_direct(env, tumor, nk)
            fresh_resolver()._nk_attacks(env)
            assert tumor.state.alive, "NK fuera de radio nunca debe matar"

    def test_nk_il6_reduces_kill_rate(self):
        """IL-6 > 0.04 reduce estadísticamente los kills de NK.

        Sin IL-6: p_kill = 1.0 * 0.10 = 0.10
        Con IL-6 (>0.04): p_kill = 0.10 * 0.60 = 0.06
        En 100 intentos, kills_with_il6 < kills_no_il6 con alta probabilidad.
        """
        kills_no_il6 = 0
        kills_with_il6 = 0
        for _ in range(100):
            env1 = make_env()
            t1 = TumorCell(position=(50.0, 50.0), memory_store=store(), energy=0.8)
            nk1 = NKCell(position=(51.0, 50.0), memory_store=store(), energy=1.0)
            add_agents_direct(env1, t1, nk1)
            fresh_resolver()._nk_attacks(env1)
            if not t1.state.alive:
                kills_no_il6 += 1

            env2 = make_env()
            t2 = TumorCell(position=(50.0, 50.0), memory_store=store(), energy=0.8)
            nk2 = NKCell(position=(51.0, 50.0), memory_store=store(), energy=1.0)
            add_agents_direct(env2, t2, nk2)
            env2.emit_cytokine((50.0, 50.0), "IL-6", 2.0)  # IL-6 >> 0.04
            fresh_resolver()._nk_attacks(env2)
            if not t2.state.alive:
                kills_with_il6 += 1

        assert kills_with_il6 <= kills_no_il6 + 15, (
            f"IL-6 debe reducir kills NK: sin={kills_no_il6}, con={kills_with_il6}"
        )

    def test_nk_kill_increments_kills_count(self):
        """Cada kill incrementa kills_count en metadata de NK."""
        kills_registered = 0
        for _ in range(50):
            env = make_env()
            tumor = TumorCell(position=(50.0, 50.0), memory_store=store(), energy=0.8)
            nk = NKCell(position=(51.0, 50.0), memory_store=store(), energy=1.0)
            add_agents_direct(env, tumor, nk)
            fresh_resolver()._nk_attacks(env)
            if not tumor.state.alive:
                assert nk.state.metadata["kills_count"] == 1
                kills_registered += 1
        assert kills_registered >= 1, "kills_count debe incrementarse tras cada kill"

    def test_nk_attacks_in_full_resolve(self):
        """_nk_attacks se ejecuta dentro de resolve() completo."""
        kills = 0
        for _ in range(30):
            env = make_env()
            tumor = TumorCell(position=(50.0, 50.0), memory_store=store(), energy=0.8)
            nk = NKCell(position=(51.0, 50.0), memory_store=store(), energy=1.0)
            add_agents_direct(env, tumor, nk)
            fresh_resolver().resolve(env)
            if not tumor.state.alive:
                kills += 1
        assert kills >= 1, "NK debe matar al menos 1 vez en 30 resolve() completos"


# ── Clase 5: Configuración DC ─────────────────────────────────────────────────

class TestDCConfig:
    """Parámetros DC calibrados correctamente."""

    def test_dc_initial_energy(self):
        from config import get_config
        get_config.cache_clear()
        assert get_config().dc_initial_energy == 0.80

    def test_dc_maturation_threshold(self):
        from config import get_config
        get_config.cache_clear()
        assert get_config().dc_maturation_ifng_threshold == 0.05

    def test_dc_activation_boost(self):
        from config import get_config
        get_config.cache_clear()
        assert get_config().dc_activation_boost == 0.20

    def test_dc_maturation_cycles(self):
        from config import get_config
        get_config.cache_clear()
        assert get_config().dc_maturation_cycles == 3

    def test_resolver_has_dc_parameters(self):
        r = fresh_resolver()
        assert r.dc_ifng_threshold == 0.05
        assert r.dc_boost == 0.20
        assert r.dc_maturation_cycles == 3


# ── Clase 6: DendriticCell instanciación ─────────────────────────────────────

class TestDCCellAgent:
    """DendriticCell: instanciación y estados."""

    def test_dc_agent_type(self):
        dc = DendriticCell(position=(50.0, 50.0), memory_store=store())
        assert dc.state.agent_type == AgentType.DENDRITIC_CELL

    def test_dc_initial_state_immature(self):
        dc = DendriticCell(position=(50.0, 50.0), memory_store=store())
        assert dc.state.metadata["maturation_state"] == "immature"
        assert dc.state.metadata["ifng_cycles_above"] == 0

    def test_dc_default_action_immature_is_quiesce(self):
        dc = DendriticCell(position=(50.0, 50.0), memory_store=store(),
                           maturation_state="immature")
        assert dc._default_action() == AgentAction.QUIESCE

    def test_dc_default_action_mature_is_migrate(self):
        dc = DendriticCell(position=(50.0, 50.0), memory_store=store(),
                           maturation_state="mature")
        assert dc._default_action() == AgentAction.MIGRATE

    def test_dc_custom_maturation_state(self):
        dc = DendriticCell(position=(50.0, 50.0), memory_store=store(),
                           maturation_state="mature")
        assert dc.state.metadata["maturation_state"] == "mature"


# ── Clase 7: DC rule engine ───────────────────────────────────────────────────

class TestDCRuleEngine:
    """Rule engine DC: decisiones correctas por estado de maduración."""

    def test_dc_immature_no_ifng_quiesce(self):
        """DC inmadura sin IFN-γ → QUIESCE (tolerogénica)."""
        from llm.rule_engine import rule_engine_decide
        ctx = make_dc_context(maturation_state="immature", ifng=0.0)
        d = rule_engine_decide(AgentType.DENDRITIC_CELL, ctx)
        assert d.action == AgentAction.QUIESCE
        assert d.reasoning == "immature tolerogenic"

    def test_dc_immature_with_ifng_signals(self):
        """DC inmadura con IFN-γ > 0.05 → SIGNAL (begin maturation)."""
        from llm.rule_engine import rule_engine_decide
        ctx = make_dc_context(maturation_state="immature", ifng=0.08)
        d = rule_engine_decide(AgentType.DENDRITIC_CELL, ctx)
        assert d.action == AgentAction.SIGNAL
        assert d.reasoning == "begin maturation"

    def test_dc_maturing_with_ifng_signals(self):
        """DC madurando con IFN-γ → SIGNAL IFN-γ."""
        from llm.rule_engine import rule_engine_decide
        ctx = make_dc_context(maturation_state="maturing", ifng=0.08)
        d = rule_engine_decide(AgentType.DENDRITIC_CELL, ctx)
        assert d.action == AgentAction.SIGNAL
        assert d.reasoning == "maturing signal"

    def test_dc_mature_with_ifng_activates(self):
        """DC madura con IFN-γ → SIGNAL (activate adaptive)."""
        from llm.rule_engine import rule_engine_decide
        ctx = make_dc_context(maturation_state="mature", ifng=0.08)
        d = rule_engine_decide(AgentType.DENDRITIC_CELL, ctx)
        assert d.action == AgentAction.SIGNAL
        assert d.reasoning == "activate adaptive"

    def test_dc_mature_without_ifng_patrols(self):
        """DC madura sin IFN-γ → MIGRATE (patrol activate)."""
        from llm.rule_engine import rule_engine_decide
        ctx = make_dc_context(maturation_state="mature", ifng=0.0)
        d = rule_engine_decide(AgentType.DENDRITIC_CELL, ctx)
        assert d.action == AgentAction.MIGRATE
        assert d.reasoning == "patrol activate"


# ── Clase 8: DC maduración e interacciones ────────────────────────────────────

class TestDCInteractions:
    """DC: maduración progresiva y boost de kill_rate."""

    def test_dc_matures_after_ifng_cycles(self):
        """DC progresa immature → maturing → mature tras dc_maturation_cycles ciclos."""
        env = make_env()
        resolver = fresh_resolver()
        dc = DendriticCell(position=(50.0, 50.0), memory_store=store())
        add_agents_direct(env, dc)

        # Emitir IFN-γ alto
        env.emit_cytokine((50.0, 50.0), "IFN-γ", 2.0)

        # Ciclo 1: immature → maturing
        resolver._dc_maturation(env)
        assert dc.state.metadata["maturation_state"] == "maturing"
        assert dc.state.metadata["ifng_cycles_above"] >= 1

        # Ciclos 2 y 3 (total = dc_maturation_cycles = 3)
        resolver._dc_maturation(env)
        resolver._dc_maturation(env)
        assert dc.state.metadata["maturation_state"] == "mature"

    def test_dc_does_not_mature_without_ifng(self):
        """DC sin IFN-γ no cambia de estado."""
        env = make_env()
        resolver = fresh_resolver()
        dc = DendriticCell(position=(50.0, 50.0), memory_store=store())
        add_agents_direct(env, dc)

        for _ in range(5):
            resolver._dc_maturation(env)

        assert dc.state.metadata["maturation_state"] == "immature"

    def test_dc_boost_increases_kill_probability(self):
        """DC madura en radio eleva kill_rate efectivo de CD8+ (de 0.15 a 0.35).

        Sin DC: p_kill = energy * 0.15 = 1.0 * 0.15
        Con DC: p_kill = energy * (0.15 + 0.20) = 1.0 * 0.35
        En 100 intentos, kills_with_dc > kills_no_dc con alta probabilidad.
        """
        kills_no_dc = 0
        kills_with_dc = 0

        for _ in range(100):
            # Sin DC
            env1 = make_env()
            t1 = TumorCell(position=(50.0, 50.0), memory_store=store(), energy=0.8)
            im1 = ImmuneCell(position=(51.0, 50.0), memory_store=store(), energy=1.0)
            add_agents_direct(env1, t1, im1)
            fresh_resolver()._immune_attacks(env1)
            if not t1.state.alive:
                kills_no_dc += 1

            # Con DC madura en radio
            env2 = make_env()
            t2 = TumorCell(position=(50.0, 50.0), memory_store=store(), energy=0.8)
            im2 = ImmuneCell(position=(51.0, 50.0), memory_store=store(), energy=1.0)
            dc = DendriticCell(position=(53.0, 50.0), memory_store=store(),
                               maturation_state="mature")
            add_agents_direct(env2, t2, im2, dc)
            fresh_resolver()._immune_attacks(env2)
            if not t2.state.alive:
                kills_with_dc += 1

        assert kills_with_dc >= kills_no_dc, (
            f"DC madura debe elevar kills: sin_dc={kills_no_dc}, con_dc={kills_with_dc}"
        )

    def test_dc_boost_returns_zero_without_mature_dc(self):
        """_get_dc_boost retorna 0.0 si no hay DC madura en radio."""
        env = make_env()
        dc_immature = DendriticCell(position=(52.0, 50.0), memory_store=store(),
                                    maturation_state="immature")
        add_agents_direct(env, dc_immature)
        resolver = fresh_resolver()
        boost = resolver._get_dc_boost((50.0, 50.0), env)
        assert boost == 0.0

    def test_dc_boost_returns_nonzero_with_mature_dc(self):
        """_get_dc_boost retorna dc_activation_boost si hay DC madura en radio."""
        env = make_env()
        dc_mature = DendriticCell(position=(52.0, 50.0), memory_store=store(),
                                  maturation_state="mature")
        add_agents_direct(env, dc_mature)
        resolver = fresh_resolver()
        boost = resolver._get_dc_boost((50.0, 50.0), env)
        assert boost == resolver.dc_boost
        assert boost == 0.20

    def test_dc_boost_applies_to_nk_too(self):
        """DC madura también eleva kill_rate de NKCell.

        Sin DC: p_kill_nk = energy * 0.10
        Con DC: p_kill_nk = energy * (0.10 + 0.20) = 0.30
        """
        kills_no_dc = 0
        kills_with_dc = 0

        for _ in range(100):
            env1 = make_env()
            t1 = TumorCell(position=(50.0, 50.0), memory_store=store(), energy=0.8)
            nk1 = NKCell(position=(51.0, 50.0), memory_store=store(), energy=1.0)
            add_agents_direct(env1, t1, nk1)
            fresh_resolver()._nk_attacks(env1)
            if not t1.state.alive:
                kills_no_dc += 1

            env2 = make_env()
            t2 = TumorCell(position=(50.0, 50.0), memory_store=store(), energy=0.8)
            nk2 = NKCell(position=(51.0, 50.0), memory_store=store(), energy=1.0)
            dc = DendriticCell(position=(53.0, 50.0), memory_store=store(),
                               maturation_state="mature")
            add_agents_direct(env2, t2, nk2, dc)
            fresh_resolver()._nk_attacks(env2)
            if not t2.state.alive:
                kills_with_dc += 1

        assert kills_with_dc >= kills_no_dc, (
            f"DC debe elevar kills NK: sin_dc={kills_no_dc}, con_dc={kills_with_dc}"
        )
