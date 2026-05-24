"""Routine: wolf patrols between forest rooms every 8 ticks."""
import random

PATROL_ROOMS = ["forest_path", "forest_deep"]


async def run(world, tick_count):
    wolf = world.monsters.get("forest_wolf")
    if wolf is None or not wolf.alive:
        return

    if tick_count % 8 != 0:
        return

    current = wolf.room_id
    choices = [r for r in PATROL_ROOMS if r != current]
    if not choices:
        return

    target_id = random.choice(choices)

    # move wolf
    old_room = world.map.get_room(current)
    if old_room:
        old_room.remove_entity(wolf.id)
    wolf.room_id = target_id
    new_room = world.map.get_room(target_id)
    if new_room:
        new_room.add_entity(wolf.id)

    # alert players in target room
    for eid in list(new_room.entity_ids if new_room else []):
        if eid in world.players:
            p = world.players[eid]
            session = world.sessions.session_for_player(p.id)
            if session:
                await world.sessions.send(session, {
                    "type": "message",
                    "text": f"A Gaunt Wolf pads silently into {new_room.name}.",
                })
