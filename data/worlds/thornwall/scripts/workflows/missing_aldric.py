"""Workflow: 'Find Missing Aldric' — a simple three-step quest.

Steps:
  1. talk_to_guard    — guard mentions Aldric is missing
  2. find_clue        — player finds Aldric's pack in the deep forest
  3. report_back      — player returns to the guard
"""

STEPS = ["talk_to_guard", "find_clue", "report_back"]


async def on_progress(player, step, world):
    session = world.sessions.session_for_player(player.id)
    if session is None:
        return

    if step == "talk_to_guard":
        await world.sessions.send(session, {
            "type": "message",
            "text": 'The guard straightens. "Aldric went into the forest three days ago. '
                    'Haven\'t seen him since. If you find any sign of him… please."',
        })
        player.__dict__.setdefault("quest_flags", set()).add("aldric_started")

    elif step == "find_clue":
        await world.sessions.send(session, {
            "type": "message",
            "text": "You spot a worn pack half-buried in leaves. The initials 'A.W.' are stitched on the flap.",
        })
        player.__dict__.setdefault("quest_flags", set()).add("aldric_clue_found")

    elif step == "report_back":
        await world.sessions.send(session, {
            "type": "message",
            "text": 'The guard\'s face falls as you hand over the pack. '
                    '"So he\'s gone then. Thank you for telling me." He presses a few coins into your hand.',
        })
        player.__dict__.setdefault("quest_flags", set()).add("aldric_complete")
