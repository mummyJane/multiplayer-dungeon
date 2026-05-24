from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class NPC:
    id: str
    name: str
    description: str
    room_id: str
    dialogue: list[str] = field(default_factory=list)
    # script id to run each tick
    behaviour_script: str = "idle"
    properties: dict = field(default_factory=dict)
    gm_generated: bool = False
