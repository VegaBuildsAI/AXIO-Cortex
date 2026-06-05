"""
Generates AXIO_IOAF_Manifesto_v2.1.docx from the manifesto content.
Run: py build_manifesto.py
"""
from docx import Document
from docx.shared import Pt, RGBColor, Inches, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import copy

# ── Colour palette ────────────────────────────────────────────────────────────
BLACK      = RGBColor(0x0D, 0x0D, 0x0D)
DARK_NAVY  = RGBColor(0x0F, 0x34, 0x60)
MID_NAVY   = RGBColor(0x16, 0x21, 0x3E)
ACCENT     = RGBColor(0xE9, 0x45, 0x60)   # AXIO red
RULE_GREY  = RGBColor(0xCC, 0xCC, 0xCC)
BODY_GREY  = RGBColor(0x2B, 0x2B, 0x2B)
TABLE_HEAD = RGBColor(0x0F, 0x34, 0x60)
TABLE_ALT  = RGBColor(0xF4, 0xF7, 0xFB)
TABLE_HEAD_HEX = "0F3460"
TABLE_ALT_HEX  = "F4F7FB"
WHITE      = RGBColor(0xFF, 0xFF, 0xFF)

doc = Document()

# ── Page margins ──────────────────────────────────────────────────────────────
for section in doc.sections:
    section.top_margin    = Inches(1.0)
    section.bottom_margin = Inches(1.0)
    section.left_margin   = Inches(1.25)
    section.right_margin  = Inches(1.25)


# ── Helper functions ──────────────────────────────────────────────────────────

def set_font(run, name="Calibri", size=11, bold=False, italic=False, color=None):
    run.font.name  = name
    run.font.size  = Pt(size)
    run.font.bold  = bold
    run.font.italic = italic
    if color:
        run.font.color.rgb = color


def add_para(text="", style="Normal", space_before=0, space_after=6,
             align=WD_ALIGN_PARAGRAPH.LEFT):
    p = doc.add_paragraph(style=style)
    p.paragraph_format.space_before = Pt(space_before)
    p.paragraph_format.space_after  = Pt(space_after)
    p.alignment = align
    if text:
        r = p.add_run(text)
        set_font(r, color=BODY_GREY)
    return p


def add_heading(text, level=1):
    """Custom styled heading."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(18 if level == 1 else 12)
    p.paragraph_format.space_after  = Pt(6)
    r = p.add_run(text)
    if level == 1:
        set_font(r, name="Calibri", size=18, bold=True, color=DARK_NAVY)
    elif level == 2:
        set_font(r, name="Calibri", size=13, bold=True, color=ACCENT)
    elif level == 3:
        set_font(r, name="Calibri", size=11, bold=True, italic=True, color=DARK_NAVY)
    return p


def add_rule():
    """Thin horizontal rule."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after  = Pt(2)
    pPr = p._p.get_or_add_pPr()
    pBdr = OxmlElement('w:pBdr')
    bottom = OxmlElement('w:bottom')
    bottom.set(qn('w:val'), 'single')
    bottom.set(qn('w:sz'), '6')
    bottom.set(qn('w:space'), '1')
    bottom.set(qn('w:color'), 'CCCCCC')
    pBdr.append(bottom)
    pPr.append(pBdr)
    return p


def add_body(text, space_before=0, space_after=8):
    p = add_para(space_before=space_before, space_after=space_after)
    r = p.add_run(text)
    set_font(r, size=11, color=BODY_GREY)
    return p


