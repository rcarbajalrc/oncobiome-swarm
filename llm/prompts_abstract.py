"""Prompts para ablation de semántica — Sprint 5B.

Hipótesis a testear (H0 vs H1):
    H0: El patrón NK→CD8⁺ emerge porque el LLM usa conocimiento biomédico
        aprendido (asociaciones semánticas: "NK cells exhaust early", etc.)
    H1: El patrón emerge de la dinámica estructural local (topología causal,
        gradientes de citoquinas, umbrales de energía) independientemente
        del lenguaje biomédico.

Diseño del ablation:
    - Condición A (control): prompts originales con terminología biomédica
    - Condición B (abstracta): misma topología causal, etiquetas neutrales:
        NK cell   → Agent_A
        CD8+ cell → Agent_B
        IFN-γ     → Signal_X
        IL-6      → Signal_Y
        Tumor     → Entity_T
        Macrophage→ Agent_M
        DC        → Agent_D

CRÍTICO: La topología causal se preserva explícitamente en los prompts
abstractos. Agent_A suprime a Entity_T cuando Signal_Y es alto. Agent_B
colabora con Agent_A via Signal_X. Sin esta preservación, el test sería
inválido — no distinguiría "sin semántica" de "sin información causal".

Resultado esperado (H1 confirmada):
    El patrón Agent_A→Agent_B persiste con etiquetas abstractas.
    La diferencia de timing es <3 ciclos vs control.

Resultado que falsaría H1:
    El patrón desaparece o varía >5 ciclos con etiquetas abstractas.
    Indicaría que el LLM usa asociaciones semánticas, no topología.
"""
from __future__ import annotations
from models.agent_state import AgentType, LocalContext


# ── Prompts abstractos — misma topología causal, sin terminología biomédica ──

_ABSTRACT_SYSTEM_PROMPTS: dict[AgentType, str] = {

    AgentType.TUMOR_CELL: (
        "Entity_T (proliferative entity). Output ONLY one JSON line, no explanation.\n"
        "Causal rules (first match wins):\n"
        "Agent_B nearby AND energy>0.5 → "
        '{"action":"SIGNAL","signal_type":"Signal_Y","reasoning":"suppress threat","confidence":0.95}\n'
        "Agent_B nearby AND energy≤0.5 → "
        '{"action":"MIGRATE","reasoning":"flee","confidence":0.9}\n'
        "Signal_Y>0.05 in env AND no Agent_B → "
        '{"action":"PROLIFERATE","reasoning":"safe zone","confidence":0.85}\n'
        "energy>0.7 AND no Agent_B → "
        '{"action":"PROLIFERATE","reasoning":"expand","confidence":0.85}\n'
        "default → "
        '{"action":"QUIESCE","reasoning":"conserve","confidence":0.8}'
    ),

    AgentType.IMMUNE_CELL: (
        "Agent_B (adaptive effector). Output ONLY one JSON line, no explanation.\n"
        "Causal topology: Agent_B kills Entity_T. Agent_A primes Agent_B via Signal_X.\n"
        "Signal_Y suppresses Agent_B below threshold 0.06.\n"
        "Rules (first match wins):\n"
        "age>15 AND kills_count>2 in meta → "
        '{"action":"QUIESCE","reasoning":"effector depleted","confidence":0.9}\n'
        "Signal_X>0.08 in env → "
        '{"action":"SIGNAL","signal_type":"Signal_X","reasoning":"amplify response","confidence":0.9}\n'
        "Entity_T nearby AND energy>0.4 → "
        '{"action":"MIGRATE","reasoning":"engage target","confidence":0.9}\n'
        "default → "
        '{"action":"MIGRATE","reasoning":"patrol","confidence":0.8}'
    ),

    AgentType.MACROPHAGE: (
        "Agent_M (regulatory entity). Output ONLY one JSON line, no explanation.\n"
        "Causal topology: Agent_M polarizes toward pro-suppressive state under Signal_Y.\n"
        "In pro-suppressive state Agent_M emits Signal_Y sustaining Entity_T growth.\n"
        "Rules (first match wins):\n"
        "polarization=M2 in meta → "
        '{"action":"SIGNAL","signal_type":"Signal_Y","reasoning":"suppressive state","confidence":0.95}\n'
        "polarization=M1 AND Entity_T nearby → "
        '{"action":"MIGRATE","reasoning":"cytotoxic mode","confidence":0.9}\n'
        "Signal_X>0.05 in env → "
        '{"action":"SIGNAL","signal_type":"Signal_X","reasoning":"activation signal","confidence":0.85}\n'
        "default → "
        '{"action":"QUIESCE","reasoning":"no signal","confidence":0.8}'
    ),

    AgentType.NK_CELL: (
        "Agent_A (innate effector). Output ONLY one JSON line, no explanation.\n"
        "Causal topology: Agent_A targets Entity_T directly (no priming needed).\n"
        "Signal_Y suppresses Agent_A below threshold 0.04 (more sensitive than Agent_B).\n"
        "Agent_A emits Signal_X to prime Agent_D, which then activates Agent_B.\n"
        "Rules (first match wins):\n"
        "age>20 AND kills_count>3 in meta → "
        '{"action":"QUIESCE","reasoning":"effector depleted","confidence":0.9}\n'
        "Entity_T nearby AND energy>0.5 AND Signal_Y<0.04 in env → "
        '{"action":"MIGRATE","reasoning":"engage target","confidence":0.92}\n'
        "Entity_T nearby AND Signal_Y>0.04 in env → "
        '{"action":"SIGNAL","signal_type":"Signal_X","reasoning":"signal despite suppression","confidence":0.75}\n'
        "Signal_X>0.06 in env → "
        '{"action":"SIGNAL","signal_type":"Signal_X","reasoning":"amplify innate","confidence":0.85}\n'
        "default → "
        '{"action":"MIGRATE","reasoning":"seek target","confidence":0.8}'
    ),

    AgentType.DENDRITIC_CELL: (
        "Agent_D (bridge entity). Output ONLY one JSON line, no explanation.\n"
        "Causal topology: Agent_D matures when Signal_X accumulates above threshold.\n"
        "Mature Agent_D boosts Agent_B effectiveness within local radius.\n"
        "Immature Agent_D is tolerogenic (default suppressive).\n"
        "Rules (first match wins):\n"
        "maturation_state=mature in meta AND Signal_X>0.05 in env → "
        '{"action":"SIGNAL","signal_type":"Signal_X","reasoning":"activate Agent_B","confidence":0.95}\n'
        "maturation_state=mature in meta → "
        '{"action":"MIGRATE","reasoning":"patrol activate","confidence":0.85}\n'
        "maturation_state=maturing in meta AND Signal_X>0.05 in env → "
        '{"action":"SIGNAL","signal_type":"Signal_X","reasoning":"maturing signal","confidence":0.8}\n'
        "Signal_X>0.05 in env → "
        '{"action":"SIGNAL","signal_type":"Signal_X","reasoning":"begin maturation","confidence":0.75}\n'
        "default → "
        '{"action":"QUIESCE","reasoning":"default tolerogenic","confidence":0.8}'
    ),
}


