from __future__ import annotations
import random
from typing import Union
from entities.player import Player
from entities.monster import Monster


class CombatResolver:
    def attack(self, attacker: Union[Player, Monster], defender: Union[Player, Monster]) -> dict:
        base = getattr(attacker, "attack", 10)
        roll = random.randint(1, 20)
        damage = max(0, base + (roll - 10))
        defender.take_damage(damage)
        return {
            "attacker": attacker.name,
            "defender": defender.name,
            "roll": roll,
            "damage": damage,
            "defender_hp": defender.hp,
            "defender_alive": defender.alive,
        }
