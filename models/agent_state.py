from __future__ import annotations

import uuid
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AgentType(str, Enum):
    TUMOR_CELL      = "TumorCell"
    IMMUNE_CELL     = "ImmuneCell"
    MACROPHAGE      = "MacrophageAgent"
    PHYTOCHEMICAL   = "PhytochemicalAgent"
    CYTOKINE        = "CytokineAgent"
    NK_CELL         = "NKCell"          # Sprint 4: Natural Killer cell
    DENDRITIC_CELL  = "DendriticCell"   # Sprint 4: Dendritic cell


class AgentAction(str, Enum):
    PROLIFERATE = "PROLIFERATE"
    QUIESCE     = "QUIESCE"
    MIGRATE     = "MIGRATE"
    SIGNAL      = "SIGNAL"
    DIE         = "DIE"
    DIFFUSE     = "DIFFUSE"


class AgentState(BaseModel):
    agent_id:   str  = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    agent_type: AgentType
    position:   tuple[float, float]
    energy:     float = Field(ge=0.0, le=1.0)
    alive:      bool  = True
    age:        int   = 0
    metadata:   dict[str, Any] = Field(default_factory=dict)

    def memory_user_id(self) -> str:
        return f"agent_{self.agent_id}"


class NearbyAgentInfo(BaseModel):
    agent_id:   str
    agent_type: AgentType
    distance:   float
    energy:     float


class LocalContext(BaseModel):
    """Información local que un agente percibe en su entorno inmediato."""
    agent_id:        str
    agent_type:      AgentType
    position:        tuple[float, float]
    energy:          float
    age:             int
    metadata:        dict[str, Any]
    nearby_agents:   list[NearbyAgentInfo] = Field(default_factory=list)
    cytokine_levels: dict[str, float]      = Field(default_factory=dict)
    recent_memories: list[str]             = Field(default_factory=list)
    cycle:           int                   = 0


class AgentDecision(BaseModel):
    action:          AgentAction
    target_position: tuple[float, float] | None = None
    signal_type:     str | None                 = None
    reasoning:       str                        = ""
    confidence:      float                      = Field(default=0.5, ge=0.0, le=1.0)
