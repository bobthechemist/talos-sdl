# Plan: Pixel Art Demo on the 96-Well Plate (Sidekick)

## Verdict on current prompt/context sufficiency

Insufficient for LLM-generated art; adequate only for a deterministic, host-expanded plan.

Verified gaps in `host/ai/prompt_factory.py` (`_build_run_system_prompt`):
- No plate geometry (rows A-H, cols 1-12, well format) — AI infers only from `to_well` description.
- No color-mixing model (R+Y=orange etc.), no "white = blank cell = no dispense" rule.
- No volume rules: `calculate_dispense_cycles` requires vol >= 10 uL and multiples of 10; `max_well_volume_ul` exists in `world_model.json.template` but is never injected into any prompt.
- "SCHEMA AWARENESS" tells the AI to read a `returns` key that no command anywhere defines.
- No plan-size/abstraction guidance; `ExecutionEngine.execute_plan` has no loop abstraction, so 96 pixels = 96+ flat command objects. Small local models (current `world_model.json` = ollama) truncate or drift on 96-item JSON.
- `ai_guidance` for sidekick references the colorimeter, which is not part of this demo.

Blockers found:
- `host/ai/chat.py` `__init__` re-assigns `self.host_tools = {}` AFTER `cog_manager.load_cogs()`, wiping host tools registered by cogs. Must be removed for any cog host tool to work.
- `firmware/sidekick/handlers.py` `handle_to_well_with_pumps` exists but is never registered via `machine.add_command`, so the AI cannot use the atomic move+dispense.
- `handle_dispense` and `handle_dispense_at` have `@try_wrapper` commented out; an exception mid-run produces no PROBLEM and the engine times out 60s per step.
- `get_current_position_degrees` calls undefined `_get_current_position_steps` (the function is `get_current_position_steps`). Latent NameError.

## User decisions
- Art authority: `PixelArtCog` with `KnownArt` (stored mappings, deterministic) and `GenArt` (external agent, skeleton only, not implemented now).
- Verification: open-loop dispense only, no colorimeter read-back.
- Model target: local Ollama — prompt must stay short, grid output, small plans.
- Deliverable: host cog + prompt additions + docs.

## Architecture

Single shared routine: grid -> plan. Two entry paths (slash command, AI host tool) both call it.
Grid format: 8 rows x 12 chars, one char per cell, char maps to a pump via palette. Multi-char cell = multiple dispenses (mixing). Blank/white char = skip.

## Steps

### Phase 1 - Prompt and context hardening
1. `host/ai/prompt_factory.py`: extend `PromptFactory` with an optional `extra_context` dict (or `context_sections`) merged into `_build_run_system_prompt`; add a `# PLATE CANVAS` section (geometry, well format, blank = no dispense) and a `# PALETTE AND MIXING` section (pump->color from `world_model['reagents']`, additive mixing, min 10 uL / multiples of 10, max well volume). Remove or fix the stale `returns` claim.
2. `host/cogs/pixel_art_cog.py` contributes its guidance through `app.ai_guidance["pixel_art"]` at load time (CogManager runs before `PromptFactory` in `ChatApp.__init__`, so this is reflected in the system prompt). Guidance must tell the planner to call the `render_pixel_art` host tool with a grid rather than emitting 96 steps.
3. `host/ai/chat.py`: delete the duplicate `host_tools` / `ai_guidance["host"]` block at the end of `__init__`.

### Phase 2 - PixelArtCog
4. New `host/cogs/pixel_art_cog.py`, class `PixelArtCog(BaseCog)`:
   - Slash commands: `/art list`, `/art show <name>`, `/art known <name>`, `/art gen <prompt>`, `/art plan <name>` (dry-run, prints expanded plan without executing).
   - Host tool `render_pixel_art` (ai_enabled) with signature `(args, plan_id, step_idx, engine, app)`; validates grid, calls `engine.inject_steps(plan)`, returns a dict summary so `ExecutionEngine._handle_data_response` logs it.
   - `_grid_to_plan(grid)`: emits `to_well(well, pump)` + `dispense(pump, vol)` pairs (or single `fill_well` steps if firmware step 7 is done), row-major order for short moves, always preceded by `home`.
   - `_validate_grid(grid)`: exactly 8x12, chars must exist in palette, error otherwise.
   - DLN logging: `intent` + `plan` entries matching `RunCog` conventions, plus one `observation` per well with expected color so `/data` and `host/summarize.py` can reconstruct the artwork.
   - Compact HITL summary (cell count, per-color counts, total uL) instead of a 96-line plan review.
