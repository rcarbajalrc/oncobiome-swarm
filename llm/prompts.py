"""Prompts v4-deterministic — output JSON forzado a formato exacto.

Estrategia: en lugar de pedir "reasoning≤3 words" (que Haiku interpreta
libremente generando ~48 tokens), se especifican los valores exactos
de reasoning permitidos por regla. Haiku replica el ejemplo exacto
sin variación → output constante ~22-25 tokens por llamada.

mem0: se recuperan máximo 2 memorias recientes, truncadas a 40 chars,
para mantener el contexto histórico sin disparar el input.

Sprint 4: añadidos prompts para NKCell y DendriticCell.
"""
from __future__ import annotations
from models.agent_state import AgentType, LocalContext


_SYSTEM_PROMPTS: dict[AgentType, str] = {

    AgentType.TUMOR_CELL: (
        "KRAS_G12D tumor cell. Output ONLY one JSON line, no explanation.\n"
        "Rules (first match wins):\n"
        "ImmuneCell nearby AND energy>0.5 → "
        '{"action":"SIGNAL","signal_type":"IL-6","reasoning":"suppress immune","confidence":0.95}\n'
        "ImmuneCell nearby AND energy≤0.5 → "
        '{"action":"MIGRATE","reasoning":"flee threat","confidence":0.9}\n'
        "IL-6>0.05 in cyto AND no ImmuneCell → "
        '{"action":"PROLIFERATE","reasoning":"safe niche","confidence":0.85}\n'
        "energy>0.7 AND no ImmuneCell → "
        '{"action":"PROLIFERATE","reasoning":"expand uncontested","confidence":0.85}\n'
        "default → "
        '{"action":"QUIESCE","reasoning":"conserve energy","confidence":0.8}'
    ),

    AgentType.IMMUNE_CELL: (
        "CD8+ T cell. Output ONLY one JSON line, no explanation.\n"
        "Rules (first match wins):\n"
        "age>15 AND kills_count>2 in meta → "
        '{"action":"QUIESCE","reasoning":"exhausted","confidence":0.9}\n'
        "IFNg>0.08 in cyto → "
        '{"action":"SIGNAL","signal_type":"IFN-γ","reasoning":"amplify response","confidence":0.9}\n'
        "TumorCell nearby AND energy>0.4 → "
        '{"action":"MIGRATE","reasoning":"engage tumor","confidence":0.9}\n'
        "default → "
        '{"action":"MIGRATE","reasoning":"patrol","confidence":0.8}'
    ),

    AgentType.MACROPHAGE: (
        "Macrophage. Output ONLY one JSON line, no explanation.\n"
        "Rules (first match wins):\n"
        "polarization=M2 in meta → "
        '{"action":"SIGNAL","signal_type":"IL-6","reasoning":"pro-tumor signal","confidence":0.95}\n'
        "polarization=M1 AND TumorCell nearby → "
        '{"action":"MIGRATE","reasoning":"cytotoxic patrol","confidence":0.9}\n'
        "IFNg>0.05 in cyto → "
        '{"action":"SIGNAL","signal_type":"IFN-γ","reasoning":"M1 activation","confidence":0.85}\n'
        "default → "
        '{"action":"QUIESCE","reasoning":"no signal","confidence":0.8}'
    ),

    # ── Sprint 4: Natural Killer cell ─────────────────────────────────────────
    # NK actúan por "missing self" — matan directamente sin presentación antigénica.
    # Son más resistentes al agotamiento que CD8+ pero muy sensibles a IL-6.
    # Colaboran con DC emitiendo IFN-γ.
    AgentType.NK_CELL: (
        "NK (Natural Killer) cell. Output ONLY one JSON line, no explanation.\n"
        "Rules (first match wins):\n"
        "age>20 AND kills_count>3 in meta → "
        '{"action":"QUIESCE","reasoning":"nk exhausted","confidence":0.9}\n'
        "TumorCell nearby AND energy>0.5 AND IL-6<0.04 in cyto → "
        '{"action":"MIGRATE","reasoning":"kill tumor","confidence":0.92}\n'
        "TumorCell nearby AND IL-6>0.04 in cyto → "
        '{"action":"SIGNAL","signal_type":"IFN-γ","reasoning":"signal despite suppression","confidence":0.75}\n'
        "IFNg>0.06 in cyto → "
        '{"action":"SIGNAL","signal_type":"IFN-γ","reasoning":"amplify innate","confidence":0.85}\n'
        "default → "
        '{"action":"MIGRATE","reasoning":"seek tumor","confidence":0.8}'
    ),

    # ── Sprint 4: Dendritic cell ───────────────────────────────────────────────
    # DC maduras activan CD8+. Inmaduras son tolerogénicas.
    # Maduran por detección de IFN-γ en el TME.
    # Rol: puente entre inmunidad innata (NK) y adaptativa (CD8+).
    AgentType.DENDRITIC_CELL: (
        "Dendritic cell. Output ONLY one JSON line, no explanation.\n"
        "Rules (first match wins):\n"
        "maturation_state=mature in meta AND IFNg>0.05 in cyto → "
        '{"action":"SIGNAL","signal_type":"IFN-γ","reasoning":"activate adaptive","confidence":0.95}\n'
        "maturation_state=mature in meta → "
        '{"action":"MIGRATE","reasoning":"patrol activate","confidence":0.85}\n'
        "maturation_state=maturing in meta AND IFNg>0.05 in cyto → "
        '{"action":"SIGNAL","signal_type":"IFN-γ","reasoning":"maturing signal","confidence":0.8}\n'
        "IFNg>0.05 in cyto → "
        '{"action":"SIGNAL","signal_type":"IFN-γ","reasoning":"begin maturation","confidence":0.75}\n'
        "default → "
        '{"action":"QUIESCE","reasoning":"immature tolerogenic","confidence":0.8}'
    ),
}


def build_system_prompt(agent_type: AgentType) -> str:
    """Retorna el system prompt para el tipo de agente.

    Para tipos sin prompt específico (PhytochemicalAgent, CytokineAgent)
    usa TumorCell como fallback conservador — nunca debería ocurrir en
    producción ya que estos agentes usan rule engine.
    """
    return _SYSTEM_PROMPTS.get(agent_type, _SYSTEM_PROMPTS[AgentType.TUMOR_CELL])


def build_user_prompt(ctx: LocalContext) -> str:
    nearby = ";".join(
        f"{a.agent_type.value[:5]}@{a.distance:.0f}(e={a.energy:.2f})"
        for a in ctx.nearby_agents[:4]
    ) or "none"
    cyto = " ".join(
        f"{k.replace('IFN-γ', 'IFNg')}={v:.3f}"
        for k, v in ctx.cytokine_levels.items() if v > 0.001
    ) or "all=0"
    # Máximo 2 memorias recientes, truncadas a 40 chars cada una
    recent = ctx.recent_memories[-2:] if ctx.recent_memories else []
    mem = "|".join(m[:40] for m in recent) if recent else "none"
    meta = " ".join(f"{k}={v}" for k, v in list(ctx.metadata.items())[:2])
    return (
        f"c={ctx.cycle} e={ctx.energy:.2f} age={ctx.age} {meta}\n"
        f"near:[{nearby}] cyto:{cyto}\nmem:{mem}"
    )
