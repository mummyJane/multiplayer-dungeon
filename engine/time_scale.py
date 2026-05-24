class TimeScaler:
    """Adjusts world tick interval based on active player count."""

    BASE_TICK = 3.0   # seconds at 0 players
    MIN_TICK = 0.5    # fastest possible tick
    PLAYER_RAMP = 0.3 # seconds faster per additional player

    def __init__(self):
        self._player_count = 0

    def set_player_count(self, count: int):
        self._player_count = max(0, count)

    def tick_interval(self) -> float:
        interval = self.BASE_TICK - (self._player_count * self.PLAYER_RAMP)
        return max(self.MIN_TICK, interval)
