# host/cogs/pixel_art_cog.py

import json
import re
from pathlib import Path

from host.cogs.base_cog import BaseCog

DEVICE = "sidekick"
ROWS = 8
COLS = 12
DEFAULT_UNIT_INCREMENT_UL = 10.0
DEFAULT_NOMINAL_WELL_VOLUME_UL = 100.0
DEFAULT_MAX_WELL_VOLUME_UL = 200.0
DEFAULT_DILUENT = "water"


class PixelArtCog(BaseCog):
    """Pixel art on the plate canvas: resolves palette liquids to pumps and loads art schemas."""

    def __init__(self, app):
        """
        Args:
            app: The main ChatApp instance.
        """
        super().__init__(app)
        self.art_dir = Path(".talos/art")

    def get_commands(self):
        return {}

    def _resolve_pump(self, liquid_name: str) -> str:
        """
        Map a liquid name (e.g. 'red') to a pump key (e.g. 'p1') using the
        world model reagents, which map pump IDs to liquid descriptions.

        Matching is a simple case-insensitive substring test against the
        description; it is intentionally not robust.

        Args:
            liquid_name: Liquid name as written in an art palette, e.g. 'red'.

        Returns:
            The pump key, e.g. 'p1'.

        Raises:
            ValueError: If no reagent description matches the liquid name.
        """
        reagents = self.app.world_model.get("reagents", {})
        needle = re.escape(liquid_name.strip().lower())
        pattern = re.compile(needle)

        for pump_id, description in reagents.items():
            if pattern.search(str(description).lower()):
                return pump_id

        raise ValueError(f"No pump assigned for liquid '{liquid_name}' in world model reagents")

    def _load_art_schema(self, name: str) -> dict:
        """
        Load an art schema JSON from the art directory.

        Args:
            name: Art name (or filename), e.g. 'smiley' or 'smiley.json'.

        Returns:
            The parsed art schema dictionary.

        Raises:
            FileNotFoundError: If the art file does not exist.
        """
        art_name = name.strip()
        if art_name.lower().endswith(".json"):
            art_name = art_name[:-5]

        art_path = self.art_dir / f"{art_name}.json"
        if not art_path.exists():
            available = ", ".join(sorted(p.stem for p in self.art_dir.glob("*.json"))) or "none"
            raise FileNotFoundError(
                f"Art schema '{art_name}' not found at {art_path}. Available art: {available}"
            )

        return json.loads(art_path.read_text(encoding="utf-8"))

    def _validate_grid(self, schema: dict) -> None:
        """Validate an art schema's grid, palette, and volume configuration."""
        grid = schema.get("grid", [])
        palette = schema.get("palette", {})

        if not isinstance(grid, list) or len(grid) != ROWS:
            count = len(grid) if isinstance(grid, list) else type(grid).__name__
            raise ValueError(f"Grid must contain exactly {ROWS} rows, got {count}")

        for row_idx, row in enumerate(grid):
            if not isinstance(row, str):
                raise ValueError(f"Grid row {row_idx} must be a string, got {type(row).__name__}")
            if len(row) != COLS:
                raise ValueError(f"Grid row {row_idx} must be {COLS} characters long, got {len(row)}: '{row}'")

        unknown = sorted({ch for row in grid for ch in row if ch not in palette})
        if unknown:
            raise ValueError(
                f"Grid characters not defined in palette: {', '.join(unknown)}. "
                f"Palette defines: {', '.join(sorted(palette))}"
            )

        volume_config = schema.get("volume_config", {})
        unit_increment = float(volume_config.get("unit_increment_ul", DEFAULT_UNIT_INCREMENT_UL))
        nominal_volume = float(volume_config.get("nominal_well_volume_ul", DEFAULT_NOMINAL_WELL_VOLUME_UL))
        max_well_volume = float(self.app.world_model.get("max_well_volume_ul", DEFAULT_MAX_WELL_VOLUME_UL))
        diluent = volume_config.get("diluent", DEFAULT_DILUENT)

        if unit_increment <= 0:
            raise ValueError(f"unit_increment_ul must be positive, got {unit_increment}")

        for char, entry in palette.items():
            liquids_ul = entry.get("liquids_ul", {})
            if not isinstance(liquids_ul, dict):
                raise ValueError(f"Palette cell '{char}' must have a liquids_ul dictionary")

            cell_total = 0.0
            for liquid_name, vol_ul in liquids_ul.items():
                vol = float(vol_ul)
                if vol < 0:
                    raise ValueError(f"Palette cell '{char}' liquid '{liquid_name}' has a negative volume: {vol}")
                if vol > 0 and not self._is_multiple(vol, unit_increment):
                    raise ValueError(
                        f"Palette cell '{char}' liquid '{liquid_name}' volume {vol} uL is not a "
                        f"multiple of unit_increment_ul ({unit_increment} uL)"
                    )
                cell_total += vol

            cell_total += max(0.0, nominal_volume - cell_total)
            if cell_total > max_well_volume:
                raise ValueError(
                    f"Palette cell '{char}' totals {cell_total} uL, exceeding max_well_volume_ul "
                    f"({max_well_volume} uL)"
                )

        for char, entry in palette.items():
            for liquid_name in entry.get("liquids_ul", {}):
                try:
                    self._resolve_pump(liquid_name)
                except ValueError as exc:
                    raise ValueError(f"Palette cell '{char}': {exc}") from exc

        try:
            self._resolve_pump(diluent)
        except ValueError as exc:
            raise ValueError(f"Diluent '{diluent}': {exc}") from exc

    @staticmethod
    def _is_multiple(vol: float, increment: float) -> bool:
        """True when vol is an integer multiple of increment, tolerant of float noise."""
        quotient = vol / increment
        return abs(quotient - round(quotient)) < 1e-9

    def _grid_to_plan(self, schema: dict) -> list[dict]:
        """Expand an art schema into a flat list of sidekick command objects."""
        self._validate_grid(schema)

        grid = schema["grid"]
        palette = schema["palette"]
        volume_config = schema.get("volume_config", {})
        nominal_volume = float(volume_config.get("nominal_well_volume_ul", DEFAULT_NOMINAL_WELL_VOLUME_UL))
        diluent = volume_config.get("diluent", DEFAULT_DILUENT)

        plan: list[dict] = [{"device": DEVICE, "command": "home", "args": {}}]

        for row_idx, row in enumerate(grid):
            row_letter = chr(ord("A") + row_idx)
            for col_idx, char in enumerate(row):
                well = f"{row_letter}{col_idx + 1}"
                liquids_ul = palette[char].get("liquids_ul", {})
                pigment_total = sum(float(vol) for vol in liquids_ul.values())

                for liquid_name, vol_ul in liquids_ul.items():
                    vol = float(vol_ul)
                    if vol <= 0:
                        continue
                    pump = self._resolve_pump(liquid_name)
                    plan.append({"device": DEVICE, "command": "to_well", "args": {"well": well, "pump": pump}})
                    plan.append({"device": DEVICE, "command": "dispense", "args": {"pump": pump, "vol": vol}})

                topoff_vol = nominal_volume - pigment_total
                if topoff_vol > 0:
                    diluent_pump = self._resolve_pump(diluent)
                    plan.append({"device": DEVICE, "command": "to_well", "args": {"well": well, "pump": diluent_pump}})
                    plan.append({"device": DEVICE, "command": "dispense", "args": {"pump": diluent_pump, "vol": topoff_vol}})

        return plan
