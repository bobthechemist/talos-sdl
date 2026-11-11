# host/cogs/pixel_art_cog.py

import json
import re
from pathlib import Path

from host.cogs.base_cog import BaseCog


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
