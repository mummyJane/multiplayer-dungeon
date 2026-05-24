from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Item:
    id: str
    name: str
    description: str
    item_type: str = "misc"       # weapon, armour, clothing, consumable, fixture, misc
    weight: float = 0.0
    value: int = 0
    properties: dict = field(default_factory=dict)
    gm_generated: bool = False
    owner_id: Optional[str] = None
    room_id: Optional[str] = None

    # ── property helpers ──────────────────────────────────────────────────────

    @property
    def is_wearable(self) -> bool:
        return bool(self.properties.get("wearable")) or self.item_type == "clothing"

    @property
    def slot(self) -> Optional[str]:
        """Clothing slot this item occupies when worn (e.g. 'mouth', 'nappy', 'top')."""
        return self.properties.get("slot")

    @property
    def item_effects(self) -> list[str]:
        """Effects applied to the wearer (e.g. ['mute', 'no_move'])."""
        return list(self.properties.get("effects", []))

    @property
    def is_fixture(self) -> bool:
        """Fixtures are immovable room objects (beds, posts, changing tables)."""
        return bool(self.properties.get("fixture")) or self.item_type == "fixture"

    @property
    def is_locked(self) -> bool:
        return bool(self.properties.get("locked"))

    @property
    def is_lockable(self) -> bool:
        return bool(self.properties.get("lockable"))
