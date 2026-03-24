"""Rule Engine — motor de reglas determinista sin LLM.

Replica exactamente las reglas de llm/prompts.py en Python puro.
Permite validar dinámica biológica, citoquinas y eventos sin coste de API.

USO:
    from llm.rule_engine import rule_engine_decide
    decision = rule_engine_decide(agent_type, context)

COSTE: $0. Velocidad: 77 ciclos en <5 segundos.
PARIDAD: las reglas son idénticas a los prompts v4-deterministic.
         Cualquier cambio en prompts.py DEBE reflejarse aquí.

Sprint 4: añadidas reglas para NKCell y DendriticCell.
Validado contra: prompts v4-deterministic (llm/prompts.py)
"""
from __future__ import annotations

from models.agent_state import AgentAction, AgentDecision, AgentType, LocalContext


def rule_engine_decide(agent_type: AgentType, ctx: LocalContext) -> AgentDecision:
    """Aplica las reglas del prompt sin llamar al LLM.

    First-match: la primera regla que se cumple determina la acción.
    Misma lógica que los system prompts v4-deterministic.
    """
    if agent_type == AgentType.TUMOR_CELL:
        return _tumor_rules(ctx)
    elif agent_type == AgentType.IMMUNE_CELL:
        return _immune_rules(ctx)
    elif agent_type == AgentType.MACROPHAGE:
        return _macrophage_rules(ctx)
    elif agent_type == AgentType.NK_CELL:
        return _nk_rules(ctx)
    elif agent_type == AgentType.DENDRITIC_CELL:
        return _dc_rules(ctx)
    else:
        return AgentDecision(action=AgentAction.QUIESCE, reasoning="unknown type", confidence=0.8)


# ── Reglas TumorCell ──────────────────────────────────────────────────────────

def _tumor_rules(ctx: LocalContext) -> AgentDecision:
    """KRAS_G12D tumor cell — reglas first-match."""
    nearby_immune = [
        a for a in ctx.nearby_agents
        if a.agent_type == AgentType.IMMUNE_CELL
    ]
    il6 = ctx.cytokine_levels.get("IL-6", 0.0)

    if nearby_immune and ctx.energy > 0.5:
        return AgentDecision(action=AgentAction.SIGNAL, signal_type="IL-6",
                             reasoning="suppress immune", confidence=0.95)
    if nearby_immune and ctx.energy <= 0.5:
        return AgentDecision(action=AgentAction.MIGRATE,
                             reasoning="flee threat", confidence=0.9)
    if il6 > 0.05 and not nearby_immune:
        return AgentDecision(action=AgentAction.PROLIFERATE,
                             reasoning="safe niche", confidence=0.85)
    if ctx.energy > 0.7 and not nearby_immune:
        return AgentDecision(action=AgentAction.PROLIFERATE,
                             reasoning="expand uncontested", confidence=0.85)
    return AgentDecision(action=AgentAction.QUIESCE,
                         reasoning="conserve energy", confidence=0.8)


# ── Reglas ImmuneCell ─────────────────────────────────────────────────────────

def _immune_rules(ctx: LocalContext) -> AgentDecision:
    """CD8+ T cell — reglas first-match."""
    kills = ctx.metadata.get("kills_count", 0)
    ifng = ctx.cytokine_levels.get("IFN-γ", 0.0)
    nearby_tumor = [
        a for a in ctx.nearby_agents
        if a.agent_type == AgentType.TUMOR_CELL
    ]

    if ctx.age > 15 and kills > 2:
        return AgentDecision(action=AgentAction.QUIESCE,
                             reasoning="exhausted", confidence=0.9)
    if ifng > 0.08:
        return AgentDecision(action=AgentAction.SIGNAL, signal_type="IFN-γ",
                             reasoning="amplify response", confidence=0.9)
    if nearby_tumor and ctx.energy > 0.4:
        return AgentDecision(action=AgentAction.MIGRATE,
                             reasoning="engage tumor", confidence=0.9)
    return AgentDecision(action=AgentAction.MIGRATE,
                         reasoning="patrol", confidence=0.8)


# ── Reglas Macrophage ─────────────────────────────────────────────────────────

def _macrophage_rules(ctx: LocalContext) -> AgentDecision:
    """Macrophage — reglas first-match."""
    polarization = ctx.metadata.get("polarization", "M0")
    ifng = ctx.cytokine_levels.get("IFN-γ", 0.0)
    nearby_tumor = [
        a for a in ctx.nearby_agents
        if a.agent_type == AgentType.TUMOR_CELL
    ]

    if polarization == "M2":
        return AgentDecision(action=AgentAction.SIGNAL, signal_type="IL-6",
                             reasoning="pro-tumor signal", confidence=0.95)
    if polarization == "M1" and nearby_tumor:
        return AgentDecision(action=AgentAction.MIGRATE,
                             reasoning="cytotoxic patrol", confidence=0.9)
    if ifng > 0.05:
        return AgentDecision(action=AgentAction.SIGNAL, signal_type="IFN-γ",
                             reasoning="M1 activation", confidence=0.85)
    return AgentDecision(action=AgentAction.QUIESCE,
                         reasoning="no signal", confidence=0.8)