def add_body_mixed(parts, space_before=0, space_after=8):
    """parts = list of (text, bold) tuples."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(space_before)
    p.paragraph_format.space_after  = Pt(space_after)
    for text, bold in parts:
        r = p.add_run(text)
        set_font(r, size=11, bold=bold, color=BODY_GREY)
    return p


def add_quote(text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after  = Pt(10)
    p.paragraph_format.left_indent  = Inches(0.5)
    r = p.add_run(text)
    set_font(r, size=11, italic=True, color=RGBColor(0x55, 0x55, 0x55))
    return p


def add_bullet(text, bold_prefix=None):
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after  = Pt(3)
    p.paragraph_format.left_indent  = Inches(0.25)
    if bold_prefix:
        r1 = p.add_run(bold_prefix + " ")
        set_font(r1, size=11, bold=True, color=DARK_NAVY)
        r2 = p.add_run(text)
        set_font(r2, size=11, color=BODY_GREY)
    else:
        r = p.add_run(text)
        set_font(r, size=11, color=BODY_GREY)
    return p


def add_table(headers, rows, col_widths=None):
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = "Table Grid"

    # Header row
    hdr_row = table.rows[0]
    for i, h in enumerate(headers):
        cell = hdr_row.cells[i]
        cell.text = ""
        r = cell.paragraphs[0].add_run(h)
        set_font(r, size=10, bold=True, color=WHITE)
        shading = OxmlElement("w:shd")
        shading.set(qn("w:val"), "clear")
        shading.set(qn("w:color"), "auto")
        shading.set(qn("w:fill"), TABLE_HEAD_HEX)
        cell._tc.get_or_add_tcPr().append(shading)
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Data rows
    for ri, row_data in enumerate(rows):
        row = table.rows[ri + 1]
        fill = "FFFFFF" if ri % 2 == 0 else TABLE_ALT_HEX
        for ci, cell_text in enumerate(row_data):
            cell = row.cells[ci]
            cell.text = ""
            r = cell.paragraphs[0].add_run(str(cell_text))
            set_font(r, size=10, color=BODY_GREY)
            shading = OxmlElement("w:shd")
            shading.set(qn("w:val"), "clear")
            shading.set(qn("w:color"), "auto")
            shading.set(qn("w:fill"), fill)
            cell._tc.get_or_add_tcPr().append(shading)

    # Column widths
    if col_widths:
        for i, w in enumerate(col_widths):
            for row in table.rows:
                row.cells[i].width = Inches(w)

    doc.add_paragraph()  # spacing after table
    return table


def add_link_line(label, url):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after  = Pt(4)
    p.paragraph_format.left_indent  = Inches(0.25)
    r1 = p.add_run(label + "  ")
    set_font(r1, size=10, bold=True, color=DARK_NAVY)
    r2 = p.add_run(url)
    set_font(r2, size=10, italic=True, color=RGBColor(0x1A, 0x73, 0xE8))


# ══════════════════════════════════════════════════════════════════════════════
# COVER
# ══════════════════════════════════════════════════════════════════════════════

p = doc.add_paragraph()
p.paragraph_format.space_before = Pt(48)
p.paragraph_format.space_after  = Pt(4)
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("THE AXIO MANIFESTO")
set_font(r, name="Calibri", size=32, bold=True, color=DARK_NAVY)

p2 = doc.add_paragraph()
p2.paragraph_format.space_after = Pt(4)
p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
r2 = p2.add_run("Intelligent Orchestrated Agent Framework")
set_font(r2, name="Calibri", size=16, italic=True, color=ACCENT)

p3 = doc.add_paragraph()
p3.paragraph_format.space_after = Pt(2)
p3.alignment = WD_ALIGN_PARAGRAPH.CENTER
r3 = p3.add_run("IOAF v2.1 — Final Debugged Release 1")
set_font(r3, size=12, color=RGBColor(0x55, 0x55, 0x55))

add_rule()

meta = doc.add_paragraph()
meta.paragraph_format.space_before = Pt(8)
meta.paragraph_format.space_after  = Pt(2)
meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
r_m = meta.add_run("Michael Vega  ·  msvv11@gmail.com  ·  May 9, 2026")
set_font(r_m, size=10, color=RGBColor(0x77, 0x77, 0x77))

doc.add_page_break()


# ══════════════════════════════════════════════════════════════════════════════
# I. THE PROBLEM
# ══════════════════════════════════════════════════════════════════════════════

add_heading("I. The Problem with AI Today", level=1)
add_rule()

add_body(
    "Every session with an AI tool begins the same way: from nothing.",
    space_before=10, space_after=8
)
add_body(
    "You open a chat window. You explain who you are. You describe what you are working on. "
    "You provide context the tool should already know. You ask your question. You get an answer. "
    "You close the window.",
    space_after=8
)
add_body(
    "Tomorrow, you open a new window. You start from nothing again.",
    space_after=8
)
add_body(
    "This is the fundamental flaw of the current generation of AI tools. They are stateless. "
    "They are amnesiac. They treat every session as if it is the first time you have ever spoken. "
    "They consume your time not just answering questions, but re-learning what they should already "
    "know about you.",
    space_after=8
)
add_body(
    "This is not intelligence. This is an expensive autocomplete that forgets you the moment you leave.",
    space_after=12
)


# ══════════════════════════════════════════════════════════════════════════════
# II. THE THESIS
# ══════════════════════════════════════════════════════════════════════════════

add_heading("II. The AXIO Thesis", level=1)
add_rule()

add_body(
    "AI should get smarter the longer you use it — not reset to zero every session.",
    space_before=10, space_after=10
)
add_body(
    "Every conversation you have contains signal. Signal about your projects, your preferences, "
    "your domain vocabulary, your open questions, your decision history. Today that signal "
    "evaporates. AXIO captures it.",
    space_after=8
)

add_body(
    "AXIO is a local-first, multi-model AI orchestration platform built on a single architectural "
    "conviction: AI sessions should be stateful, cumulative, and sovereign.",
    space_after=10
)

add_bullet(
    "the system remembers. Not just the last conversation — all of them, semantically indexed and retrievable.",
    bold_prefix="Stateful:"
)
add_bullet(
    "every session adds to a growing knowledge base. The longer you use AXIO, the better it understands your work.",
    bold_prefix="Cumulative:"
)
add_bullet(
    "your data never leaves your machine unless you choose. No cloud dependency for memory. "
    "No vendor lock-in. No subscription required to keep your own history.",
    bold_prefix="Sovereign:"
)

doc.add_paragraph()


# ══════════════════════════════════════════════════════════════════════════════
# III. IOAF — THE MEMORY ARCHITECTURE
# ══════════════════════════════════════════════════════════════════════════════

add_heading("III. IOAF — The Memory Architecture", level=1)
add_rule()

add_body(
    "The intellectual core of AXIO is the Intelligent Orchestrated Agent Framework (IOAF) — "
    "a three-tier memory system that transforms stateless model calls into a continuously "
    "learning personal AI workspace.",
    space_before=10, space_after=12
)

add_heading("Tier 1 — The Record", level=2)
add_quote("What was said.")
add_body(
    "Every session is saved verbatim as timestamped JSON at ~/.axio/sessions/. This is the ground "
    "truth — a permanent, human-readable archive of every exchange. It requires no external "
    "dependencies. It is always written. It is the foundation on which the higher tiers are built.",
    space_after=10
)

add_heading("Tier 2 — The Understanding", level=2)
add_quote("What it meant.")
add_body(
    "At the end of every session, a language model reads the full conversation and writes a summary "
    "— not a transcript, but an interpretation. What were you working on? What decisions were made? "
    "What remained open? That summary is converted into a 768-dimensional vector by a local embedding "
    "model (nomic-embed-text) and stored in a ChromaDB vector database at ~/.axio/chroma/.",
    space_after=8
)
add_body(
    "When you begin your next session, AXIO embeds your first prompt and searches that vector store. "
    "The five most semantically similar past sessions surface automatically. Their summaries are "
    "injected into the system prompt before the first model call. The model already knows your "
    "context before you say a word.",
    space_after=8
)
add_body(
    "This is not keyword search. It is semantic memory — recall by meaning, not by string match.",
    space_after=10
)

add_heading("Tier 3 — The Facts", level=2)
add_quote("What you need it to know.")
add_body(
    "Running in parallel to both tiers above is a lightweight structured facts store at "
    "~/.axio/memory/. Every user message is scanned for extractable facts: your name, your active "
    "projects, your clients, your preferred frameworks, your workspace paths. These facts are stored "
    "as simple key-value JSON and loaded at the start of every session — instantly, with no Ollama "
    "dependency.",
    space_after=8
)
add_body(
    "Tier 3 is the fastest path to personalization. It is also the most resilient — it works "
    "even when the embedding model is unavailable.",
    space_after=10
)

add_heading("The Master Record", level=3)
add_body(
    "All four operational modes feed a single cross-mode knowledge base: console_memory.json. "
    "A conversation in RevRec about a SaaS contract can inform a follow-up session in Code about "
    "implementing the billing logic. The modes are separate workspaces. The memory is one.",
    space_after=12
)


# ══════════════════════════════════════════════════════════════════════════════
# IV. ROUTING
# ══════════════════════════════════════════════════════════════════════════════

add_heading("IV. Intelligent Routing — The Right Model for the Right Task", level=1)
add_rule()

add_body(
    "Not every question deserves the same model. Not every model deserves every question.",
    space_before=10, space_after=8
)
add_body(
    "Large cloud models are powerful but expensive and latency-bound. Small local models are fast "
    "and free but have limits. The right architecture matches the task to the tool.",
    space_after=10
)

add_table(
    headers=["Task Type", "Route", "Model", "Reason"],
    rows=[
        ["Arithmetic",        "math",              "Python interpreter",  "Exact, instant, deterministic. 100/100 every time."],
        ["Code generation",   "coding_agent",      "qwen3-coder:30b",     "Scored 92/100 on coding benchmarks."],
        ["Revenue analysis",  "revenue_analysis",  "qwen3:14b",           "Scored 85/100 on ASC 606 tasks."],
        ["General chat",      "quick_chat",        "qwen3:8b",            "Fast, low cost, 92/100 on coding."],
        ["Complex reasoning", "premium_reasoning", "Claude Sonnet 4.6",   "When only the best will do."],
    ],
    col_widths=[1.3, 1.4, 1.5, 2.6]
)

add_body(
    "Every route has a fallback chain. If the primary model fails, times out, or is unavailable, "
    "the next model in the chain takes over — automatically, without user intervention.",
    space_after=8
)
add_body(
    "This is cost-aware orchestration. You pay for Claude when you need Claude. You use local "
    "compute when local compute is sufficient. The router decides.",
    space_after=12
)

add_heading("The Math Principle", level=3)
add_body(
    "Every language model in AXIO's fleet — including the strongest — timed out or failed when "
    "asked to compute eight-digit multiplication in-context. Not because they are weak. Because "
    "computing arithmetic token-by-token in an 8,192-token window is the wrong tool for the job.",
    space_after=8
)
add_body(
    "AXIO routes all arithmetic to a Python interpreter before any model call. Zero latency. "
    "Zero tokens consumed. Score: 100. This is the broader principle: use the right instrument, "
    "not the most impressive one.",
    space_after=12
)


# ══════════════════════════════════════════════════════════════════════════════
# V. FOUR MODES
# ══════════════════════════════════════════════════════════════════════════════

add_heading("V. Four Modes — One Platform", level=1)
add_rule()

add_body(
    "AXIO presents four specialist operational modes, each with its own model assignment, toolset, "
    "and memory namespace. They share one runtime, one memory system, and one routing engine.",
    space_before=10, space_after=12
)

add_heading("Chat — For thinking out loud.", level=2)
add_body(
    "Fast general-purpose conversation powered by Claude Haiku or Mistral locally. The cheapest "
    "compute tier — appropriate for the most common task type. Full session memory. Math intercepted "
    "before model. Designed for speed.",
    space_after=10
)

add_heading("Code — For building things.", level=2)
add_body(
    "An autonomous agentic coding loop. The model does not just answer — it reads files, writes "
    "files, edits code, searches directories, and executes PowerShell. Claude Sonnet is the primary "
    "model; qwen3-coder:30b handles local sessions. Once Claude is selected within a session, the "
    "session stays on Claude — the sticky flag prevents mid-conversation model drift that degrades "
    "coherence.",
    space_after=10
)

add_heading("Cowork — For working alongside your files.", level=2)
add_body(
    "A workspace-aware assistant that indexes your project tree and routes each prompt to the best "
    "available model. Reference any file in context with @filename. The router decides on every "
    "turn whether the task warrants a fast local model or escalation to Claude.",
    space_after=10
)

add_heading("RevRec — For revenue recognition.", level=2)
add_body(
    "A specialist ASC 606 / IFRS 15 domain agent with 17 tools: contract analysis, performance "
    "obligation identification, transaction price determination, allocation schedules, deferred "
    "revenue models, variable consideration analysis, contract modification analysis, and written "
    "memo generation — all output to Excel. The same Claude call structure as Code mode. The same "
    "file tools. The same memory system. The domain is narrow; the capability is deep.",
    space_after=8
)
add_body(
    "Launch command:  py axio.py --claude revrec",
    space_after=12
)


# ══════════════════════════════════════════════════════════════════════════════
# VI. SOVEREIGNTY
# ══════════════════════════════════════════════════════════════════════════════

add_heading("VI. Sovereignty by Design", level=1)
add_rule()

add_body(
    "AXIO is built on an explicit stance: your AI memory belongs to you.",
    space_before=10, space_after=8
)
add_body(
    "Every piece of data AXIO generates — sessions, embeddings, facts, summaries, audit logs — "
    "lives in ~/.axio/ on your local machine. No API call persists your history to a third-party "
    "server. No subscription controls access to your own past sessions. No vendor can revoke your "
    "memory.",
    space_after=8
)
add_body(
    "The Anthropic Claude API is an optional escalation tier, used only when you request it or "
    "when the router determines the task requires it. It is not the backbone of the system. It is "
    "a capability tier within a larger architecture that runs without it.",
    space_after=8
)
add_body(
    "This is not an anti-cloud position. It is a pro-sovereignty position. Cloud compute is "
    "valuable. Cloud data custody is a risk. AXIO separates the two.",
    space_after=12
)


# ══════════════════════════════════════════════════════════════════════════════
# VII. ASSESSMENT ENGINE
# ══════════════════════════════════════════════════════════════════════════════

add_heading("VII. The Assessment Engine — Knowing What You Have", level=1)
add_rule()

add_body(
    "You cannot optimize what you cannot measure.",
    space_before=10, space_after=10
)
add_body(
    "AXIO includes a first-class benchmark and assessment system. Run py axio.py benchmark and "
    "the platform executes four standardized tasks against every configured model:",
    space_after=8
)

add_table(
    headers=["ID", "Task Type", "Scorer", "What It Measures"],
    rows=[
        ["MATH-001",    "Exact arithmetic",         "python_exact (100 or 0)",  "84,736,291 × 69,384,725 — deterministic correctness"],
        ["CODING-001",  "Code generation",           "Rubric / LLM-as-judge",    "Flask REST API — structure, correctness, style"],
        ["REVREC-001",  "ASC 606 analysis",          "Rubric / LLM-as-judge",    "SaaS performance obligation decision tree"],
        ["ARCH-001",    "Architecture design",       "Rubric / LLM-as-judge",    "Microservices — design quality and tradeoffs"],
    ],
    col_widths=[0.9, 1.5, 1.6, 2.8]
)

add_body(
    "Results are scored by a rubric-based LLM-as-judge against domain-specific criteria — "
    "not vibes, not impressions, but structured rubrics with defined point allocations. "
    "Scores are logged to JSONL. Assessment snapshots are appended to engine/assessments.jsonl "
    "with full model-by-model breakdowns, latency data, and health flags for timeout errors.",
    space_after=8
)
add_body(
    "This means routing decisions are not opinions. They are data.",
    space_after=10
)

add_heading("Benchmark Results — ASSESS-006 (May 9, 2026)", level=3)
add_table(
    headers=["Model", "Coding", "Architecture", "Revenue", "Math", "Avg"],
    rows=[
        ["qwen3:14b",       "92", "—",  "85", "timeout", "~88"],
        ["qwen3:8b",        "92", "82", "72", "timeout", "~82"],
        ["qwen3-coder:30b", "92", "75", "72", "0",       "~73"],
        ["llama3.1:8b",     "72", "45", "35", "15",      "~42"],
        ["python_exact",    "—",  "—",  "—",  "100",     "—"],
    ],
    col_widths=[1.5, 0.8, 1.0, 0.8, 0.8, 0.8]
)

add_body(
    "When qwen3:14b scored 85/100 on revenue analysis and qwen3-coder:30b scored 72/100, "
    "the routing table was updated to match. When qwen3:8b and qwen3:14b both timed out on "
    "MATH-001, arithmetic was routed to the Python interpreter and the health flags cleared. "
    "The system learns from its own performance data. That is not a feature. That is the point.",
    space_after=12
)


# ══════════════════════════════════════════════════════════════════════════════
# VIII. WHAT THIS BUILDS TOWARD
# ══════════════════════════════════════════════════════════════════════════════

add_heading("VIII. What This Is Building Toward", level=1)
add_rule()

add_body(
    "AXIO v2.1 is a working, debugged, locally deployed platform. It is also a proof of concept "
    "for a larger idea.",
    space_before=10, space_after=8
)
add_body(
    "The Console Master Memory (console_memory.json) is a longitudinal record of every interaction "
    "across all modes. Every session adds to it. Over months, it becomes something more valuable "
    "than any individual conversation: a structured history of how a person thinks, what they "
    "build, what problems they return to, what they have already solved.",
    space_after=8
)
add_body(
    "That record has uses beyond session recall. It is the raw material for fine-tuning a model "
    "on your specific domain vocabulary and decision patterns. It is the foundation for a personal "
    "AI that is genuinely personal — not just prompted to act like it knows you, but trained on "
    "evidence that it does.",
    space_after=8
)
add_body(
    "The architecture is already in place. The data accumulation has already begun.",
    space_after=12
)


# ══════════════════════════════════════════════════════════════════════════════
# IX. DIAGRAMS
# ══════════════════════════════════════════════════════════════════════════════

add_heading("IX. Architecture Diagrams", level=1)
add_rule()

add_body(
    "Three FigJam diagrams document the live system as built:",
    space_before=10, space_after=8
)

add_link_line(
    "IOAF Model Routing & Fallback Architecture",
    "https://www.figma.com/board/NM2PhZHkCeRrhDF3cqnR0Y"
)
add_body(
    "How every prompt flows through the router to its model, with fallback chains at every branch.",
    space_after=8
)

add_link_line(
    "IOAF Three-Tier Memory System",
    "https://www.figma.com/board/iNJUG5sGf7YYCEJRV99IOv"
)
add_body(
    "How session data moves from raw conversation through summarization, embedding, and ChromaDB "
    "into semantic recall at the next session start.",
    space_after=8
)

add_link_line(
    "Four-Mode Platform Workflow",
    "https://www.figma.com/board/GTXZvCwuku1cf6UdBXDXvD"
)
add_body(
    "How Chat, Code, Cowork, and RevRec share the routing engine, memory system, and Claude "
    "escalation tier.",
    space_after=12
)

add_body(
    "These are not aspirational diagrams. They reflect the deployed codebase as of May 9, 2026.",
    space_after=12
)


# ══════════════════════════════════════════════════════════════════════════════
# X. PRINCIPLES
# ══════════════════════════════════════════════════════════════════════════════

add_heading("X. Principles", level=1)
add_rule()

add_body("", space_before=10)
add_bullet(
    "Run without the cloud. Escalate to it when it earns its cost.",
    bold_prefix="Local-first."
)
add_bullet(
    "Every session should make the next one better. Statefulness is not a feature — it is the purpose.",
    bold_prefix="Memory compounds."
)
add_bullet(
    "Cheap and fast is correct when it is sufficient. Expensive and powerful is correct when it is necessary. The router decides — on data, not assumption.",
    bold_prefix="Route to the right instrument."
)
add_bullet(
    "Routing decisions, benchmark scores, health flags, latency, and model drift — all logged, all queryable. Optimization follows observation.",
    bold_prefix="Measure everything."
)
add_bullet(
    "Your memory, your data, your machine. Cloud is a capability tier. It is not a dependency.",
    bold_prefix="Sovereignty is not optional."
)
add_bullet(
    "The value of AXIO is not in any single session. It is in the accumulation — the growing knowledge base that makes every session richer than the one before.",
    bold_prefix="Build for the long run."
)

doc.add_paragraph()
add_rule()

footer = doc.add_paragraph()
footer.paragraph_format.space_before = Pt(10)
footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
r_f = footer.add_run(
    "AXIO v2.1 — Final Debugged Release 1  ·  Built by Michael Vega  ·  msvv11@gmail.com  ·  May 9, 2026"
)
set_font(r_f, size=9, italic=True, color=RGBColor(0x88, 0x88, 0x88))


# ══════════════════════════════════════════════════════════════════════════════
# SAVE
# ══════════════════════════════════════════════════════════════════════════════

out_path = r"C:\Users\AXIO\AXIO Model Improvement\axio-console-v2.1\AXIO_IOAF_Manifesto_v2.1.docx"
doc.save(out_path)
print(f"Saved: {out_path}")
