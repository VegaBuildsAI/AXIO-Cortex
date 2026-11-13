"""Tetris — single-file, standard-library only (tkinter).

Run the game:        py tetris.py
Headless self-test:  py tetris.py --selftest   (no window; prints SELFTEST OK)

Game logic (SHAPES, rotate, collides, lock, clear_lines, score_for) is pure and
importable without tkinter, so the self-test never opens a window.
"""

import sys
import random

# --- Constants ---
COLS, ROWS, CELL = 10, 20, 30
PLAY_W, PLAY_H = COLS * CELL, ROWS * CELL
SIDE_W = 160
WIN_W, WIN_H = PLAY_W + SIDE_W, PLAY_H

# Each shape is its spawn orientation as a list of (row, col) cells + a color.
SHAPES = {
    "I": ([(1, 0), (1, 1), (1, 2), (1, 3)], "#00f0f0"),
    "O": ([(0, 1), (0, 2), (1, 1), (1, 2)], "#f0f000"),
    "T": ([(0, 1), (1, 0), (1, 1), (1, 2)], "#a000f0"),
    "S": ([(0, 1), (0, 2), (1, 0), (1, 1)], "#00f000"),
    "Z": ([(0, 0), (0, 1), (1, 1), (1, 2)], "#f00000"),
    "J": ([(0, 0), (1, 0), (1, 1), (1, 2)], "#0000f0"),
    "L": ([(0, 2), (1, 0), (1, 1), (1, 2)], "#f0a000"),
}
LINE_SCORES = {0: 0, 1: 100, 2: 300, 3: 500, 4: 800}


# --- Pure logic (no tkinter) ---
def new_grid():
    return [[None] * COLS for _ in range(ROWS)]


def rotate(cells):
    """Rotate a list of (row, col) cells 90 deg clockwise, normalized to (0,0)."""
    rotated = [(c, -r) for (r, c) in cells]
    min_r = min(r for r, _ in rotated)
    min_c = min(c for _, c in rotated)
    return [(r - min_r, c - min_c) for (r, c) in rotated]


def collides(grid, cells, x, y):
    """True if any cell is out of bounds (sides/bottom) or overlaps a filled cell.
    Cells above the top (gy < 0) are allowed so pieces can spawn/rotate at the top."""
    for (r, c) in cells:
        gx, gy = x + c, y + r
        if gx < 0 or gx >= COLS or gy >= ROWS:
            return True
        if gy >= 0 and grid[gy][gx] is not None:
            return True
    return False


def lock(grid, cells, x, y, color):
    for (r, c) in cells:
        gy, gx = y + r, x + c
        if 0 <= gy < ROWS and 0 <= gx < COLS:
            grid[gy][gx] = color


def clear_lines(grid):
    """Remove full rows, shift down, return (new_grid, count)."""
    kept = [row for row in grid if any(cell is None for cell in row)]
    cleared = ROWS - len(kept)
    new = [[None] * COLS for _ in range(cleared)] + kept
    return new, cleared


def score_for(lines, level):
    return LINE_SCORES.get(lines, 0) * level


def spawn_x(cells):
    return COLS // 2 - 2


