# host/lab/sidekick_plate_manager.py

class PlateManager:
    """Tracks well contents and provides state summaries for the AI."""
    def __init__(self, max_volume_ul):
        self.max_volume_ul = max_volume_ul
        self.plate_state = {}
        self._initialize_plate()

    def _initialize_plate(self):
        rows = "ABCDEFGH"
        for row in rows:
            for col in range(1, 13):
                self.plate_state[f"{row}{col}"] = {"p1": 0, "p2": 0, "p3": 0, "p4": 0}
        self.plate_state['waste'] = {}

    def get_well_volume(self, well_id):
        well = self.plate_state.get(well_id.upper())
        return sum(well.values()) if well else 0

    def is_well_empty(self, well_id):
        return self.get_well_volume(well_id) == 0

    def add_liquid(self, well_id, pump_id, volume):
        well = self.plate_state.get(well_id.upper())
        if well and pump_id in well:
            well[pump_id] += volume

    def get_plate_summary(self):
        """Returns a string summary of non-empty wells for the AI context."""
        summary = []
        for well, contents in self.plate_state.items():
            vol = sum(contents.values())
            if vol > 0:
                detail = ", ".join([f"{p}:{v}uL" for p, v in contents.items() if v > 0])
                summary.append(f"Well {well}: {detail} (Total: {vol}uL)")
        return "\n".join(summary) if summary else "All wells are currently empty."