# tests/host/test_pixel_art_cog.py
"""Unit tests for host/cogs/pixel_art_cog.py. No hardware required."""

import contextlib
import io
import json
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from host.cogs.pixel_art_cog import PixelArtCog

ANSI_RE = re.compile(r"\033\[[0-9;]*m")

DEFAULT_REAGENTS = {
    "p1": "Red Food Coloring",
    "p2": "Yellow",
    "p3": "Blue",
    "p4": "Water",
}


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def capture_stdout(func, *args, **kwargs) -> str:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        func(*args, **kwargs)
    return buffer.getvalue()


class FakeDLN:
    """Records log_science calls instead of writing to SQLite."""

    def __init__(self):
        self.entries = []

    def log_science(self, entry_type: str, data: dict, supersedes_id=None, reason=None) -> int:
        self.entries.append({"entry_type": entry_type, "data": data})
        return len(self.entries)

    def entries_of(self, entry_type: str) -> list:
        return [e for e in self.entries if e["entry_type"] == entry_type]


class FakeEngine:
    """Records execute_plan calls instead of talking to hardware."""

    def __init__(self):
        self.calls = []

    def execute_plan(self, plan: list, plan_id: int = None):
        self.calls.append({"plan": plan, "plan_id": plan_id})


class FakeApp:
    def __init__(self, reagents=None, dln=None, engine=None, require_confirmation: bool = False):
        self.world_model = {"reagents": dict(DEFAULT_REAGENTS if reagents is None else reagents)}
        self.dln = dln or FakeDLN()
        self.device_manager = None
        self.require_confirmation = require_confirmation
        self.execution_engine = engine
        self.cog_manager = SimpleNamespace(loaded_cogs={})


def make_schema(grid, palette, rows=8, cols=12, nominal=100.0, increment=10.0, diluent="water"):
    return {
        "name": "Test Art",
        "description": "test schema",
        "plate_geometry": {"rows": rows, "cols": cols},
        "volume_config": {
            "nominal_well_volume_ul": nominal,
            "unit_increment_ul": increment,
            "diluent": diluent,
        },
        "palette": palette,
        "grid": grid,
    }


def full_grid(char, rows=8, cols=12):
    return [char * cols] * rows


class TestPixelArtCogPumpResolution(unittest.TestCase):
    def setUp(self):
        self.cog = PixelArtCog(FakeApp())

    def test_valid_mappings(self):
        self.assertEqual(self.cog._resolve_pump("red"), "p1")
        self.assertEqual(self.cog._resolve_pump("yellow"), "p2")
        self.assertEqual(self.cog._resolve_pump("blue"), "p3")
        self.assertEqual(self.cog._resolve_pump("water"), "p4")

    def test_matching_is_case_insensitive_and_trims(self):
        self.assertEqual(self.cog._resolve_pump("RED"), "p1")
        self.assertEqual(self.cog._resolve_pump("  Water  "), "p4")

    def test_substring_of_description_matches(self):
        # "red" is a substring of "Red Food Coloring".
        self.assertEqual(self.cog._resolve_pump("red"), "p1")
        self.assertEqual(self.cog._resolve_pump("food"), "p1")

    def test_missing_liquid_raises_value_error(self):
        with self.assertRaises(ValueError) as ctx:
            self.cog._resolve_pump("purple")
        self.assertEqual(
            str(ctx.exception),
            "No pump assigned for liquid 'purple' in world model reagents",
        )

    def test_empty_reagents_raises(self):
        cog = PixelArtCog(FakeApp(reagents={}))
        with self.assertRaises(ValueError):
            cog._resolve_pump("red")