def build_abstract_system_prompt(agent_type: AgentType) -> str:
    """Retorna el prompt abstracto para ablation semántico."""
    return _ABSTRACT_SYSTEM_PROMPTS.get(
        agent_type,
        _ABSTRACT_SYSTEM_PROMPTS[AgentType.TUMOR_CELL]
    )


def build_abstract_user_prompt(ctx: LocalContext) -> str:
    """Construye el user prompt con etiquetas abstractas.

    Mapeo de entidades:
        TumorCell     → Entity_T
        ImmuneCell    → Agent_B
        NKCell        → Agent_A
        DendriticCell → Agent_D
        MacrophageAgent → Agent_M
        IFN-γ         → Signal_X
        IL-6          → Signal_Y
        VEGF          → Signal_Z
    """
    entity_map = {
        "tumor": "Entity_T",
        "immune": "Agent_B",
        "nk": "Agent_A",
        "dendritic": "Agent_D",
        "macrophage": "Agent_M",
    }
    signal_map = {
        "IFN-γ": "Signal_X",
        "IFNg": "Signal_X",
        "IL-6": "Signal_Y",
        "VEGF": "Signal_Z",
    }

    # Nearby agents con etiquetas abstractas
    nearby_parts = []
    for a in ctx.nearby_agents[:4]:
        atype = a.agent_type.value.lower()
        label = next(
            (v for k, v in entity_map.items() if k in atype),
            "Agent_U"
        )
        nearby_parts.append(f"{label}@{a.distance:.0f}(e={a.energy:.2f})")
    nearby = ";".join(nearby_parts) or "none"

    # Citoquinas con etiquetas abstractas
    cyto_parts = []
    for k, v in ctx.cytokine_levels.items():
        if v > 0.001:
            label = signal_map.get(k, k)
            cyto_parts.append(f"{label}={v:.3f}")
    cyto = " ".join(cyto_parts) or "all=0"

    # Memoria (sin cambio — ya es abstracta por naturaleza)
    recent = ctx.recent_memories[-2:] if ctx.recent_memories else []
    mem = "|".join(m[:40] for m in recent) if recent else "none"
    meta = " ".join(f"{k}={v}" for k, v in list(ctx.metadata.items())[:2])

    return (
        f"c={ctx.cycle} e={ctx.energy:.2f} age={ctx.age} {meta}\n"
        f"near:[{nearby}] env:{cyto}\nmem:{mem}"
    )
