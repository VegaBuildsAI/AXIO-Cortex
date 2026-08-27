# Generates AXIO-Architecture.svg — unified architecture export reconstructed from the 3 .jam files.
W = 1680
H = 2240
P = []  # svg fragments


def esc(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def box(x, y, w, h, lines, fill, stroke, tcol="#ffffff", rx=12, fs=15, sub_fs=12, bold0=True):
    P.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>')
    n = len(lines)
    lh = 18
    total = n * lh
    cy = y + h / 2 - total / 2 + 14
    for i, ln in enumerate(lines):
        weight = "700" if (i == 0 and bold0) else "400"
        size = fs if i == 0 else sub_fs
        op = "1" if i == 0 else "0.82"
        P.append(f'<text x="{x+w/2}" y="{cy+i*lh}" text-anchor="middle" font-family="Inter,Segoe UI,sans-serif" '
                 f'font-size="{size}" font-weight="{weight}" fill="{tcol}" opacity="{op}">{esc(ln)}</text>')


def diamond(cx, cy, w, h, lines, fill, stroke, tcol="#ffffff"):
    P.append(f'<polygon points="{cx},{cy-h/2} {cx+w/2},{cy} {cx},{cy+h/2} {cx-w/2},{cy}" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>')
    n = len(lines)
    lh = 16
    cyt = cy - (n * lh) / 2 + 12
    for i, ln in enumerate(lines):
        P.append(f'<text x="{cx}" y="{cyt+i*lh}" text-anchor="middle" font-family="Inter,sans-serif" '
                 f'font-size="{13 if i==0 else 11}" font-weight="{"700" if i==0 else "400"}" fill="{tcol}" opacity="{"1" if i==0 else "0.85"}">{esc(ln)}</text>')


def arrow(x1, y1, x2, y2, label=None, dash=False, col="#475569", lcol="#334155"):
    d = ' stroke-dasharray="6 5"' if dash else ''
    P.append(f'<path d="M{x1},{y1} L{x2},{y2}" fill="none" stroke="{col}" stroke-width="2"{d} marker-end="url(#ah)"/>')
    if label:
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        tw = len(label) * 6.2 + 12
        P.append(f'<rect x="{mx-tw/2}" y="{my-11}" width="{tw}" height="18" rx="9" fill="#ffffff" stroke="#e2e8f0"/>')
        P.append(f'<text x="{mx}" y="{my+2}" text-anchor="middle" font-family="Inter,sans-serif" font-size="11" font-weight="600" fill="{lcol}">{esc(label)}</text>')


def elbow(x1, y1, x2, y2, label=None, dash=False, col="#475569", midx=None):
    d = ' stroke-dasharray="6 5"' if dash else ''
    mx = midx if midx is not None else (x1 + x2) / 2
    P.append(f'<path d="M{x1},{y1} L{mx},{y1} L{mx},{y2} L{x2},{y2}" fill="none" stroke="{col}" stroke-width="2"{d} marker-end="url(#ah)"/>')
    if label:
        tw = len(label) * 6.2 + 12
        P.append(f'<rect x="{mx-tw/2}" y="{(y1+y2)/2-9}" width="{tw}" height="18" rx="9" fill="#fff" stroke="#e2e8f0"/>')
        P.append(f'<text x="{mx}" y="{(y1+y2)/2+3}" text-anchor="middle" font-family="Inter,sans-serif" font-size="11" font-weight="600" fill="#334155">{esc(label)}</text>')


def band(y, h, title, sub):
    P.append(f'<rect x="28" y="{y}" width="{W-56}" height="{h}" rx="18" fill="#ffffff" stroke="#e2e8f0" stroke-width="1.5"/>')
    P.append(f'<rect x="28" y="{y}" width="6" height="{h}" rx="3" fill="{sub}"/>')
    P.append(f'<text x="52" y="{y+34}" font-family="Inter,sans-serif" font-size="20" font-weight="800" fill="#0f172a">{esc(title)}</text>')


# palette
NAVY = "#1e293b"; NAVY_S = "#334155"
PURP = "#6d28d9"; PURP_S = "#5b21b6"
TEAL = "#0d9488"; TEAL_S = "#0f766e"
CRIM = "#dc2626"; CRIM_S = "#b91c1c"
INDIGO = "#4f46e5"; INDIGO_S = "#4338ca"
GREEN = "#15803d"; GREEN_S = "#166534"
AMBER = "#b45309"; AMBER_S = "#92400e"
SLATE = "#475569"

# ---------- header ----------
P.append(f'<rect x="0" y="0" width="{W}" height="{H}" fill="#f1f5f9"/>')
P.append(f'<text x="{W/2}" y="52" text-anchor="middle" font-family="Inter,sans-serif" font-size="30" font-weight="800" fill="#0f172a">AXIO Platform &#8212; IOAF Architecture</text>')
P.append(f'<text x="{W/2}" y="80" text-anchor="middle" font-family="Inter,sans-serif" font-size="14" fill="#64748b">v2.1 Continuous Resilient Cortex Memory &#183; Postgres-Cortex + gemma4:12b / Claude &#183; local-first multi-model orchestration</text>')

# =========================================================
# BAND 1 - Four-Mode Platform Workflow
# =========================================================
b1y = 104; b1h = 560
band(b1y, b1h, "1 - Four-Mode Platform Workflow", INDIGO)
box(70, b1y + 150, 150, 70, ["py axio.py", "Launcher"], NAVY, NAVY_S)
diamond(330, b1y + 185, 130, 92, ["--claude", "flag?"], NAVY, NAVY_S)
box(70, b1y + 300, 150, 70, ["FORCE_CLAUDE=1", "All prompts -> Claude"], INDIGO, INDIGO_S)
arrow(220, b1y + 185, 265, b1y + 185)
arrow(330, b1y + 231, 330, b1y + 300, "yes", dash=True)
elbow(330, b1y + 335, 480, b1y + 185, "no", midx=410)
modes = [
    ("Chat Mode", "modes/chat.py", "gemma4:12b local + web-augment / Claude Haiku", CRIM, CRIM_S),
    ("Code Mode", "modes/code.py", "Claude Sonnet 4.6 (Opus avail) - 42-tool harness", PURP, PURP_S),
    ("Cowork Mode", "modes/cowork.py", "gemma4:12b local + web-augment / Claude boost", TEAL, TEAL_S),
    ("RevRec Mode", "modes/revrec.py - rev_agent.py", "gemma4:12b / Claude - ASC 606 (isolated mem)", AMBER, AMBER_S),
]
mx = 500; mw = 330; mh = 92; gap = 20; my0 = b1y + 70
for i, (t, f, dd, c, s) in enumerate(modes):
    yy = my0 + i * (mh + gap)
    box(mx, yy, mw, mh, [t, f, dd], c, s)
for i in range(4):
    yy = my0 + i * (mh + gap) + mh / 2
    elbow(480, b1y + 185, mx, yy, midx=478, col=SLATE)
tx = 900
box(tx, b1y + 70, 250, 80, ["AXIO Cortex - MemoryManager", "core/memory.py", "chat/cowork/code shared; revrec isolated"], NAVY, NAVY_S, sub_fs=11)
tiers = [("Tier 3 - Facts (PG + JSON)", PURP, PURP_S), ("Tier 2 - pgvector + Chroma", TEAL, TEAL_S), ("Tier 1 - Sessions + journals", INDIGO, INDIGO_S)]
for i, (t, c, s) in enumerate(tiers):
    box(tx, b1y + 180 + i * 70, 250, 56, [t], c, s, fs=14)
for i in range(4):
    yy = my0 + i * (mh + gap) + mh / 2
    elbow(mx + mw, yy, tx, b1y + 110, midx=875, col=SLATE)
box(tx + 290, b1y + 250, 250, 90, ["Console Master Memory", "~/.axio/memory/", "console_memory.json", "cross-mode knowledge base"], GREEN, GREEN_S, fs=15, sub_fs=11)
for i in range(3):
    elbow(tx + 250, b1y + 208 + i * 70, tx + 290, b1y + 295, midx=1175, col=SLATE, dash=True)

# =========================================================
# BAND 2 - Three-Tier Memory System
# =========================================================
b2y = 690; b2h = 720
band(b2y, b2h, "2 - IOAF Three-Tier Memory System  (session lifecycle)", PURP)
rowy = b2y + 110
box(70, rowy, 150, 64, ["User Message"], NAVY, NAVY_S)
box(300, rowy, 175, 64, ["MemoryManager", "core/memory.py"], NAVY, NAVY_S)
box(560, rowy - 70, 230, 70, ["Tier 3 Read", "Facts: Postgres + JSON mirror", "console.global_profile injected"], PURP, PURP_S, sub_fs=11)
box(560, rowy + 70, 230, 70, ["Tier 2 Read", "pgvector cosine Top-N", "(Chroma / keyword fallback)"], TEAL, TEAL_S, sub_fs=11)
box(870, rowy, 200, 64, ["System Prompt", "Memory Prefix Injected"], INDIGO, INDIGO_S)
box(1150, rowy, 190, 64, ["Model Call", "gemma4:12b / Claude API"], CRIM, CRIM_S)
box(1420, rowy, 150, 64, ["Response"], GREEN, GREEN_S)
arrow(220, rowy + 32, 300, rowy + 32)
elbow(475, rowy + 32, 560, rowy - 35, midx=520, col=SLATE)
elbow(475, rowy + 32, 560, rowy + 105, midx=520, col=SLATE)
elbow(790, rowy - 35, 870, rowy + 32, midx=835, col=SLATE)
elbow(790, rowy + 105, 870, rowy + 32, midx=835, col=SLATE)
arrow(1070, rowy + 32, 1150, rowy + 32)
arrow(1340, rowy + 32, 1420, rowy + 32)
wy = b2y + 340
P.append(f'<text x="60" y="{wy-14}" font-family="Inter,sans-serif" font-size="14" font-weight="700" fill="#7c2d12">Persist before inference + on exit  -&gt;  all tiers (crash-safe)</text>')
box(70, wy, 150, 64, ["record / exit"], NAVY, NAVY_S)
box(300, wy, 200, 76, ["Tier 1 Write", "journals + Postgres", "~/.axio/journals + sessions"], INDIGO, INDIGO_S, sub_fs=11)
box(300, wy + 110, 230, 76, ["Tier 3 Write", "auto_update_facts()", "Postgres + JSON mirror"], PURP, PURP_S, sub_fs=11)
box(580, wy, 180, 70, ["gemma4:12b", "Summarize session"], CRIM, CRIM_S)
box(810, wy, 200, 70, ["nomic-embed-text", "Embed summary - 768-dim"], TEAL, TEAL_S, sub_fs=11)
box(1060, wy, 220, 76, ["Tier 2 Write", "pgvector + Chroma mirror", "durable outbox -> replay"], TEAL_S, "#134e4a", sub_fs=11)
arrow(220, wy + 32, 300, wy + 32)
elbow(220, wy + 32, 300, wy + 148, midx=260, col=SLATE)
arrow(500, wy + 35, 580, wy + 35)
arrow(760, wy + 35, 810, wy + 35)
arrow(1010, wy + 35, 1060, wy + 35)
ly = b2y + 580
for i, (t, c) in enumerate([("Tier 1 - Sessions + crash-safe journals", INDIGO), ("Tier 2 - pgvector primary + Chroma mirror", TEAL), ("Tier 3 - Structured facts + global_profile (always loaded)", PURP)]):
    P.append(f'<rect x="{80+i*500}" y="{ly}" width="16" height="16" rx="4" fill="{c}"/>')
    P.append(f'<text x="{102+i*500}" y="{ly+13}" font-family="Inter,sans-serif" font-size="12.5" fill="#334155">{esc(t)}</text>')

# =========================================================
# BAND 3 - Model Routing & Fallback
# =========================================================
b3y = 1436; b3h = 760
band(b3y, b3h, "3 - Model Routing & Fallback Architecture", CRIM)
box(70, b3y + 300, 150, 70, ["User Prompt"], NAVY, NAVY_S)
box(290, b3y + 296, 200, 78, ["core/router.py", "Keyword + Regex", "route detection"], NAVY, NAVY_S, sub_fs=11)
arrow(220, b3y + 335, 290, b3y + 335)
routes = [
    ("engine/math_tool.py", "python exact - score 100", GREEN, GREEN_S, "route = exact_math"),
    ("Claude Sonnet 4.6 / Opus", "Code - 42-tool agent", PURP, PURP_S, "route = coding_agent"),
    ("Claude Opus 4.8", "ASC 606 / Revenue", AMBER, AMBER_S, "route = revenue_analysis"),
    ("gemma4:12b", "Chat / Cowork / quick", TEAL, TEAL_S, "route = quick_chat"),
    ("Claude Opus 4.8", "Premium reasoning", INDIGO, INDIGO_S, "route = premium / FORCE_CLAUDE=1"),
]
rx0 = 620; rw = 300; rh = 72; rgap = 18; ry0 = b3y + 70
for i, (t, dd, c, s, lab) in enumerate(routes):
    yy = ry0 + i * (rh + rgap)
    box(rx0, yy, rw, rh, [t, dd], c, s)
    elbow(490, b3y + 335, rx0, yy + rh / 2, midx=560, col=SLATE)
    tw = len(lab) * 5.4 + 10
    P.append(f'<rect x="{560-tw/2}" y="{yy+rh/2-9}" width="{tw}" height="18" rx="9" fill="#fff" stroke="#e2e8f0"/>')
    P.append(f'<text x="560" y="{yy+rh/2+3}" text-anchor="middle" font-family="Inter,sans-serif" font-size="10" font-weight="600" fill="#334155">{esc(lab)}</text>')
box(1010, b3y + 300, 180, 76, ["Response", "to User"], NAVY, NAVY_S)
for i in range(5):
    yy = ry0 + i * (rh + rgap) + rh / 2
    elbow(rx0 + rw, yy, 1010, b3y + 338, midx=975, col=SLATE)
fy = ry0 + 5 * (rh + rgap) + 10
P.append(f'<text x="{rx0}" y="{fy+4}" font-family="Inter,sans-serif" font-size="13" font-weight="700" fill="#7c2d12">Fallback / escalation chain</text>')
fbs = [("LOCAL_ONLY=1 / no API key", "all routes -> gemma4:12b", CRIM, CRIM_S),
       ("Claude Sonnet <-> Opus", "in-app model + effort switch", INDIGO, INDIGO_S),
       ("Local fallback: gemma4:12b", "on Claude error / timeout", AMBER, AMBER_S)]
for i, (t, dd, c, s) in enumerate(fbs):
    box(rx0 + i * 330, fy + 14, 300, 66, [t, dd], c, s)

defs = ('<defs><marker id="ah" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="userSpaceOnUse">'
        '<path d="M0,0 L8,3 L0,6 Z" fill="#475569"/></marker></defs>')

svg = f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg">{defs}' + ''.join(P) + '</svg>'

import os
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _rel in ("diagrams/AXIO-Architecture.svg", "docs/AXIO-Architecture.svg"):
    _path = os.path.join(_root, _rel)
    os.makedirs(os.path.dirname(_path), exist_ok=True)
    with open(_path, "w", encoding="utf-8") as _f:
        _f.write(svg)
    print("wrote", _rel, len(svg), "bytes")
