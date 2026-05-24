"""Seeds the Thornwall world with its starter map and NPCs."""
from world.zone import Zone, ZoneType
from world.room import Room
from entities.npc import NPC
from entities.monster import Monster


def seed(world):
    # zones
    town = Zone(id="town", name="Thornwall", zone_type=ZoneType.OUTDOOR)
    tavern_zone = Zone(id="tavern", name="The Rusted Flagon", zone_type=ZoneType.BUILDING)
    forest = Zone(id="forest", name="Dark Forest", zone_type=ZoneType.OUTDOOR)
    world.map.add_zone(town)
    world.map.add_zone(tavern_zone)
    world.map.add_zone(forest)

    # rooms
    rooms = [
        Room(id="town_square",   name="Town Square",
             description="The dusty centre of Thornwall. A notice board creaks in the wind. "
                         "Muddy footprints lead in every direction.",
             zone_id="town", x=0, y=0,
             exits={"east": "tavern_entrance", "north": "north_gate"}),

        Room(id="tavern_entrance", name="The Rusted Flagon — Entrance",
             description="A low doorway leads into smoky warmth. The smell of ale and tallow candles drifts out.",
             zone_id="tavern", x=1, y=0,
             exits={"west": "town_square", "in": "tavern_common"}),

        Room(id="tavern_common", name="The Rusted Flagon — Common Room",
             description="Rough-hewn tables crowd a soot-blackened room. A fire pops in the hearth.",
             zone_id="tavern", x=1, y=1,
             exits={"out": "tavern_entrance"}),

        Room(id="north_gate",    name="North Gate",
             description="Iron-banded oak gates stand half-open. The forest road stretches north.",
             zone_id="town", x=0, y=1,
             exits={"south": "town_square", "north": "forest_path"}),

        Room(id="forest_path",   name="Forest Path",
             description="Tall pines crowd the dirt road. Strange sounds echo between the trunks.",
             zone_id="forest", x=0, y=2,
             exits={"south": "north_gate", "north": "forest_deep"}),

        Room(id="forest_deep",   name="Deep Forest",
             description="The canopy closes overhead. It is very dark. Something moves in the shadows.",
             zone_id="forest", x=0, y=3,
             exits={"south": "forest_path"}),
    ]
    for r in rooms:
        world.map.add_room(r)
    world.map.set_entry_room("town_square")

    # NPCs
    world.npcs["innkeeper"] = NPC(
        id="innkeeper", name="Marta the Innkeeper",
        description="A stout woman with flour-dusted hands and sharp eyes.",
        room_id="tavern_common",
        dialogue=["Welcome to the Flagon. Rooms are a silver a night.", "Watch yourself in the forest."],
    )
    world.npcs["guard"] = NPC(
        id="guard", name="Town Guard",
        description="A bored-looking guard leaning on a spear.",
        room_id="north_gate",
        dialogue=["Keep to the path if you're heading north.", "Haven't seen Aldric in three days."],
    )

    # Monster
    world.spawn_monster(Monster(
        id="forest_wolf", name="Gaunt Wolf",
        description="A large wolf with matted grey fur and hollow eyes.",
        room_id="forest_deep",
        hp=25, max_hp=25, attack=7, defence=2,
    ))