class TestPixelArtCogValidation(unittest.TestCase):
    def setUp(self):
        self.cog = PixelArtCog(FakeApp())
        self.palette = {
            "R": {"name": "Red", "liquids_ul": {"red": 30.0}},
            "O": {"name": "Orange", "liquids_ul": {"red": 20.0, "yellow": 10.0}},
            ".": {"name": "Background", "liquids_ul": {}},
        }

    def test_valid_schema_passes(self):
        self.cog._validate_grid(make_schema(full_grid("R"), self.palette))
        self.cog._validate_grid(make_schema(full_grid("."), self.palette))

    def test_wrong_row_count(self):
        with self.assertRaises(ValueError) as ctx:
            self.cog._validate_grid(make_schema(full_grid("R")[:7], self.palette))
        self.assertIn("exactly 8 rows", str(ctx.exception))

    def test_wrong_row_length(self):
        grid = full_grid("R")
        grid[3] = "R" * 11
        with self.assertRaises(ValueError) as ctx:
            self.cog._validate_grid(make_schema(grid, self.palette))
        self.assertIn("row 3", str(ctx.exception))
        self.assertIn("12 characters", str(ctx.exception))

    def test_non_string_row(self):
        grid = full_grid("R")
        grid[0] = 12
        with self.assertRaises(ValueError) as ctx:
            self.cog._validate_grid(make_schema(grid, self.palette))
        self.assertIn("must be a string", str(ctx.exception))

    def test_unknown_palette_character(self):
        with self.assertRaises(ValueError) as ctx:
            self.cog._validate_grid(make_schema(full_grid("X"), self.palette))
        self.assertIn("not defined in palette", str(ctx.exception))
        self.assertIn("X", str(ctx.exception))

    def test_volume_not_multiple_of_increment(self):
        palette = {"R": {"name": "Red", "liquids_ul": {"red": 15.0}}}
        with self.assertRaises(ValueError) as ctx:
            self.cog._validate_grid(make_schema(full_grid("R"), palette))
        self.assertIn("not a multiple", str(ctx.exception))

    def test_custom_increment_is_respected(self):
        palette = {"R": {"name": "Red", "liquids_ul": {"red": 25.0}}}
        # 25 is a multiple of a 5 uL increment.
        self.cog._validate_grid(make_schema(full_grid("R"), palette, increment=5.0, nominal=100.0))
        with self.assertRaises(ValueError):
            self.cog._validate_grid(make_schema(full_grid("R"), palette, increment=10.0))

    def test_exceeds_max_well_volume(self):
        palette = {"R": {"name": "Red", "liquids_ul": {"red": 250.0}}}
        with self.assertRaises(ValueError) as ctx:
            self.cog._validate_grid(make_schema(full_grid("R"), palette))
        self.assertIn("max_well_volume_ul", str(ctx.exception))

    def test_max_well_volume_comes_from_world_model(self):
        cog = PixelArtCog(FakeApp())
        cog.app.world_model["max_well_volume_ul"] = 120.0
        palette = {"R": {"name": "Red", "liquids_ul": {"red": 130.0}}}
        with self.assertRaises(ValueError):
            cog._validate_grid(make_schema(full_grid("R"), palette))
        # Same palette is fine under a larger limit.
        cog.app.world_model["max_well_volume_ul"] = 300.0
        cog._validate_grid(make_schema(full_grid("R"), palette))

    def test_negative_volume_rejected(self):
        palette = {"R": {"name": "Red", "liquids_ul": {"red": -10.0}}}
        with self.assertRaises(ValueError) as ctx:
            self.cog._validate_grid(make_schema(full_grid("R"), palette))
        self.assertIn("negative", str(ctx.exception))

    def test_unresolvable_liquid_in_palette_rejected(self):
        palette = {"P": {"name": "Purple", "liquids_ul": {"purple": 20.0}}}
        with self.assertRaises(ValueError) as ctx:
            self.cog._validate_grid(make_schema(full_grid("P"), palette))
        self.assertIn("purple", str(ctx.exception))

    def test_unresolvable_diluent_rejected(self):
        palette = {".": {"name": "Background", "liquids_ul": {}}}
        with self.assertRaises(ValueError) as ctx:
            self.cog._validate_grid(make_schema(full_grid("."), palette, diluent="ethanol"))
        self.assertIn("ethanol", str(ctx.exception))

    def test_load_art_schema_strips_extension_and_raises_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.cog.art_dir = Path(tmp)
            (self.cog.art_dir / "art.json").write_text(json.dumps(make_schema(full_grid("R"), self.palette)))

            schema = self.cog._load_art_schema("art.json")
            self.assertEqual(schema["name"], "Test Art")
            self.assertEqual(self.cog._load_art_schema("art")["name"], "Test Art")

            with self.assertRaises(FileNotFoundError) as ctx:
                self.cog._load_art_schema("missing")
            self.assertIn("not found", str(ctx.exception))
            self.assertIn("art", str(ctx.exception))


