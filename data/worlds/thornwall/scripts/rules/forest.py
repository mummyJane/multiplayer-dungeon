"""Rules: dark forest behaviour."""


async def on_player_enter(player, room, world):
    """Warn players entering the deep forest."""
    if room.id == "forest_deep" and not player.__dict__.get("_warned_deep"):
        player._warned_deep = True
        session = world.sessions.session_for_player(player.id)
        if session:
            await world.sessions.send(session, {
                "type": "message",
                "text": "A chill runs down your spine. Something watches from the darkness.",
            })
