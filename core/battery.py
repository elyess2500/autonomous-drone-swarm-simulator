"""
core/battery.py - Battery simulation for a single drone.

Handles:
  - Per-frame drain based on drone activity
  - Weather/storm multipliers
  - Recharge at base
  - Low / critical threshold events
"""

import config


class Battery:
    """
    Models drone battery state.

    Usage
    -----
    b = Battery()
    b.update("moving", in_storm=True)
    if b.should_return():
        # send drone home
    """

    def __init__(self, initial: float = config.BATTERY_MAX):
        self.level    = float(initial)
        self.max      = float(config.BATTERY_MAX)
        self.charging = False

        # Internal flag to avoid repeated alerts
        self._low_alerted      = False
        self._critical_alerted = False

    # ──────────────────────────────────────────
    # Per-frame update
    # ──────────────────────────────────────────

    def update(self, activity: str, in_storm: bool = False, in_wind: bool = False):
        """
        Drain or charge the battery by one frame.

        Parameters
        ----------
        activity : str
            One of "idle", "moving", "scanning", "charging", "failed"
        in_storm : bool
            Extra drain when weather is stormy.
        in_wind : bool
            Slight extra drain in wind zones.
        """
        if self.charging:
            self._charge()
            return

        if activity == "failed":
            return  # no drain on failed drones

        # Base drain
        base_drain = {
            "idle":     config.BATTERY_IDLE_DRAIN,
            "moving":   config.BATTERY_MOVE_DRAIN,
            "scanning": config.BATTERY_SCAN_DRAIN,
            "avoiding": config.BATTERY_MOVE_DRAIN * 1.1,
            "returning": config.BATTERY_MOVE_DRAIN,
        }.get(activity, config.BATTERY_IDLE_DRAIN)

        # Modifiers
        if in_storm:
            base_drain += config.STORM_EXTRA_DRAIN
        if in_wind:
            base_drain += config.BATTERY_MOVE_DRAIN * 0.15

        self.level = max(0.0, self.level - base_drain)

    def _charge(self):
        """Increment charge level; stop when full."""
        self.level = min(self.max, self.level + config.BATTERY_CHARGE_RATE)
        if self.level >= self.max:
            self.charging = False
            self._low_alerted      = False
            self._critical_alerted = False

    def start_charging(self):
        self.charging = True

    def stop_charging(self):
        self.charging = False
        if self.level >= config.BATTERY_RELAUNCH_THRESH:
            self._low_alerted = False
            self._critical_alerted = False

    # ──────────────────────────────────────────
    # State queries
    # ──────────────────────────────────────────

    @property
    def pct(self) -> float:
        """Battery level as 0.0–1.0."""
        return self.level / self.max

    def should_return(self) -> bool:
        """True when battery is low enough that drone should head home."""
        return self.level <= config.BATTERY_LOW_THRESH and not self.charging

    def is_critical(self) -> bool:
        return self.level <= config.BATTERY_CRITICAL and not self.charging

    def is_full(self) -> bool:
        return self.level >= self.max * 0.99

    def is_empty(self) -> bool:
        return self.level <= 0.0

    # ──────────────────────────────────────────
    # Alert helpers (fire once per low event)
    # ──────────────────────────────────────────

    def pop_low_alert(self) -> bool:
        """Returns True (once) when battery first drops below LOW threshold."""
        if self.level <= config.BATTERY_LOW_THRESH and not self._low_alerted and not self.charging:
            self._low_alerted = True
            return True
        return False

    def pop_critical_alert(self) -> bool:
        if self.level <= config.BATTERY_CRITICAL and not self._critical_alerted and not self.charging:
            self._critical_alerted = True
            return True
        return False

    # ──────────────────────────────────────────
    # Visual helpers
    # ──────────────────────────────────────────

    def color(self) -> tuple[int, int, int]:
        """Return a colour (green → yellow → red) based on level."""
        p = self.pct
        if p > 0.6:
            return config.C_UI_OK
        elif p > 0.25:
            return config.C_UI_WARN
        else:
            return config.C_UI_DANGER

    def __repr__(self):
        return f"Battery({self.level:.1f}/{self.max:.0f}, {'CHG' if self.charging else 'DRN'})"