# ── Reglas NKCell — Sprint 4 ──────────────────────────────────────────────────

def _nk_rules(ctx: LocalContext) -> AgentDecision:
    """Natural Killer cell — reglas first-match.

    Espejo de llm/prompts.py AgentType.NK_CELL:
        age>20 AND kills>3 → QUIESCE (exhausted)
        TumorCell nearby AND energy>0.5 AND IL-6<0.04 → MIGRATE (kill)
        TumorCell nearby AND IL-6>0.04 → SIGNAL IFN-γ (suppress+signal)
        IFNg>0.06 → SIGNAL IFN-γ (amplify innate)
        default → MIGRATE (seek tumor)
    """
    kills = ctx.metadata.get("kills_count", 0)
    il6   = ctx.cytokine_levels.get("IL-6", 0.0)
    ifng  = ctx.cytokine_levels.get("IFN-γ", 0.0)
    nearby_tumor = [
        a for a in ctx.nearby_agents
        if a.agent_type == AgentType.TUMOR_CELL
    ]

    # Regla 1: agotamiento NK (más tardío que CD8+)
    if ctx.age > 20 and kills > 3:
        return AgentDecision(action=AgentAction.QUIESCE,
                             reasoning="nk exhausted", confidence=0.9)

    # Regla 2: tumor cerca + energía suficiente + no suprimida → atacar
    if nearby_tumor and ctx.energy > 0.5 and il6 < 0.04:
        return AgentDecision(action=AgentAction.MIGRATE,
                             reasoning="kill tumor", confidence=0.92)

    # Regla 3: tumor cerca PERO IL-6 suprime kill → señalizar en lugar de atacar
    if nearby_tumor and il6 > 0.04:
        return AgentDecision(action=AgentAction.SIGNAL, signal_type="IFN-γ",
                             reasoning="signal despite suppression", confidence=0.75)

    # Regla 4: IFN-γ alto → amplificar señal innata
    if ifng > 0.06:
        return AgentDecision(action=AgentAction.SIGNAL, signal_type="IFN-γ",
                             reasoning="amplify innate", confidence=0.85)

    # Default: buscar tumor
    return AgentDecision(action=AgentAction.MIGRATE,
                         reasoning="seek tumor", confidence=0.8)


# ── Reglas DendriticCell — Sprint 4 ──────────────────────────────────────────

def _dc_rules(ctx: LocalContext) -> AgentDecision:
    """Dendritic cell — reglas first-match.

    Espejo de llm/prompts.py AgentType.DENDRITIC_CELL:
        mature AND IFNg>0.05 → SIGNAL IFN-γ (activate adaptive)
        mature → MIGRATE (patrol activate)
        maturing AND IFNg>0.05 → SIGNAL IFN-γ (maturing signal)
        IFNg>0.05 → SIGNAL IFN-γ (begin maturation)
        default → QUIESCE (immature tolerogenic)
    """
    maturation = ctx.metadata.get("maturation_state", "immature")
    ifng = ctx.cytokine_levels.get("IFN-γ", 0.0)

    # Regla 1: DC madura + IFN-γ → señalizar activamente para activar CD8+
    if maturation == "mature" and ifng > 0.05:
        return AgentDecision(action=AgentAction.SIGNAL, signal_type="IFN-γ",
                             reasoning="activate adaptive", confidence=0.95)

    # Regla 2: DC madura sin IFN-γ → patrullar para encontrar CD8+
    if maturation == "mature":
        return AgentDecision(action=AgentAction.MIGRATE,
                             reasoning="patrol activate", confidence=0.85)

    # Regla 3: DC madurando + IFN-γ → señalizar durante proceso de maduración
    if maturation == "maturing" and ifng > 0.05:
        return AgentDecision(action=AgentAction.SIGNAL, signal_type="IFN-γ",
                             reasoning="maturing signal", confidence=0.8)

    # Regla 4: DC inmadura pero detecta IFN-γ → iniciar maduración (señal)
    if ifng > 0.05:
        return AgentDecision(action=AgentAction.SIGNAL, signal_type="IFN-γ",
                             reasoning="begin maturation", confidence=0.75)

    # Default: DC inmadura en TME supresivo → quiesce (tolerogénica)
    return AgentDecision(action=AgentAction.QUIESCE,
                         reasoning="immature tolerogenic", confidence=0.8)