class TestPixelArtCogPlanExpansion(unittest.TestCase):
    def setUp(self):
        self.cog = PixelArtCog(FakeApp())
        self.palette = {
            "R": {"name": "Red", "liquids_ul": {"red": 30.0}},
            "O": {"name": "Orange", "liquids_ul": {"red": 20.0, "yellow": 10.0}},
            ".": {"name": "Background", "liquids_ul": {}},
        }

    def test_plan_starts_with_home(self):
        plan = self.cog._grid_to_plan(make_schema(full_grid("R"), self.palette))
        self.assertEqual(plan[0], {"device": "sidekick", "command": "home", "args": {}})

    def test_two_step_pairs_for_single_liquid_cell(self):
        plan = self.cog._grid_to_plan(make_schema(full_grid("R"), self.palette))
        # home + (move + dispense) for red + (move + dispense) for water top-off, per well
        self.assertEqual(len(plan), 1 + 96 * 4)
        self.assertEqual(plan[1], {"device": "sidekick", "command": "to_well", "args": {"well": "A1", "pump": "p1"}})
        self.assertEqual(plan[2], {"device": "sidekick", "command": "dispense", "args": {"pump": "p1", "vol": 30.0}})
        self.assertEqual(plan[3], {"device": "sidekick", "command": "to_well", "args": {"well": "A1", "pump": "p4"}})
        self.assertEqual(plan[4], {"device": "sidekick", "command": "dispense", "args": {"pump": "p4", "vol": 70.0}})

    def test_mixing_cell_emits_pair_per_liquid(self):
        plan = self.cog._grid_to_plan(make_schema(full_grid("O"), self.palette))
        # home + 2 pigments * 2 steps + top-off pair, per well
        self.assertEqual(len(plan), 1 + 96 * 6)
        first_well = plan[1:7]
        self.assertEqual([s["args"]["well"] for s in first_well if s["command"] == "to_well"], ["A1"] * 3)
        self.assertEqual([s["args"]["pump"] for s in first_well], ["p1", "p1", "p2", "p2", "p4", "p4"])
        volumes = [s["args"]["vol"] for s in first_well if s["command"] == "dispense"]
        self.assertEqual(volumes, [20.0, 10.0, 70.0])

    def test_diluent_top_off_amount(self):
        plan = self.cog._grid_to_plan(make_schema(full_grid("R"), self.palette))
        top_off = [s for s in plan[1:] if s["command"] == "dispense" and s["args"]["pump"] == "p4"]
        self.assertEqual(len(top_off), 96)
        self.assertEqual(top_off[0]["args"]["vol"], 70.0)  # 100 nominal - 30 pigment

    def test_no_top_off_when_cell_is_already_full(self):
        palette = {"R": {"name": "Full", "liquids_ul": {"red": 100.0}}}
        plan = self.cog._grid_to_plan(make_schema(full_grid("R"), palette))
        self.assertEqual(len(plan), 1 + 96 * 2)  # home + one pair per well
        self.assertEqual([s["command"] for s in plan[1:3]], ["to_well", "dispense"])

    def test_well_names_use_rows_a_to_h_and_columns_1_to_12(self):
        plan = self.cog._grid_to_plan(make_schema(full_grid("R"), self.palette))
        wells = list(dict.fromkeys(s["args"]["well"] for s in plan if s["command"] == "to_well"))
        self.assertEqual(wells[0], "A1")
        self.assertEqual(wells[12], "B1")
        self.assertEqual(wells[-1], "H12")
        self.assertEqual(len(wells), 96)

    def test_total_step_count_for_full_plate(self):
        # 96 cells, one pigment each -> 2 steps per cell + home.
        plan = self.cog._grid_to_plan(make_schema(full_grid("R"), self.palette))
        self.assertEqual(len(plan), 1 + 96 * 4)

        # Blank cells: top-off only -> 2 steps per cell.
        plan_blank = self.cog._grid_to_plan(make_schema(full_grid("."), self.palette))
        self.assertEqual(len(plan_blank), 1 + 96 * 2)

    def test_smiley_art_expands_to_expected_step_count(self):
        schema = {
            "name": "Smiley Face",
            "plate_geometry": {"rows": 8, "cols": 12},
            "volume_config": {"nominal_well_volume_ul": 100.0, "unit_increment_ul": 10.0, "diluent": "water"},
            "palette": {
                ".": {"name": "Background", "liquids_ul": {}},
                "O": {"name": "Orange", "liquids_ul": {"red": 20.0, "yellow": 10.0}},
                "G": {"name": "Green", "liquids_ul": {"yellow": 20.0, "blue": 20.0}},
                "R": {"name": "Red", "liquids_ul": {"red": 30.0}},
            },
            "grid": [
                "...OOOOOO...",
                "..OOOOOOOO..",
                ".OOGGOOGGOO.",
                ".OOOOOOOOOO.",
                ".OROOOOOORO.",
                ".OORRRRRROO.",
                "..OOOOOOOO..",
                "...OOOOOO...",
            ],
        }
        plan = self.cog._grid_to_plan(schema)
        # 28 blanks (2 steps) + 56 orange (4) + 4 green (6) + 8 red (4) + home = 449
        self.assertEqual(len(plan), 449)

    def test_plan_expansion_validates_first(self):
        with self.assertRaises(ValueError):
            self.cog._grid_to_plan(make_schema(full_grid("Z"), self.palette))