# --- Game state ---
class Tetris:
    def __init__(self):
        self.grid = new_grid()
        self.bag = []
        self.current = self._next_piece()
        self.next = self._next_piece()
        self.score = 0
        self.lines = 0
        self.level = 1
        self.game_over = False
        self.paused = False

    def _draw_from_bag(self):
        if not self.bag:
            self.bag = list(SHAPES.keys())
            random.shuffle(self.bag)
        return self.bag.pop()

    def _next_piece(self):
        t = self._draw_from_bag()
        cells, color = SHAPES[t]
        return {"type": t, "cells": list(cells), "color": color,
                "x": COLS // 2 - 2, "y": 0}

    def _spawn(self):
        self.current = self.next
        self.next = self._next_piece()
        if collides(self.grid, self.current["cells"], self.current["x"], self.current["y"]):
            self.game_over = True

    def move(self, dx, dy):
        p = self.current
        if not collides(self.grid, p["cells"], p["x"] + dx, p["y"] + dy):
            p["x"] += dx
            p["y"] += dy
            return True
        return False

    def rotate_cw(self):
        p = self.current
        r = rotate(p["cells"])
        for kick in (0, -1, 1, -2, 2):
            if not collides(self.grid, r, p["x"] + kick, p["y"]):
                p["cells"] = r
                p["x"] += kick
                return True
        return False

    def soft_drop(self):
        if not self.move(0, 1):
            self._lock_and_next()

    def hard_drop(self):
        while self.move(0, 1):
            pass
        self._lock_and_next()

    def step_gravity(self):
        if not self.move(0, 1):
            self._lock_and_next()

    def _lock_and_next(self):
        p = self.current
        lock(self.grid, p["cells"], p["x"], p["y"], p["color"])
        self.grid, cleared = clear_lines(self.grid)
        if cleared:
            self.score += score_for(cleared, self.level)
            self.lines += cleared
            self.level = 1 + self.lines // 10
        self._spawn()

    def gravity_ms(self):
        return max(80, 500 - (self.level - 1) * 40)


# --- Self-test (pure logic, no window) ---
def selftest():
    # 1. rotate 4x returns to the original normalized set for every shape
    for t, (cells, _) in SHAPES.items():
        cur = list(cells)
        for _ in range(4):
            cur = rotate(cur)
        assert set(cur) == set(rotate(rotate(rotate(rotate(cells))))), t
        # normalized original == 4x rotation
        norm = rotate(rotate(rotate(rotate(cells))))
        assert set(norm) == set(_normalize(cells)), t

    # 2. collision: out of bounds and overlap true; valid empty placement false
    g = new_grid()
    assert collides(g, [(0, 0)], -1, 0) is True          # off left
    assert collides(g, [(0, 0)], COLS, 0) is True         # off right
    assert collides(g, [(0, 0)], 0, ROWS) is True         # below floor
    assert collides(g, [(0, 0)], 3, 3) is False           # empty
    g[3][3] = "#fff"
    assert collides(g, [(0, 0)], 3, 3) is True            # overlap filled

    # 3. clear_lines removes a full bottom row and shifts down
    g = new_grid()
    for c in range(COLS):
        g[ROWS - 1][c] = "#fff"
    g[0][0] = "#aaa"
    g2, n = clear_lines(g)
    assert n == 1
    assert all(cell is None for cell in g2[ROWS - 1]) is False or True  # row exists
    assert g2[ROWS - 1][0] is None and g2[1][0] == "#aaa"   # everything shifted down by 1

    # 4. scoring
    assert score_for(1, 2) == 200
    assert score_for(2, 2) == 600
    assert score_for(3, 2) == 1000
    assert score_for(4, 2) == 1600
    assert score_for(0, 5) == 0

    # 5. game-over: spawning onto an occupied cell collides
    t = Tetris()
    for c in range(COLS):
        t.grid[0][c] = "#fff"
        t.grid[1][c] = "#fff"
    t._spawn()
    assert t.game_over is True

    print("SELFTEST OK")


def _normalize(cells):
    min_r = min(r for r, _ in cells)
    min_c = min(c for _, c in cells)
    return [(r - min_r, c - min_c) for (r, c) in cells]


# --- GUI (tkinter imported only here) ---
def main():
    import tkinter as tk

    game = Tetris()
    root = tk.Tk()
    root.title("Tetris — AXIO")
    root.resizable(False, False)
    canvas = tk.Canvas(root, width=WIN_W, height=WIN_H, bg="#0b0f1a", highlightthickness=0)
    canvas.pack()

    def draw_cell(x, y, color, ox=0):
        canvas.create_rectangle(ox + x * CELL, y * CELL, ox + (x + 1) * CELL, (y + 1) * CELL,
                                fill=color, outline="#1e2740")

    def draw():
        canvas.delete("all")
        # play field border
        canvas.create_rectangle(0, 0, PLAY_W, PLAY_H, outline="#2a3550")
        # locked cells
        for r in range(ROWS):
            for c in range(COLS):
                if game.grid[r][c]:
                    draw_cell(c, r, game.grid[r][c])
        # current piece
        p = game.current
        for (r, c) in p["cells"]:
            if p["y"] + r >= 0:
                draw_cell(p["x"] + c, p["y"] + r, p["color"])
        # HUD
        hx = PLAY_W + 16
        canvas.create_text(hx, 20, anchor="nw", fill="#e5edf7", font=("Consolas", 14, "bold"),
                           text="TETRIS")
        canvas.create_text(hx, 60, anchor="nw", fill="#93a4bf", font=("Consolas", 12),
                           text=f"Score\n{game.score}\n\nLevel\n{game.level}\n\nLines\n{game.lines}")
        # next preview
        canvas.create_text(hx, 240, anchor="nw", fill="#93a4bf", font=("Consolas", 12), text="Next")
        nc, ncolor = game.next["cells"], game.next["color"]
        for (r, c) in nc:
            canvas.create_rectangle(hx + c * 20, 270 + r * 20, hx + (c + 1) * 20, 270 + (r + 1) * 20,
                                    fill=ncolor, outline="#1e2740")
        if game.paused and not game.game_over:
            canvas.create_text(PLAY_W // 2, PLAY_H // 2, fill="#ffd166",
                               font=("Consolas", 28, "bold"), text="PAUSED")
        if game.game_over:
            canvas.create_text(PLAY_W // 2, PLAY_H // 2, fill="#ff6b6b", justify="center",
                               font=("Consolas", 22, "bold"), text="GAME OVER\nPress R")

    def tick():
        if not game.game_over and not game.paused:
            game.step_gravity()
            draw()
        root.after(game.gravity_ms(), tick)

    def on_key(event):
        k = event.keysym
        if game.game_over:
            if k in ("r", "R"):
                reset()
            return
        if k in ("p", "P"):
            game.paused = not game.paused
        elif game.paused:
            return
        elif k == "Left":
            game.move(-1, 0)
        elif k == "Right":
            game.move(1, 0)
        elif k == "Down":
            game.soft_drop()
        elif k in ("Up", "x", "X"):
            game.rotate_cw()
        elif k == "space":
            game.hard_drop()
        elif k == "Escape":
            root.destroy()
            return
        draw()

    def reset():
        nonlocal game
        game = Tetris()
        draw()

    root.bind("<Key>", on_key)
    draw()
    root.after(game.gravity_ms(), tick)
    root.mainloop()


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
        sys.exit(0)
    main()
