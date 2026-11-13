# host/cogs/pixel_art_cog.py

import json
import re
from pathlib import Path

from host.cogs.base_cog import BaseCog
from host.gui.console import C

DEVICE = "sidekick"
ROWS = 8
COLS = 12
DEFAULT_UNIT_INCREMENT_UL = 10.0
DEFAULT_NOMINAL_WELL_VOLUME_UL = 100.0
DEFAULT_MAX_WELL_VOLUME_UL = 200.0
DEFAULT_DILUENT = "water"

# Rough runtime model, mirroring firmware/sidekick/__init__.py pump_timings.
DISPENSE_SECONDS_PER_CYCLE = 0.25
MOVE_SECONDS_PER_DISPENSE = 1.5
HOME_SECONDS = 5.0
PARK_SECONDS = 3.0


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
        """Slash commands for the pixel art workflow. Usage: /art <subcommand>."""
        return {
            "/art": self.cmd_art,
            "art list": self.cmd_art_list,
            "art show": self.cmd_art_show,
            "art plan": self.cmd_art_plan,
            "art run": self.cmd_art_run,
        }

    @staticmethod
    def _as_args_str(args) -> str:
        """Accept either a single argument string or the token list ChatApp passes."""
        if isinstance(args, (list, tuple)):
            return " ".join(str(a) for a in args).strip()
        return str(args or "").strip()

    def cmd_art(self, *args):
        """Routes '/art <subcommand> ...' to the matching handler. Usage: /art list|show|plan|run <name>"""
        tokens = [str(a) for a in args]
        if not tokens:
            print(f"{C.ERR}Usage: /art <list|show|plan|run> [name]{C.END}")
            return

        subcommand = tokens[0].lower()
        handlers = {
            "list": self.cmd_art_list,
            "show": self.cmd_art_show,
            "plan": self.cmd_art_plan,
            "run": self.cmd_art_run,
        }
        handler = handlers.get(subcommand)
        if handler is None:
            print(f"{C.ERR}Unknown art subcommand: '{subcommand}'. Try: {', '.join(handlers)}{C.END}")
            return

        handler(" ".join(tokens[1:]))

    def cmd_art_list(self, args: str = "") -> None:
        """List every art schema in the art directory. Usage: /art list"""
        self.art_dir.mkdir(parents=True, exist_ok=True)

        files = sorted(self.art_dir.glob("*.json"))
        if not files:
            print(f"{C.WARN}No art schemas found in {self.art_dir}.{C.END}")
            return

        print(f"\n{C.INFO}--- Art Schemas ({self.art_dir}) ---{C.END}")
        for path in files:
            try:
                schema = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                print(f"  {C.ERR}{path.name}{C.END}: unreadable JSON ({exc})")
                continue

            geometry = schema.get("plate_geometry", {})
            dims = f"{geometry.get('rows', '?')}x{geometry.get('cols', '?')}"
            print(f"  {C.OK}{path.stem:<12}{C.END} [{dims}] {schema.get('name', 'Untitled')}")
            description = schema.get("description", "")
            if description:
                print(f"    {description}")

    def cmd_art_show(self, args: str = "") -> None:
        """Show an art schema: header, ASCII grid preview, and palette legend. Usage: /art show <name>"""
        name = self._as_args_str(args)
        if not name:
            name = input("Artwork name: ").strip()
            if not name:
                print(f"{C.ERR}No artwork name provided.{C.END}")
                return

        try:
            schema = self._load_art_schema(name)
        except (FileNotFoundError, ValueError) as exc:
            print(f"{C.ERR}{exc}{C.END}")
            return

        geometry = schema.get("plate_geometry", {})
        rows = int(geometry.get("rows", ROWS))
        cols = int(geometry.get("cols", COLS))
        volume_config = schema.get("volume_config", {})
        nominal_volume = float(volume_config.get("nominal_well_volume_ul", DEFAULT_NOMINAL_WELL_VOLUME_UL))

        print(f"\n{C.INFO}=== {schema.get('name', name)} ==={C.END}")
        print(f"Grid: {rows}x{cols} | Nominal well volume: {nominal_volume} uL | Diluent: {volume_config.get('diluent', DEFAULT_DILUENT)}")
        if schema.get("description"):
            print(f"{schema['description']}")

        print()
        print(self._format_grid_preview(schema, rows, cols))

        print(f"\n{C.INFO}--- Palette Legend ---{C.END}")
        palette = schema.get("palette", {})
        for token in sorted(palette):
            entry = palette[token]
            liquids_ul = entry.get("liquids_ul", {})
            pigment_total = sum(float(v) for v in liquids_ul.values())
            topoff = max(0.0, nominal_volume - pigment_total)

            if liquids_ul:
                mix = ", ".join(
                    f"{liquid} {float(vol)} uL" for liquid, vol in liquids_ul.items()
                )
            else:
                mix = "no pigments"

            pumps = ", ".join(
                f"{liquid}={self._safe_resolve_pump(liquid)}" for liquid in liquids_ul
            )
            print(f"  {C.OK}{token}{C.END}  {entry.get('name', 'Unnamed')}")
            print(f"       mix: {mix}")
            if pumps:
                print(f"       pumps: {pumps}")
            print(f"       top-off: {topoff} uL ({pigment_total + topoff} uL in well)")

    def cmd_art_plan(self, args: str = "") -> None:
        """Dry-run: print plan summary statistics without sending any hardware commands. Usage: /art plan <name>"""
        name = self._as_args_str(args)
        if not name:
            print(f"{C.ERR}Usage: /art plan <name>{C.END}")
            return

        try:
            schema = self._load_art_schema(name)
            plan = self._grid_to_plan(schema)
        except (FileNotFoundError, ValueError) as exc:
            print(f"{C.ERR}{exc}{C.END}")
            return

        stats = self._plan_stats(schema, plan)

        print(f"\n{C.INFO}=== Plan Summary: {schema.get('name', name)} ==={C.END}")
        print(f"  Artwork:        {schema.get('name', name)} ({name}.json)")
        print(f"  Grid:           {stats['rows']}x{stats['cols']} ({stats['cells']} cells)")
        print(f"  Active wells:   {stats['active_wells']}")
        print(f"  Steps:          {stats['steps']} "
              f"(home {stats['home_steps']}, move {stats['move_steps']}, dispense {stats['dispense_steps']}, "
              f"park {stats['park_steps']})")
        print(f"  Dispense cycles: {stats['cycles']}")
        print(f"  Total volume:   {stats['total_ul']} uL")
        print(f"  Est. runtime:   {self._format_duration(stats['estimated_seconds'])} "
              f"({stats['estimated_seconds']:.1f} s, open-loop estimate)")

        print(f"\n{C.INFO}--- Per-liquid breakdown ---{C.END}")
        for liquid, volume in sorted(stats["per_liquid"].items(), key=lambda kv: -kv[1]):
            pump = stats["pumps"].get(liquid, "?")
            print(f"  {liquid:<12} {pump:<4} {volume:>8.1f} uL")

    def cmd_art_run(self, args: str = "") -> None:
        """Execute an artwork on the plate: log intent + per-well observations, then run the plan. Usage: /art run <name>"""
        name = self._as_args_str(args)
        if not name:
            print(f"{C.ERR}Usage: /art run <name>{C.END}")
            return

        try:
            schema = self._load_art_schema(name)
            plan = self._grid_to_plan(schema)
        except (FileNotFoundError, ValueError) as exc:
            print(f"{C.ERR}{exc}{C.END}")
            return

        stats = self._plan_stats(schema, plan)
        print(f"\n{C.INFO}=== Executing {schema.get('name', name)} ==={C.END}")
        print(f"  {stats['active_wells']} wells, {stats['steps']} steps, "
              f"~{self._format_duration(stats['estimated_seconds'])}")

        engine = self._get_execution_engine()
        if engine is None:
            print(f"{C.ERR}No execution engine available. Is run_cog loaded? Use /art plan <name> for a dry run.{C.END}")
            return

        if getattr(self.app, "require_confirmation", False):
            answer = input("Confirm execution? [y/N] ").strip().lower()
            if answer not in ("y", "yes"):
                print(f"{C.WARN}Execution cancelled.{C.END}")
                return

        # 1. Log the intent (with the expanded plan) to get a valid plan_id.
        plan_id = self.dln.log_science(
            entry_type="intent",
            data={"intent": f"Execute pixel art: {schema.get('name', name)}", "plan": plan},
        )
        print(f"{C.OK}[*] Intent logged (ID: {plan_id}).{C.END}")

        # 2. Log one observation per non-empty well so the artwork can be reconstructed.
        cell_count = self._log_cell_observations(schema)
        print(f"{C.OK}[*] {cell_count} well observations logged.{C.END}")

        # 3. Hand the expanded plan to the execution engine.
        engine.execute_plan(plan, plan_id=plan_id)
        print(f"{C.OK}[*] Pixel art '{schema.get('name', name)}' executed ({len(plan)} steps).{C.END}")

    def _log_cell_observations(self, schema: dict) -> int:
        """Log one DLN observation per well that receives liquid. Returns the number logged."""
        palette = schema.get("palette", {})
        volume_config = schema.get("volume_config", {})
        nominal_volume = float(volume_config.get("nominal_well_volume_ul", DEFAULT_NOMINAL_WELL_VOLUME_UL))

        logged = 0
        for row_idx, row in enumerate(schema.get("grid", [])):
            row_letter = chr(ord("A") + row_idx)
            for col_idx, char in enumerate(row):
                liquids_ul = palette.get(char, {}).get("liquids_ul", {})
                pigment_total = sum(float(v) for v in liquids_ul.values())
                topoff = max(0.0, nominal_volume - pigment_total)
                total_vol = pigment_total + topoff
                if total_vol <= 0:
                    continue

                self.dln.log_science(
                    entry_type="observation",
                    data={
                        "well": f"{row_letter}{col_idx + 1}",
                        "liquids": liquids_ul,
                        "total_vol_ul": total_vol,
                    },
                )
                logged += 1

        return logged

    def _plan_stats(self, schema: dict, plan: list[dict]) -> dict:
        """Summarise an expanded plan: wells, steps, per-liquid volumes, and estimated runtime."""
        geometry = schema.get("plate_geometry", {})
        rows = int(geometry.get("rows", ROWS))
        cols = int(geometry.get("cols", COLS))
        volume_config = schema.get("volume_config", {})
        nominal_volume = float(volume_config.get("nominal_well_volume_ul", DEFAULT_NOMINAL_WELL_VOLUME_UL))
        increment = float(volume_config.get("unit_increment_ul", DEFAULT_UNIT_INCREMENT_UL))

        per_liquid: dict[str, float] = {}
        pumps: dict[str, str] = {}
        wells: set[str] = set()
        home_steps = move_steps = dispense_steps = park_steps = 0
        cycles = 0

        for step in plan:
            command = step.get("command")
            step_args = step.get("args", {})
            if command == "home":
                home_steps += 1
                continue
            if command == "park":
                park_steps += 1
                continue
            if command == "to_well":
                move_steps += 1
                well = step_args.get("well")
                if well:
                    wells.add(well)
                continue
            if command != "dispense":
                continue

            dispense_steps += 1
            pump = step_args.get("pump")
            vol = float(step_args.get("vol", 0.0))

            liquid = self._liquid_for_pump(pump)
            per_liquid[liquid] = per_liquid.get(liquid, 0.0) + vol
            pumps[liquid] = pump
            if vol > 0:
                cycles += int(vol / increment)

        estimated_seconds = (
            HOME_SECONDS
            + dispense_steps * MOVE_SECONDS_PER_DISPENSE
            + cycles * DISPENSE_SECONDS_PER_CYCLE
            + park_steps * PARK_SECONDS
        )

        return {
            "rows": rows,
            "cols": cols,
            "cells": rows * cols,
            "active_wells": len(wells),
            "steps": len(plan),
            "home_steps": home_steps,
            "move_steps": move_steps,
            "dispense_steps": dispense_steps,
            "park_steps": park_steps,
            "cycles": cycles,
            "total_ul": round(sum(per_liquid.values()), 6),
            "per_liquid": per_liquid,
            "pumps": pumps,
            "estimated_seconds": estimated_seconds,
            "nominal_volume": nominal_volume,
        }

    def _liquid_for_pump(self, pump: str) -> str:
        """Reverse lookup: pump key -> reagent description, falling back to the pump key."""
        reagents = self.app.world_model.get("reagents", {})
        return str(reagents.get(pump, pump))

    @staticmethod
    def _format_duration(seconds: float) -> str:
        """Format seconds as 'Xm Ys'."""
        minutes, secs = divmod(int(round(seconds)), 60)
        return f"{minutes}m {secs:02d}s"

    def _get_execution_engine(self):
        """Find an ExecutionEngine: on the app, or via the loaded run cog."""
        engine = getattr(self.app, "execution_engine", None)
        if engine is not None:
            return engine

        run_cog = self.app.cog_manager.loaded_cogs.get("run_cog")
        return getattr(run_cog, "execution_engine", None)

    def _safe_resolve_pump(self, liquid_name: str) -> str:
        """Resolve a pump for display purposes, reporting unassigned liquids without raising."""
        try:
            return self._resolve_pump(liquid_name)
        except ValueError:
            return "?"

    @staticmethod
    def _format_grid_preview(schema: dict, rows: int, cols: int) -> str:
        """Render the grid as ASCII with row letters (A-H) and column headers (1-12)."""
        grid = schema.get("grid", [])
        header = "   " + " ".join(f"{col:>2}" for col in range(1, cols + 1))
        lines = [header, "   " + "-" * (cols * 3 - 1)]

        for row_idx in range(rows):
            row = (grid[row_idx] if row_idx < len(grid) else "").ljust(cols)
            letter = chr(ord("A") + row_idx)
            lines.append(f"{letter}  " + " ".join(f"{ch:>2}" for ch in row))

        return "\n".join(lines)

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

        # Park the arm over the safe park position once the canvas is complete.
        plan.append({"device": DEVICE, "command": "park", "args": {}})

        return plan
