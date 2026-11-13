# BUILD TASK — Playable Tetris in Python (tkinter, no install)

> **Why tkinter, not pygame:** this machine runs **Python 3.14**, which has **no
> pygame wheel** — `pip install pygame` fails (source build). **tkinter is in the
> Python standard library**, so there is **nothing to install**, it works offline,
> and it still gives a real graphical window with keyboard controls. Do **not** use
> or `pip install` pygame.

## How to run this in AXIO Code mode — LOCAL ONLY (gemma4:12b)

```powershell
cd "C:\Users\AXIO\AXIO Model Improvement\axio-console-v2.1"
$env:LOCAL_ONLY = "1"
py axio.py code
```

Then **type this task** (the wording matters — it makes the harness give the agent
**50 steps** instead of 10, and loads this spec):

```
load workspaces\tetris\TETRIS_BUILD.md
```
```
Implement this Tetris spec end-to-end and completely: write the file, run the self-test, and iterate until SELFTEST OK.
```

> The phrase *end-to-end / completely* classifies the task as **complex → 50 steps**
> ([step budget: simple 10 · normal 20 · complex 50]). A short command like
> "execute file" gets only 10 steps and stops early — that's what happened before.
>
> You'll **approve** the compile/self-test commands (normal `execute`-risk gate).
> `gemma4:12b` may take several gate-driven passes — that's expected; type
> `continue` or `fix the failing selftest` if it pauses. The `verification_gate`
> won't let it finish until the compile **and** the headless self-test pass.

---

## Objective

One file: `workspaces/tetris/tetris.py` (absolute path
`C:\Users\AXIO\AXIO Model Improvement\axio-console-v2.1\workspaces\tetris\tetris.py`).
Run `py tetris.py` → a Tetris window opens and is playable. Standard library only
(`tkinter`, `random`, `sys`, `os`). No third-party packages.

## Architecture (keep game logic separate from the GUI — critical for the self-test)

Put **all game logic as plain module-level functions/classes that DO NOT import or
create any tkinter objects.** Import tkinter and build the window **only inside the
GUI class / `main()`**. This lets `--selftest` verify the logic with no window.

- **Constants:** `COLS=10`, `ROWS=20`, `CELL=30`.
- **`SHAPES`**: the 7 tetrominoes (I, O, T, S, Z, J, L) as small matrices of 0/1,
  each with a distinct color (I=cyan, O=yellow, T=purple, S=green, Z=red, J=blue,
  L=orange).
- **Pure functions (no tkinter):**
  - `new_grid()` → ROWS×COLS grid of `None`.
  - `rotate(shape)` → shape rotated 90° clockwise (`[list(r) for r in zip(*shape[::-1])]`).
  - `collides(grid, shape, x, y)` → True if any filled cell is out of bounds or
    overlaps a filled grid cell.
  - `lock(grid, shape, x, y, color)` → write the piece's cells into the grid.
  - `clear_lines(grid)` → remove full rows, shift down, return `(new_grid, count)`.
  - `score_for(lines, level)` → `{0:0,1:100,2:300,3:500,4:800}[lines] * level`.
- **GUI class (tkinter):** a `Canvas` (COLS*CELL × ROWS*CELL) plus a side panel for
  **score / level / lines** and a **next-piece preview**. Gravity via
  `root.after(interval_ms, tick)`; `interval_ms` shrinks as level rises. Redraw each
  tick and after each input.

## Gameplay requirements (acceptance)

- 7 pieces spawn **randomly** at top center; keep a **next piece** and show its preview.
- Move L/R; **soft drop** (Down); **hard drop** (Space) that drops to the bottom and
  locks (back off one row after the first collision so it doesn't lock inside the stack).
- **Rotate clockwise** (Up). *Counter-clockwise and wall kicks are optional.*
- Lock on landing → clear full lines → add `score_for(n, level)` → `lines += n` →
  **level = 1 + lines // 10**; recompute gravity speed from level.
- **Game over** when a freshly spawned piece already collides → show a "Game Over —
  press R to restart" overlay; **R** restarts, **P** pauses/resumes, **Esc**/close quits.
- ~30–60 FPS feel; no unhandled exceptions.

## Controls (implement exactly; show them on the game-over overlay)

| Key   | Action        |  | Key | Action              |
|-------|---------------|--|-----|---------------------|
| ← / → | Move          |  | P   | Pause / resume      |
| ↓     | Soft drop     |  | R   | Restart (game over) |
| ↑     | Rotate CW     |  | Esc | Quit                |
| Space | Hard drop     |  |     |                     |

## REQUIRED headless self-test (this is how you verify — never open the window yourself)

Add a `--selftest` path that runs the **pure logic only** and **creates no Tk
window**. At the very top of the file:

```python
import sys, os
if "--selftest" in sys.argv:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")  # harmless; we don't touch Tk in selftest
```

`--selftest` must run these asserts, print `SELFTEST OK`, and `sys.exit(0)`:
1. For every shape, `rotate` applied 4× returns the original shape.
2. `collides` is True for an out-of-bounds x and for overlap on a filled cell; False for a valid empty placement.
3. A grid with a full bottom row → `clear_lines` returns count `1` and shifts rows down (top row becomes empty).
4. `score_for(1..4, 2)` == `200, 600, 1000, 1600` (i.e. 100/300/500/800 × level 2).
5. Spawning a piece onto an occupied top row → `collides` True (game-over condition).

Keep `import tkinter` **out** of the self-test path (import it inside the GUI class
or `main()` so `--selftest` never needs a display).

## Build procedure — do these in order with your tools

1. `inspect_python_environment` on the workspace dir; also confirm tkinter:
   `run_command: py -c "import tkinter; print('tk ok')"` (should print `tk ok`). **No pip installs.**
2. `write_file` the full `tetris.py` at the absolute path above. **Quote paths with spaces.**
3. `run_command: py -m py_compile "C:\Users\AXIO\AXIO Model Improvement\axio-console-v2.1\workspaces\tetris\tetris.py"` → must exit 0.
4. `run_command: py "C:\Users\AXIO\AXIO Model Improvement\axio-console-v2.1\workspaces\tetris\tetris.py" --selftest` → output must contain `SELFTEST OK`, exit 0. If it fails, read the traceback, `edit_file`/`write_file` to fix, and re-run this step.
5. Call **`verification_gate`**.
6. **Do NOT run `py tetris.py` without `--selftest`** — that opens the window and
   blocks the console (you can't see it). Finish by reporting the run command.

## Definition of done (self-check before TASK_COMPLETE)

- [ ] Standard-library only; **no pygame, no pip installs**.
- [ ] `py -m py_compile tetris.py` exits 0.
- [ ] `py tetris.py --selftest` prints `SELFTEST OK` and exits 0.
- [ ] 7 random pieces + next-piece preview; move / soft drop / hard drop / rotate CW.
- [ ] Line clears with 100/300/500/800 × level; `level = 1 + lines//10`; speed scales.
- [ ] HUD (score/level/lines); pause; game over + R restart; Esc/close quit.
- [ ] `verification_gate` passed; you did NOT launch the GUI yourself.

## How the user runs it (put this in your final message)

```powershell
cd "C:\Users\AXIO\AXIO Model Improvement\axio-console-v2.1\workspaces\tetris"
py tetris.py
```