5. Register `pixel_art_cog` in `required_cogs` of the demo world model (contextual loading would skip it when no hardware is connected, which breaks dry-run).

### Phase 3 - KnownArt library
6. New `data/art/` with seed mappings, JSON schema: name, grid (8 strings of 12 chars), palette (char -> pump key), default volume per cell. Seed: smiley, rainbow gradient, Bayer-style, checkerboard.
7. `world_model.pixel_art.json` demo world model: experiment name, reagents p1 red / p2 yellow / p3 blue / p4 water, plate geometry, default pixel volume, required cogs incl. `pixel_art_cog`.

### Phase 4 - GenArt skeleton
8. In `PixelArtCog`, `_generate_grid(prompt)` stub: lazily builds a separate agent via `LLMManager.get_agent` with an art-specific system prompt (grid output only, no plan JSON), parses/validates with the same `_validate_grid`, and raises NotImplementedError for the actual LLM call. Keep the parser and format contract complete so implementation is a one-line swap later.

### Phase 5 - Firmware fixes
9. `firmware/sidekick/__init__.py`: register `handle_to_well_with_pumps` as `fill_well` (well, pump, vol), ai_enabled, with effects/usage_notes.
10. `firmware/sidekick/handlers.py`: restore `@try_wrapper` on `handle_dispense` and `handle_dispense_at`; fix `_get_current_position_steps` NameError.

### Phase 6 - Docs
11. New `docs/tutorials/pixel_art_demo.md` (prompt, run transcript, expected output, failure modes) + `mkdocs.yml` nav entry.

## Relevant files
- `host/ai/prompt_factory.py` - extra context sections, palette/canvas/volume rules
- `host/ai/chat.py` - remove duplicate host_tools reset
- `host/cogs/pixel_art_cog.py` - new cog, grid parser, plan expander, host tool
- `host/cogs/cog_manager.py` - reuse existing host tool registration pattern
- `host/ai/execution_engine.py` - reuse `inject_steps` and host tool callback signature
- `firmware/sidekick/__init__.py` - register `fill_well`
- `firmware/sidekick/handlers.py` - `handle_to_well_with_pumps`, `calculate_dispense_cycles`, `parse_well_designation`
- `dln/dln.py` - `log_science`, `query_relational`, `store_blob`

## Verification
1. Unit test `tests/host/test_pixel_art_cog.py` (new dir): grid validation (wrong size, unknown char), plan expansion (cell count, skip blanks, mixing cells), no hardware required.
2. Dry run: `/art plan smiley` prints expanded plan; compare against expected step count.
3. Hardware smoke test with a 4-cell art before the full 96.
4. After a run, DLN query on `entry_type='observation'` with `json_extract(data,'$.well')` must reconstruct the grid identically to the source mapping.
5. Confirm `app.host_tools` contains `render_pixel_art` after cog load (post-fix).
6. Timing check: 96 cells x (move + 1 cycle) should complete in a few minutes; measure one full run.

## Decisions
- Grid format chosen over JSON plan output for small-model reliability.
- Open-loop: no colorimeter, but per-well DLN observations still logged for reproducibility.
- Excluded: image rendering, camera capture, colorimeter verification, GenArt LLM implementation.
- Known risk: host tool injects steps mid-execution, bypassing per-step human review; the operator approves the aggregate render step.

## Further considerations
1. Plan expansion via host tool (recommended) vs. cog slash command executing directly — host tool keeps the AI in the loop and matches the dynamic execution engine design.
2. `fill_well` halves plan size and serial round trips (recommended) vs. `to_well` + `dispense` pair with no firmware change.
3. Whether KnownArt mappings live in `data/art/` (runtime, writable, recommended) or `docs/_assets/art/` (documentation, read-only).
