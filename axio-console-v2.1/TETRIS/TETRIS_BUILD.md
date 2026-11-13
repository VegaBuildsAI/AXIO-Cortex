# BUILD TASK — Playable Tetris in Python (pygame)

> **How to use this file — LOCAL ONLY (gemma4:12b, no Claude):**
>
> Launch Code mode fully on-device, then paste the whole contents of this file as
> your task. In PowerShell:
>
> ```powershell
> cd "C:\Users\AXIO\AXIO Model Improvement\axio-console-v2.1"
> $env:LOCAL_ONLY = "1"
> py axio.py code
> ```
>
> (Or set `LOCAL_ONLY=1` in `.env` and run `py axio.py code`.) Under `LOCAL_ONLY=1`
> everything runs through `gemma4:12b`; the `--claude` flag is ignored. Confirm the
> banner shows `Local agent: READY (gemma4:12b)` and `Claude API: OFF (local-only)`.
>
> You will be asked to **approve** the `pip install` / compile / test commands —
> that's the normal `execute`-risk gate. Approve them.
>
> **Working with the local model:** `gemma4:12b` is capable but smaller, so it may
> take **several gate-driven iterations** — that is expected and fine. The
> verification gate will keep it honest: it cannot declare the task complete until
> `py -m py_compile` and the headless `--selftest` both pass. If it stalls, tell it
> `continue` or `fix the failing selftest`. Build the **core game first**; the items
> marked *optional* below can be added last (or skipped) without failing acceptance.

---

## Objective

Create a **complete, single-file, runnable Tetris game** at
`workspaces/tetris/tetris.py` that I can start with `py tetris.py` and play with the
keyboard. Use **pygame** for the window and rendering. Do not split into multiple
files — one `tetris.py`.

## Environment

- Windows, Python via the `py` launcher.
- One dependency: **pygame** (`py -m pip install pygame`).
- Target directory: the current workspace folder `workspaces/tetris/`. Write
  `tetris.py` there (use an absolute path).

## Functional requirements (acceptance criteria)

1. **Board:** standard 10 columns × 20 visible rows. Render a visible grid.
2. **Pieces:** all 7 tetrominoes — I, O, T, S, Z, J, L — each with its conventional
   color. Pieces spawn at the top center.
3. **Movement & rotation:**
   - Move left / right; soft drop (down); **hard drop** (space) that instantly
     locks the piece.
   - Rotate **clockwise** (required). **Counter-clockwise** rotation is *optional*.
   - **Basic wall kicks** are *optional but recommended*: if a rotation collides
     with a wall/floor/stack, try nudging ±1 (and ±2 for I) horizontally before
     rejecting the rotation. If omitted, simply reject rotations that don't fit.
4. **Gravity:** pieces fall automatically on a timer; the interval shortens as the
   level rises. Locking a piece spawns the next one.
5. **Line clears & scoring:** clear 1–4 full rows at once; award
   `100 / 300 / 500 / 800` points for `1 / 2 / 3 / 4` lines, multiplied by the
   current level. Increase **level every 10 cleared lines**; gravity speeds up each
   level.
6. **Next-piece preview** shown beside the board. (A **hold** slot is a nice-to-have.)
7. **HUD:** current score, level, and total lines cleared.
8. **States:** **Pause** (P), **Game over** with a restart prompt (R), and a clean
   quit (Esc or window close). No crashes or unhandled exceptions.
9. **Frame pacing:** ~60 FPS using `pygame.time.Clock`; input must feel responsive
   (handle held-key repeat for left/right/soft-drop, e.g. via `pygame.key.set_repeat`
   or a manual DAS timer).

## Controls (implement exactly, and print them on the game-over screen)

| Key            | Action                    |
|----------------|---------------------------|
| ← / →          | Move left / right         |
| ↓              | Soft drop                 |
| Space          | Hard drop (lock)          |
| ↑ or X         | Rotate clockwise          |
| Z or Ctrl      | Rotate counter-clockwise  |
| C              | Hold (if implemented)     |
| P              | Pause / resume            |
| R              | Restart (after game over) |
| Esc            | Quit                      |

## Headless self-test (REQUIRED — this is how you verify without a window)

A GUI window cannot be verified by you and **will block the console** — so **do not
launch the interactive game**. Instead, build a headless self-test into the same
file:

- Support a `--selftest` command-line flag.
- On `--selftest`, force pygame's dummy video driver so **no window opens**:
  at the very top of the file, before importing/initializing pygame, do
  `if "--selftest" in sys.argv: os.environ["SDL_VIDEODRIVER"] = "dummy"`.
- The self-test must exercise the **core logic directly** (not the render loop) with
  `assert`s:
  - each tetromino rotates through its states and back to origin;
  - collision detection rejects out-of-bounds and overlapping placements;
  - a manually filled bottom row is detected and cleared, and rows above shift down;
  - scoring returns 100/300/500/800 × level for 1/2/3/4 line clears;
  - a piece hard-dropped into a full column triggers game-over.
- On success, `print("SELFTEST OK")` and `sys.exit(0)`. On any failure, let the
  assertion raise (non-zero exit).

Structure the code so logic (board, piece, collision, clear, score) is callable
without the render loop — e.g. plain functions/classes the self-test imports, with
`main()` doing the pygame loop only when not in self-test mode.

## Build procedure — do these steps in order, using your tools

1. `inspect_python_environment` on the target dir — confirm Python is available.
2. `run_command`: `py -m pip install pygame`  *(approve the gate)*.
3. `write_file`: create the absolute-path `.../workspaces/tetris/tetris.py` with the
   full implementation above.
4. `run_command`: `py -m py_compile <abs path>\tetris.py` — must exit 0 (syntax gate).
5. `run_command` (PowerShell) headless test:
   `$env:SDL_VIDEODRIVER='dummy'; py "<abs path>\tetris.py" --selftest`
   — output must contain `SELFTEST OK` and exit 0. If it fails, read the traceback,
   fix `tetris.py`, and re-run this step until it passes.
6. Call **`verification_gate`** — it should pass on the successful compile + self-test.
7. **Do NOT run `py tetris.py`** (the real GUI) — it blocks and you can't see it.
   Finish by reporting the exact command for the user to run.

## Definition of done (self-check before you say TASK_COMPLETE)

- [ ] `workspaces/tetris/tetris.py` exists and `py -m py_compile` passes.
- [ ] `py tetris.py --selftest` prints `SELFTEST OK` and exits 0.
- [ ] All 7 pieces, CW rotation, gravity, soft/hard drop implemented (CCW + wall kicks optional).
- [ ] Line clears with 100/300/500/800 × level scoring; level up every 10 lines.
- [ ] Next-piece preview + HUD (score/level/lines); pause, game over + restart, quit.
- [ ] `verification_gate` passed.
- [ ] You reported the run command below and did NOT launch the GUI yourself.

## How the user runs it (include this in your final message)

```powershell
cd "C:\Users\AXIO\AXIO Model Improvement\axio-console-v2.1\workspaces\tetris"
py tetris.py
```

If pygame is missing at runtime: `py -m pip install pygame`.