class TestPixelArtCogSlashCommands(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.art_dir = Path(self.tmp.name)
        self.dln = FakeDLN()
        self.engine = FakeEngine()
        self.app = FakeApp(dln=self.dln, engine=self.engine)
        self.cog = PixelArtCog(self.app)
        self.cog.art_dir = self.art_dir

        self.smiley = {
            "name": "Smiley Face",
            "description": "8x12 smiley",
            "plate_geometry": {"rows": 8, "cols": 12},
            "volume_config": {"nominal_well_volume_ul": 100.0, "unit_increment_ul": 10.0, "diluent": "water"},
            "palette": {
                ".": {"name": "Background Water", "liquids_ul": {}},
                "R": {"name": "Red Lips", "liquids_ul": {"red": 30.0}},
            },
            "grid": ["RRRRRRRRRRRR"] + ["RRRRRRRRRRRR"] * 7,
        }
        (self.art_dir / "smiley.json").write_text(json.dumps(self.smiley), encoding="utf-8")

    def test_get_commands_registers_art_handlers(self):
        commands = self.cog.get_commands()
        self.assertEqual(commands["/art"], self.cog.cmd_art)
        self.assertEqual(commands["art list"], self.cog.cmd_art_list)
        self.assertEqual(commands["art show"], self.cog.cmd_art_show)
        self.assertEqual(commands["art plan"], self.cog.cmd_art_plan)
        self.assertEqual(commands["art run"], self.cog.cmd_art_run)

    def test_cmd_art_routes_subcommands(self):
        output = strip_ansi(capture_stdout(self.cog.cmd_art, "list"))
        self.assertIn("Smiley Face", output)

        output = strip_ansi(capture_stdout(self.cog.cmd_art, "bogus"))
        self.assertIn("Unknown art subcommand", output)

        output = strip_ansi(capture_stdout(self.cog.cmd_art))
        self.assertIn("Usage: /art", output)

    def test_art_list_creates_missing_directory_and_lists_schemas(self):
        self.cog.art_dir = Path(self.tmp.name) / "art-new"
        output = strip_ansi(capture_stdout(self.cog.cmd_art_list, ""))
        self.assertTrue(self.cog.art_dir.exists())
        self.assertIn("No art schemas found", output)

        self.cog.art_dir = self.art_dir
        output = strip_ansi(capture_stdout(self.cog.cmd_art_list, ""))
        self.assertIn("smiley", output)
        self.assertIn("Smiley Face", output)
        self.assertIn("8x12 smiley", output)

    def test_art_show_prints_header_grid_and_legend(self):
        output = strip_ansi(capture_stdout(self.cog.cmd_art_show, "smiley"))
        self.assertIn("=== Smiley Face ===", output)
        self.assertIn("Grid: 8x12", output)
        self.assertIn("100.0 uL", output)

        # Column headers and row letters.
        self.assertIn(" 1  2  3  4  5  6  7  8  9 10 11 12", output)
        self.assertIn("A ", output)
        self.assertIn("H ", output)

        # Legend with mix and top-off.
        self.assertIn("Red Lips", output)
        self.assertIn("red 30.0 uL", output)
        self.assertIn("red=p1", output)
        self.assertIn("top-off: 70.0 uL", output)

    def test_art_show_prompts_when_name_missing(self):
        with patch("builtins.input", return_value="smiley"):
            output = strip_ansi(capture_stdout(self.cog.cmd_art_show, ""))
        self.assertIn("=== Smiley Face ===", output)

        with patch("builtins.input", return_value=""):
            output = strip_ansi(capture_stdout(self.cog.cmd_art_show, ""))
        self.assertIn("No artwork name provided", output)

    def test_art_show_reports_missing_art_without_raising(self):
        output = strip_ansi(capture_stdout(self.cog.cmd_art_show, "nope"))
        self.assertIn("not found", output)

    def test_art_plan_prints_summary_without_executing(self):
        output = strip_ansi(capture_stdout(self.cog.cmd_art_plan, "smiley"))
        self.assertIn("Plan Summary", output)
        self.assertIn("Active wells:   96", output)
        self.assertIn("Steps:          385", output)  # home + 96 * (2 + 2)
        self.assertIn("Per-liquid breakdown", output)
        self.assertIn("Red Food Coloring", output)
        self.assertIn("2880.0 uL", output)  # 96 * 30 red
        self.assertIn("6720.0 uL", output)  # 96 * 70 water top-off
        self.assertIn("Est. runtime", output)
        self.assertEqual(self.engine.calls, [])
        self.assertEqual(self.dln.entries, [])

        output = strip_ansi(capture_stdout(self.cog.cmd_art_plan, ""))
        self.assertIn("Usage: /art plan", output)

    def test_art_run_logs_intent_and_observations_then_executes(self):
        output = strip_ansi(capture_stdout(self.cog.cmd_art_run, "smiley"))
        self.assertIn("Executing Smiley Face", output)
        self.assertIn("Intent logged", output)
        self.assertIn("96 well observations logged", output)

        intent_entries = self.dln.entries_of("intent")
        self.assertEqual(len(intent_entries), 1)
        self.assertEqual(intent_entries[0]["data"]["intent"], "Execute pixel art: Smiley Face")
        self.assertEqual(len(intent_entries[0]["data"]["plan"]), 385)

        observations = self.dln.entries_of("observation")
        self.assertEqual(len(observations), 96)
        self.assertEqual(observations[0]["data"]["well"], "A1")
        self.assertEqual(observations[0]["data"]["liquids"], {"red": 30.0})
        self.assertEqual(observations[0]["data"]["total_vol_ul"], 100.0)
        self.assertEqual(observations[-1]["data"]["well"], "H12")

        self.assertEqual(len(self.engine.calls), 1)
        self.assertEqual(len(self.engine.calls[0]["plan"]), 385)
        self.assertEqual(self.engine.calls[0]["plan_id"], 1)  # plan_id from the intent log
        self.assertIn("executed (385 steps)", output)

    def test_art_run_respects_confirmation_prompt(self):
        self.app.require_confirmation = True
        with patch("builtins.input", return_value="n"):
            output = strip_ansi(capture_stdout(self.cog.cmd_art_run, "smiley"))
        self.assertIn("Execution cancelled", output)
        self.assertEqual(self.engine.calls, [])
        self.assertEqual(self.dln.entries, [])

    def test_art_run_without_engine_reports_error(self):
        self.app.execution_engine = None
        output = strip_ansi(capture_stdout(self.cog.cmd_art_run, "smiley"))
        self.assertIn("No execution engine available", output)
        self.assertEqual(self.engine.calls, [])

    def test_art_run_falls_back_to_run_cog_engine(self):
        self.app.execution_engine = None
        self.app.cog_manager.loaded_cogs["run_cog"] = SimpleNamespace(execution_engine=self.engine)
        strip_ansi(capture_stdout(self.cog.cmd_art_run, "smiley"))
        self.assertEqual(len(self.engine.calls), 1)

    def test_art_run_reports_missing_art_without_executing(self):
        output = strip_ansi(capture_stdout(self.cog.cmd_art_run, "nope"))
        self.assertIn("not found", output)
        self.assertEqual(self.engine.calls, [])
        self.assertEqual(self.dln.entries, [])


if __name__ == "__main__":
    unittest.main()
