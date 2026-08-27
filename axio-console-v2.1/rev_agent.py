"""
AXIO Revenue Recognition Agent v1.0
ASC 606 / IFRS 15 specialist agent — analysis, Excel models, automations.
Knowledge base: KPMG Revenue for Software and SaaS Handbook (Dec 2025)
Usage: py rev_agent.py
"""

import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from core.code_tools import build_default_registry, summarize_arguments
from core.code_tools.finance_tools import build_finance_tools
from core.code_tools.router import (
    DynamicToolRouter,
    LoopGuard,
    TrajectoryLogger,
    classify_complexity,
    process_history,
    step_budget,
    truncate_observation,
)

try:
    import requests
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "requests", "--quiet"])
    import requests

try:
    import anthropic as _anthropic
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "anthropic", "--quiet"])
    try:
        import anthropic as _anthropic
    except ImportError:
        _anthropic = None

try:
    import openpyxl
    from openpyxl.styles import (Font, PatternFill, Alignment, Border, Side,
                                  numbers)
    from openpyxl.utils import get_column_letter
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "openpyxl", "--quiet"])
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

try:
    import pdfplumber
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "pdfplumber", "--quiet",
                    "--break-system-packages"], capture_output=True)
    try:
        import pdfplumber
    except ImportError:
        pdfplumber = None

try:
    from pypdf import PdfReader as _PdfReader
except ImportError:
    try:
        from PyPDF2 import PdfReader as _PdfReader
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "pypdf", "--quiet",
                        "--break-system-packages"], capture_output=True)
        try:
            from pypdf import PdfReader as _PdfReader
        except ImportError:
            _PdfReader = None

# ---------------------------------------------------------------
# Config
# ---------------------------------------------------------------
BASE        = Path(__file__).resolve().parent
LOG_FILE    = BASE / "logs/rev_agent_audit.jsonl"
OUTPUT_DIR  = BASE / "workspaces/revenue-agent"
OLLAMA_URL     = "http://127.0.0.1:11434/api/chat"
AGENT_MODEL    = os.environ.get("MODEL_REASONING", "gemma4:12b")   # local base
FALLBACK_MODEL = os.environ.get("MODEL_FALLBACK", "gemma4:12b")    # light fallback
# Claude tier for the RevRec agent (auto-upgrade on PDF/complex tasks).
CLAUDE_MODEL   = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")
CLAUDE_EFFORT  = os.environ.get("CLAUDE_EFFORT", "high")
CLAUDE_MAX_TOKENS = int(os.environ.get("CLAUDE_MAX_TOKENS", "16000"))
PROMPT_CACHE   = os.environ.get("PROMPT_CACHE", "1").strip() not in ("0", "false", "no", "")
TIMEOUT        = 600               # seconds — local models may need several minutes
TOOL_VISIBILITY_BUDGET = 8

# Tasks that auto-route to Claude API (large context, PDF, complex multi-step)
CLAUDE_TRIGGERS = [".pdf", "contract modification", "large contract", "full analysis"]

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------
# Excel helpers
# ---------------------------------------------------------------
HEADER_FILL   = PatternFill("solid", fgColor="1F3864")
SUBHEAD_FILL  = PatternFill("solid", fgColor="2E75B6")
ALT_FILL      = PatternFill("solid", fgColor="D6E4F0")
TOTAL_FILL    = PatternFill("solid", fgColor="BDD7EE")
WHITE_FILL    = PatternFill("solid", fgColor="FFFFFF")
HEADER_FONT   = Font(bold=True, color="FFFFFF", size=11)
SUBHEAD_FONT  = Font(bold=True, color="FFFFFF", size=10)
LABEL_FONT    = Font(bold=True, size=10)
TOTAL_FONT    = Font(bold=True, size=10)
NORMAL_FONT   = Font(size=10)
THIN_BORDER   = Border(
    left=Side(style="thin"), right=Side(style="thin"),
    top=Side(style="thin"),  bottom=Side(style="thin")
)
MONEY_FMT  = '#,##0.00'
PCT_FMT    = '0.0%'
NUM_FMT    = '#,##0'

def style_header(cell, sub=False):
    cell.fill = SUBHEAD_FILL if sub else HEADER_FILL
    cell.font = SUBHEAD_FONT if sub else HEADER_FONT
    cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    cell.border = THIN_BORDER

def style_total(cell):
    cell.fill = TOTAL_FILL
    cell.font = TOTAL_FONT
    cell.border = THIN_BORDER

def style_normal(cell, alt=False):
    cell.fill = ALT_FILL if alt else WHITE_FILL
    cell.font = NORMAL_FONT
    cell.border = THIN_BORDER

def autofit(ws):
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            try:
                if cell.value:
                    max_len = max(max_len, len(str(cell.value)))
            except Exception:
                pass
        ws.column_dimensions[col_letter].width = min(max(max_len + 2, 10), 40)

# ---------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "analyze_contract",
            "description": (
                "Analyze a contract description or text for ASC 606 / Topic 606 revenue recognition. "
                "Returns: identified performance obligations, variable consideration flags, "
                "transaction price guidance, SSP allocation notes, and recognition timing."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "contract_text": {
                        "type": "string",
                        "description": "Contract description or excerpted contract text to analyze"
                    },
                    "entity_type": {
                        "type": "string",
                        "description": "Type of entity: 'saas', 'software_license', 'hybrid', 'professional_services'"
                    }
                },
                "required": ["contract_text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_allocation_schedule",
            "description": (
                "Create an Excel workbook with a multi-element arrangement allocation schedule. "
                "Allocates transaction price across performance obligations using SSP ratios. "
                "Includes a revenue recognition waterfall by period."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Output filename e.g. 'contract_allocation.xlsx'"
                    },
                    "contract_name": {
                        "type": "string",
                        "description": "Name or ID of the contract"
                    },
                    "total_price": {
                        "type": "number",
                        "description": "Total contract transaction price"
                    },
                    "performance_obligations": {
                        "type": "array",
                        "description": "List of performance obligation objects with name, ssp, timing, periods",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name":    {"type": "string"},
                                "ssp":     {"type": "number",  "description": "Stand-alone selling price"},
                                "timing":  {"type": "string",  "description": "'point_in_time' or 'over_time'"},
                                "periods": {"type": "integer", "description": "Number of periods if over_time (months)"}
                            }
                        }
                    }
                },
                "required": ["filename", "contract_name", "total_price", "performance_obligations"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_deferred_revenue_schedule",
            "description": (
                "Create an Excel deferred revenue rollforward schedule. "
                "Tracks beginning balance, additions, recognized amounts, and ending balance by period."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Output filename e.g. 'deferred_revenue_rollforward.xlsx'"
                    },
                    "contracts": {
                        "type": "array",
                        "description": "List of contract objects",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name":              {"type": "string"},
                                "total_value":       {"type": "number"},
                                "start_period":      {"type": "string", "description": "e.g. '2025-Q1'"},
                                "recognition_months":{"type": "integer"}
                            }
                        }
                    },
                    "periods": {
                        "type": "array",
                        "description": "List of period labels e.g. ['Q1 2025','Q2 2025',...]",
                        "items": {"type": "string"}
                    }
                },
                "required": ["filename", "contracts", "periods"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_variable_consideration_model",
            "description": (
                "Create an Excel model for estimating variable consideration under ASC 606. "
                "Implements both expected value and most-likely-amount methods with constraint analysis."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Output filename e.g. 'variable_consideration.xlsx'"
                    },
                    "contract_name": {"type": "string"},
                    "base_price":    {"type": "number",  "description": "Base fixed contract price"},
                    "scenarios": {
                        "type": "array",
                        "description": "List of variable consideration scenarios",
                        "items": {
                            "type": "object",
                            "properties": {
                                "description":  {"type": "string"},
                                "amount":       {"type": "number"},
                                "probability":  {"type": "number", "description": "0.0 to 1.0"},
                                "type":         {"type": "string", "description": "bonus, penalty, refund, discount"}
                            }
                        }
                    }
                },
                "required": ["filename", "contract_name", "base_price", "scenarios"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_contract_modification_analysis",
            "description": (
                "Create an Excel workbook analyzing a contract modification under ASC 606. "
                "Evaluates whether the modification is a new contract, prospective change, or "
                "cumulative catch-up, and recalculates revenue per ASC 606-10-25-18 through 25-21."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename":         {"type": "string"},
                    "contract_name":    {"type": "string"},
                    "original_price":   {"type": "number"},
                    "original_pos": {
                        "type": "array",
                        "description": "Original performance obligations",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name":        {"type": "string"},
                                "allocated":   {"type": "number"},
                                "recognized":  {"type": "number"},
                                "remaining":   {"type": "number"}
                            }
                        }
                    },
                    "modification_type": {
                        "type": "string",
                        "description": "new_contract | prospective | cumulative_catchup"
                    },
                    "new_goods_services": {"type": "string"},
                    "price_change":       {"type": "number"}
                },
                "required": ["filename", "contract_name", "original_price",
                             "original_pos", "modification_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_excel",
            "description": "Read data from an existing Excel file. Returns sheet names and cell values.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path":       {"type": "string", "description": "Absolute path to .xlsx file"},
                    "sheet_name": {"type": "string", "description": "Sheet name to read (optional, reads first sheet if omitted)"},
                    "max_rows":   {"type": "integer", "description": "Max rows to return (default 100)"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_memo",
            "description": "Write a structured ASC 606 technical accounting memo to a .txt or .md file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename":       {"type": "string", "description": "Output filename e.g. 'rev_rec_memo.md'"},
                    "contract_name":  {"type": "string"},
                    "content":        {"type": "string", "description": "Full memo content in markdown"}
                },
                "required": ["filename", "contract_name", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_pdf",
            "description": (
                "Extract text from a PDF contract or document. "
                "Returns the full text (or a page range) ready for ASC 606 analysis. "
                "Use this before analyze_contract when the user provides a PDF file path."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path to the PDF file"
                    },
                    "start_page": {
                        "type": "integer",
                        "description": "First page to extract (1-based). Omit for page 1."
                    },
                    "end_page": {
                        "type": "integer",
                        "description": "Last page to extract (1-based, inclusive). Omit for all pages."
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": "Maximum characters to return (default 12000 — fits one model context pass)."
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read any text file (contract, CSV, existing memo, Python script).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_outputs",
            "description": "List all files produced in the revenue-agent workspace.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run a PowerShell command (install packages, run scripts). Always asks confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command":     {"type": "string"},
                    "working_dir": {"type": "string"}
                },
                "required": ["command"]
            }
        }
    },
]

# ---------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------
def tool_analyze_contract(contract_text: str, entity_type: str = "saas") -> str:
    """
    Returns a structured ASC 606 analysis framework based on contract text.
    The model will fill in the actual analysis — this tool provides structure + flags.
    """
    flags = []

    text_lower = contract_text.lower()

    # Performance obligation indicators
    pos = []
    po_keywords = {
        "Software license": ["license", "perpetual", "on-premise", "on premise"],
        "SaaS / hosted service": ["saas", "cloud", "hosted", "subscription service", "access to"],
        "PCS / Support & Maintenance": ["pcs", "maintenance", "support", "updates", "upgrades", "bug fix"],
        "Professional services": ["implementation", "consulting", "training", "customization", "professional services"],
        "Specified upgrades": ["specified upgrade", "specified enhancement", "future version", "roadmap"],
        "Material right / option": ["option to renew", "renewal option", "discount on future", "material right"],
        "Usage-based fees": ["usage", "per transaction", "per user", "per seat", "consumption"],
    }
    for po_name, keywords in po_keywords.items():
        if any(k in text_lower for k in keywords):
            pos.append(po_name)

    # Variable consideration flags
    vc_keywords = {
        "Performance bonuses": ["bonus", "milestone payment", "performance incentive"],
        "Penalties / clawbacks": ["penalty", "clawback", "service level", "sla", "credits"],
        "Refund rights": ["refund", "money back", "cancellation right"],
        "Volume discounts": ["volume discount", "tiered pricing", "volume rebate"],
        "Usage-based / royalties": ["usage-based", "royalty", "per transaction", "consumption-based"],
        "Price concessions": ["price protection", "most favored nation", "mfn clause"],
    }
    for vc_name, keywords in vc_keywords.items():
        if any(k in text_lower for k in keywords):
            flags.append(f"VARIABLE CONSIDERATION: {vc_name}")

    # Contract combination triggers
    if any(k in text_lower for k in ["related party", "same time", "package deal", "bundled"]):
        flags.append("CONTRACT COMBINATION: May need to evaluate contract combination criteria (606-10-25-9)")

    # Modification indicators
    if any(k in text_lower for k in ["amendment", "change order", "modify", "modification", "addendum"]):
        flags.append("CONTRACT MODIFICATION: Evaluate under 606-10-25-18 through 25-21")

    # License vs SaaS distinction
    if any(k in text_lower for k in ["take possession", "download", "on-premise", "perpetual"]):
        flags.append("LICENSE vs SaaS: Evaluate software license criteria — can customer take possession and host independently?")

    # Principal vs agent
    if any(k in text_lower for k in ["reseller", "distributor", "third party", "agent", "marketplace"]):
        flags.append("PRINCIPAL vs AGENT: Evaluate control of goods/services before transfer to customer (606-10-55-36)")

    result = {
        "entity_type": entity_type,
        "potential_performance_obligations": pos if pos else ["REVIEW NEEDED — no standard POs detected"],
        "variable_consideration_flags": flags if flags else ["None detected — verify manually"],
        "asc606_checklist": {
            "step1_contract_exists": "Verify: written/verbal agreement, approved, rights identified, payment terms defined, commercial substance",
            "step2_identify_pos": f"Identified: {', '.join(pos) if pos else 'see contract review'}. Test: (1) capable of being distinct, (2) distinct in context of contract",
            "step3_transaction_price": "Determine fixed + variable amounts. Apply constraint. Check financing component (>12 months).",
            "step4_allocate": "Establish SSP for each PO. Use observable price or estimate (adjusted market, expected cost+margin, residual). Allocate pro-rata.",
            "step5_recognize": "Point-in-time (license, delivery) vs Over-time (SaaS, PCS, services meeting criteria 606-10-25-27)",
        },
        "kpmg_handbook_references": {
            "contract_exists":   "Section B — Step 1 (pp. 66-135)",
            "perf_obligations":  "Section C — Step 2 (pp. 136-293): software/SaaS distinct analysis",
            "transaction_price": "Section D — Step 3 (pp. 294-398): variable consideration, constraint",
            "allocation":        "Section E — Step 4 (pp. 399-513): SSP, VSOE no longer required",
            "recognition":       "Section F — Step 5 (pp. 514-637): license vs SaaS timing",
            "modifications":     "Section G — Contract modifications (pp. 638-702)",
            "contract_costs":    "Section H — Contract costs, 340-40 (pp. 703-774)",
        },
        "high_risk_areas": flags,
    }
    return json.dumps(result, indent=2)


def tool_create_allocation_schedule(
        filename: str,
        contract_name: str,
        total_price: float,
        performance_obligations: list) -> str:
    try:
        wb = openpyxl.Workbook()

        # ---- Sheet 1: Allocation Summary ----
        ws = wb.active
        ws.title = "Allocation Summary"
        ws.sheet_view.showGridLines = False

        # Title
        ws.merge_cells("A1:H1")
        ws["A1"] = f"ASC 606 — Transaction Price Allocation"
        ws["A1"].font = Font(bold=True, size=14, color="1F3864")
        ws["A1"].alignment = Alignment(horizontal="left")

        ws.merge_cells("A2:H2")
        ws["A2"] = f"Contract: {contract_name}   |   Total Transaction Price: ${total_price:,.2f}   |   Date: {datetime.now().strftime('%Y-%m-%d')}"
        ws["A2"].font = Font(size=10, color="595959")
        ws.row_dimensions[3].height = 8

        # Headers row 4
        headers = ["Performance Obligation", "Recognition Pattern", "Periods",
                   "SSP", "SSP %", "Allocated Price", "Allocated %", "ASC 606 Ref"]
        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=4, column=col, value=h)
            style_header(cell)
        ws.row_dimensions[4].height = 22

        total_ssp = sum(po.get("ssp", 0) for po in performance_obligations)

        rows_data = []
        for i, po in enumerate(performance_obligations):
            name    = po.get("name", f"PO {i+1}")
            ssp     = float(po.get("ssp", 0))
            timing  = po.get("timing", "point_in_time")
            periods = po.get("periods", 1)
            ssp_pct = ssp / total_ssp if total_ssp else 0
            alloc   = total_price * ssp_pct
            alloc_pct = alloc / total_price if total_price else 0
            ref = "606-10-25-14" if timing == "over_time" else "606-10-25-30"
            rows_data.append((name, timing.replace("_", " ").title(), periods,
                               ssp, ssp_pct, alloc, alloc_pct, ref))

        for i, row in enumerate(rows_data):
            r = i + 5
            alt = (i % 2 == 1)
            for col, val in enumerate(row, 1):
                cell = ws.cell(row=r, column=col, value=val)
                style_normal(cell, alt)
                if col == 4:
                    cell.number_format = MONEY_FMT
                elif col == 5:
                    cell.number_format = PCT_FMT
                elif col == 6:
                    cell.number_format = MONEY_FMT
                elif col == 7:
                    cell.number_format = PCT_FMT

        # Total row
        total_row = len(rows_data) + 5
        totals = ["TOTAL", "", "",
                  total_ssp, 1.0, total_price, 1.0, ""]
        for col, val in enumerate(totals, 1):
            cell = ws.cell(row=total_row, column=col, value=val)
            style_total(cell)
            if col == 4:
                cell.number_format = MONEY_FMT
            elif col == 5:
                cell.number_format = PCT_FMT
            elif col == 6:
                cell.number_format = MONEY_FMT
            elif col == 7:
                cell.number_format = PCT_FMT

        # Notes section
        note_row = total_row + 2
        ws.cell(row=note_row, column=1, value="NOTES & REFERENCES").font = LABEL_FONT
        notes = [
            "SSP = Stand-Alone Selling Price per ASC 606-10-32-31. VSOE no longer required under Topic 606.",
            "Allocation is pro-rata based on relative SSP per ASC 606-10-32-28.",
            "Variable consideration (if any) allocated per ASC 606-10-32-39 guidance.",
            "KPMG Handbook Ref: Section E — Step 4: Allocate the Transaction Price (pp. 399-513).",
        ]
        for j, note in enumerate(notes):
            cell = ws.cell(row=note_row + 1 + j, column=1, value=note)
            cell.font = Font(size=9, color="595959", italic=True)
            ws.merge_cells(f"A{note_row + 1 + j}:H{note_row + 1 + j}")

        autofit(ws)

        # ---- Sheet 2: Recognition Waterfall ----
        ws2 = wb.create_sheet("Recognition Waterfall")
        ws2.sheet_view.showGridLines = False

        ws2.merge_cells("A1:M1")
        ws2["A1"] = f"Revenue Recognition Waterfall — {contract_name}"
        ws2["A1"].font = Font(bold=True, size=13, color="1F3864")
        ws2["A1"].alignment = Alignment(horizontal="left")
        ws2.row_dimensions[3].height = 8

        # Find max periods
        max_periods = max((po.get("periods", 1) for po in performance_obligations), default=12)
        period_labels = [f"Period {p+1}" for p in range(max_periods)]

        # Headers
        ws2.cell(row=3, column=1, value="Performance Obligation")
        style_header(ws2.cell(row=3, column=1))
        ws2.cell(row=3, column=2, value="Total Allocated")
        style_header(ws2.cell(row=3, column=2))
        for p, label in enumerate(period_labels):
            cell = ws2.cell(row=3, column=3 + p, value=label)
            style_header(cell, sub=True)
        ws2.row_dimensions[3].height = 22

        # Data rows
        period_totals = [0.0] * max_periods
        total_ssp = sum(po.get("ssp", 0) for po in performance_obligations)

        for i, po in enumerate(performance_obligations):
            r   = i + 4
            alt = (i % 2 == 1)
            ssp = float(po.get("ssp", 0))
            ssp_pct = ssp / total_ssp if total_ssp else 0
            alloc   = total_price * ssp_pct
            timing  = po.get("timing", "point_in_time")
            periods = int(po.get("periods", 1))

            cell = ws2.cell(row=r, column=1, value=po.get("name", f"PO {i+1}"))
            style_normal(cell, alt)
            cell = ws2.cell(row=r, column=2, value=alloc)
            style_normal(cell, alt)
            cell.number_format = MONEY_FMT

            if timing == "point_in_time":
                # Recognize all in period 1
                cell = ws2.cell(row=r, column=3, value=alloc)
                style_normal(cell, alt)
                cell.number_format = MONEY_FMT
                period_totals[0] += alloc
                for p in range(1, max_periods):
                    c = ws2.cell(row=r, column=3 + p, value="-")
                    style_normal(c, alt)
                    c.alignment = Alignment(horizontal="center")
            else:
                # Straight-line over periods
                per_period = alloc / periods if periods else 0
                for p in range(max_periods):
                    if p < periods:
                        c = ws2.cell(row=r, column=3 + p, value=per_period)
                        c.number_format = MONEY_FMT
                        period_totals[p] += per_period
                    else:
                        c = ws2.cell(row=r, column=3 + p, value="-")
                        c.alignment = Alignment(horizontal="center")
                    style_normal(c, alt)

        # Total row
        total_r = len(performance_obligations) + 4
        cell = ws2.cell(row=total_r, column=1, value="TOTAL REVENUE")
        style_total(cell)
        cell = ws2.cell(row=total_r, column=2, value=total_price)
        style_total(cell)
        cell.number_format = MONEY_FMT
        for p, pt in enumerate(period_totals):
            cell = ws2.cell(row=total_r, column=3 + p, value=round(pt, 2) if pt else "-")
            style_total(cell)
            if isinstance(pt, float) and pt > 0:
                cell.number_format = MONEY_FMT

        autofit(ws2)

        # ---- Sheet 3: ASC 606 Checklist ----
        ws3 = wb.create_sheet("ASC 606 Checklist")
        ws3.sheet_view.showGridLines = False
        ws3.merge_cells("A1:D1")
        ws3["A1"] = "ASC 606 Five-Step Model — Review Checklist"
        ws3["A1"].font = Font(bold=True, size=13, color="1F3864")
        ws3["A1"].alignment = Alignment(horizontal="left")

        checklist = [
            ("STEP", "REQUIREMENT", "KPMG HANDBOOK REF", "STATUS"),
            ("Step 1", "Identify the contract — approval, rights identified, payment terms, commercial substance, collectibility probable", "Section B (pp. 66-135)", ""),
            ("Step 2a", "Identify promised goods/services in contract — explicit and implicit promises", "Section C (pp. 136-293)", ""),
            ("Step 2b", "Determine distinct POs — capable of being distinct AND distinct in context of contract", "C: 606-10-25-19", ""),
            ("Step 2c", "Evaluate series of distinct goods/services (same pattern of transfer, same measure of progress)", "C: 606-10-25-14(b)", ""),
            ("Step 2d", "Identify material rights (options for additional goods/services at discount)", "C: 606-10-55-42", ""),
            ("Step 3a", "Determine fixed consideration", "Section D (pp. 294-398)", ""),
            ("Step 3b", "Estimate variable consideration — expected value OR most likely amount", "D: 606-10-32-8", ""),
            ("Step 3c", "Apply variable consideration constraint — highly probable no significant reversal", "D: 606-10-32-11", ""),
            ("Step 3d", "Assess significant financing component (>12 months between payment and delivery)", "D: 606-10-32-15", ""),
            ("Step 3e", "Non-cash consideration at fair value", "D: 606-10-32-21", ""),
            ("Step 4a", "Determine SSP for each PO — observable price or estimate", "Section E (pp. 399-513)", ""),
            ("Step 4b", "Allocate transaction price pro-rata based on relative SSP", "E: 606-10-32-28", ""),
            ("Step 4c", "Allocate discounts — evidence of discount belonging to specific POs?", "E: 606-10-32-36", ""),
            ("Step 4d", "Allocate variable consideration to specific POs if criteria met", "E: 606-10-32-39", ""),
            ("Step 5a", "Over-time criteria met? (customer consumes, entity creates w/no alternative use + right to payment, or customer controls asset)", "Section F (pp. 514-637)", ""),
            ("Step 5b", "If over-time: measure of progress (output or input method)", "F: 606-10-25-31", ""),
            ("Step 5c", "If point-in-time: control transferred (right to payment, legal title, physical possession, risks & rewards, customer acceptance)", "F: 606-10-25-30", ""),
            ("Step 5d", "Software license: functional IP (point-in-time) vs symbolic IP (over-time)", "F: 606-10-55-58", ""),
            ("Mod.", "Contract modification — new contract, prospective, or cumulative catch-up?", "Section G (pp. 638-702)", ""),
            ("Costs", "Contract acquisition costs (incremental) — capitalize if expected to recover. Amortize over benefit period", "Section H (pp. 703-774)", ""),
        ]

        for r_i, row in enumerate(checklist):
            for c_i, val in enumerate(row):
                cell = ws3.cell(row=r_i + 3, column=c_i + 1, value=val)
                if r_i == 0:
                    style_header(cell)
                    ws3.row_dimensions[r_i + 3].height = 22
                elif val and val.startswith("Step") or val in ("Mod.", "Costs"):
                    cell.font = LABEL_FONT
                    cell.fill = ALT_FILL if r_i % 2 == 0 else WHITE_FILL
                    cell.border = THIN_BORDER
                else:
                    style_normal(cell, r_i % 2 == 0)
                    if c_i == 3:  # Status column
                        cell.fill = PatternFill("solid", fgColor="FFFF99")

        ws3.column_dimensions["A"].width = 10
        ws3.column_dimensions["B"].width = 60
        ws3.column_dimensions["C"].width = 28
        ws3.column_dimensions["D"].width = 18

        # Save
        out_path = OUTPUT_DIR / filename
        wb.save(str(out_path))
        return f"OK: Created allocation schedule at {out_path}"

    except Exception as e:
        return f"ERROR creating allocation schedule: {e}"


def tool_create_deferred_revenue_schedule(
        filename: str,
        contracts: list,
        periods: list) -> str:
    try:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Deferred Revenue Rollforward"
        ws.sheet_view.showGridLines = False

        ws.merge_cells(f"A1:{get_column_letter(len(periods) + 5)}1")
        ws["A1"] = "Deferred Revenue Rollforward — ASC 606"
        ws["A1"].font = Font(bold=True, size=13, color="1F3864")
        ws["A1"].alignment = Alignment(horizontal="left")
        ws.row_dimensions[3].height = 8

        # Headers
        base_headers = ["Contract", "Total Value", "Start Period", "Rec. Months"]
        all_headers = base_headers + periods + ["Total Recognized", "Remaining Deferred"]
        for c, h in enumerate(all_headers, 1):
            cell = ws.cell(row=3, column=c, value=h)
            style_header(cell, sub=(c > len(base_headers)))
        ws.row_dimensions[3].height = 22

        # Data
        period_totals = [0.0] * len(periods)
        total_recognized = 0.0

        for i, contract in enumerate(contracts):
            r   = i + 4
            alt = i % 2 == 1
            name    = contract.get("name", f"Contract {i+1}")
            value   = float(contract.get("total_value", 0))
            start   = contract.get("start_period", periods[0] if periods else "P1")
            months  = int(contract.get("recognition_months", len(periods)))
            per_period = value / months if months else 0

            # Find start index
            start_idx = periods.index(start) if start in periods else 0
            recognized = 0.0

            ws.cell(row=r, column=1, value=name).border = THIN_BORDER
            ws.cell(row=r, column=2, value=value).number_format = MONEY_FMT
            ws.cell(row=r, column=3, value=start)
            ws.cell(row=r, column=4, value=months)

            for p_i, _ in enumerate(periods):
                cell = ws.cell(row=r, column=5 + p_i)
                style_normal(cell, alt)
                if start_idx <= p_i < start_idx + months:
                    cell.value = round(per_period, 2)
                    cell.number_format = MONEY_FMT
                    period_totals[p_i] += per_period
                    recognized += per_period
                else:
                    cell.value = "-"
                    cell.alignment = Alignment(horizontal="center")

            total_recognized += recognized
            remaining = value - recognized

            cell_tr = ws.cell(row=r, column=5 + len(periods), value=round(recognized, 2))
            cell_tr.number_format = MONEY_FMT
            style_normal(cell_tr, alt)
            cell_rem = ws.cell(row=r, column=6 + len(periods), value=round(remaining, 2))
            cell_rem.number_format = MONEY_FMT
            style_normal(cell_rem, alt)

            for c in [1, 2, 3, 4]:
                style_normal(ws.cell(row=r, column=c), alt)

        # Total row
        total_r = len(contracts) + 4
        ws.cell(row=total_r, column=1, value="TOTAL").font = TOTAL_FONT
        for c in range(1, len(all_headers) + 1):
            style_total(ws.cell(row=total_r, column=c))

        for p_i, pt in enumerate(period_totals):
            cell = ws.cell(row=total_r, column=5 + p_i, value=round(pt, 2))
            cell.number_format = MONEY_FMT
            style_total(cell)

        grand_total = sum(c.get("total_value", 0) for c in contracts)
        ws.cell(row=total_r, column=2, value=grand_total).number_format = MONEY_FMT
        ws.cell(row=total_r, column=5 + len(periods), value=round(total_recognized, 2)).number_format = MONEY_FMT
        ws.cell(row=total_r, column=6 + len(periods), value=round(grand_total - total_recognized, 2)).number_format = MONEY_FMT

        autofit(ws)
        out_path = OUTPUT_DIR / filename
        wb.save(str(out_path))
        return f"OK: Deferred revenue schedule created at {out_path}"
    except Exception as e:
        return f"ERROR: {e}"


def tool_create_variable_consideration_model(
        filename: str,
        contract_name: str,
        base_price: float,
        scenarios: list) -> str:
    try:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Variable Consideration"
        ws.sheet_view.showGridLines = False

        ws.merge_cells("A1:G1")
        ws["A1"] = f"Variable Consideration Analysis — ASC 606-10-32-8"
        ws["A1"].font = Font(bold=True, size=13, color="1F3864")
        ws.row_dimensions[3].height = 8

        ws.cell(row=2, column=1, value=f"Contract: {contract_name}   |   Base Price: ${base_price:,.2f}")
        ws.cell(row=2, column=1).font = Font(size=10, color="595959")

        # Method 1: Expected Value
        ws.merge_cells("A4:G4")
        ws["A4"] = "METHOD 1: Expected Value (probability-weighted)"
        ws["A4"].font = Font(bold=True, size=11, color="1F3864")

        headers = ["Scenario", "Type", "Amount", "Probability", "Expected Value",
                   "Constraint Applied?", "ASC 606 Ref"]
        for c, h in enumerate(headers, 1):
            style_header(ws.cell(row=5, column=c, value=h))

        total_ev = 0.0
        for i, s in enumerate(scenarios):
            r   = i + 6
            alt = i % 2 == 1
            ev  = float(s.get("amount", 0)) * float(s.get("probability", 0))
            total_ev += ev
            row_data = [
                s.get("description", f"Scenario {i+1}"),
                s.get("type", "variable"),
                float(s.get("amount", 0)),
                float(s.get("probability", 0)),
                round(ev, 2),
                "Review — highly probable?",
                "606-10-32-8(a)"
            ]
            for c, val in enumerate(row_data, 1):
                cell = ws.cell(row=r, column=c, value=val)
                style_normal(cell, alt)
                if c == 3:
                    cell.number_format = MONEY_FMT
                elif c == 4:
                    cell.number_format = PCT_FMT
                elif c == 5:
                    cell.number_format = MONEY_FMT

        ev_total_r = len(scenarios) + 6
        ws.cell(row=ev_total_r, column=1, value="Expected Value Total")
        ws.cell(row=ev_total_r, column=5, value=round(total_ev, 2)).number_format = MONEY_FMT
        for c in range(1, 8):
            style_total(ws.cell(row=ev_total_r, column=c))

        # Summary: Total estimated transaction price
        summary_r = ev_total_r + 2
        ws.merge_cells(f"A{summary_r}:G{summary_r}")
        ws[f"A{summary_r}"] = "TRANSACTION PRICE SUMMARY"
        ws[f"A{summary_r}"].font = Font(bold=True, size=11, color="1F3864")

        summary_data = [
            ("Base / Fixed Price", base_price),
            ("Expected Variable Consideration (pre-constraint)", total_ev),
            ("Estimated Transaction Price (pre-constraint)", base_price + total_ev),
        ]
        for j, (label, val) in enumerate(summary_data):
            r = summary_r + 1 + j
            ws.cell(row=r, column=1, value=label).font = LABEL_FONT
            cell = ws.cell(row=r, column=2, value=val)
            cell.number_format = MONEY_FMT
            cell.font = NORMAL_FONT

        # Notes
        note_r = summary_r + len(summary_data) + 2
        ws.cell(row=note_r, column=1, value="CONSTRAINT ANALYSIS NOTES").font = LABEL_FONT
        constraint_notes = [
            "Per 606-10-32-11: Include variable consideration ONLY to extent highly probable no significant revenue reversal when uncertainty resolved.",
            "Factors increasing risk of reversal: susceptibility to external factors, broad range of outcomes, long time to resolution, limited experience, wide range of consideration in similar contracts.",
            "KPMG Handbook Ref: Section D — Step 3 (pp. 294-398), Variable Consideration and Constraint guidance.",
            "Method 2 (most likely amount) may be appropriate for binary outcomes — apply whichever better predicts entitled consideration.",
        ]
        for j, note in enumerate(constraint_notes):
            cell = ws.cell(row=note_r + 1 + j, column=1, value=note)
            cell.font = Font(size=9, italic=True, color="595959")
            ws.merge_cells(f"A{note_r+1+j}:G{note_r+1+j}")

        autofit(ws)
        out_path = OUTPUT_DIR / filename
        wb.save(str(out_path))
        return f"OK: Variable consideration model created at {out_path}"
    except Exception as e:
        return f"ERROR: {e}"


def tool_create_contract_modification_analysis(
        filename: str,
        contract_name: str,
        original_price: float,
        original_pos: list,
        modification_type: str,
        new_goods_services: str = "",
        price_change: float = 0.0) -> str:
    try:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Modification Analysis"
        ws.sheet_view.showGridLines = False

        ws.merge_cells("A1:F1")
        ws["A1"] = f"Contract Modification Analysis — ASC 606-10-25-18 through 25-21"
        ws["A1"].font = Font(bold=True, size=13, color="1F3864")

        ws.cell(row=2, column=1, value=f"Contract: {contract_name}   |   Modification Type: {modification_type.replace('_',' ').title()}")
        ws.cell(row=2, column=1).font = Font(size=10, color="595959")
        ws.row_dimensions[3].height = 8

        # Decision tree
        ws.cell(row=4, column=1, value="MODIFICATION TYPE DECISION TREE").font = LABEL_FONT

        decision_map = {
            "new_contract":      ("New Contract (606-10-25-18a)",
                                  "Remaining goods/services are distinct AND price reflects SSP of additional goods/services.",
                                  "Account for as separate contract. Original contract unaffected."),
            "prospective":       ("Termination + New Contract (606-10-25-18b)",
                                  "Remaining goods/services are distinct but price does NOT reflect SSP (or partially delivered).",
                                  "Treat as termination of original and creation of new contract. Reallocate remaining consideration."),
            "cumulative_catchup":("Cumulative Catch-up (606-10-25-18c)",
                                  "Remaining goods/services are NOT distinct — modification to single performance obligation.",
                                  "Update transaction price and measure of completion. Recognize adjustment as revenue/contra-revenue in current period."),
        }

        dtype, criteria, treatment = decision_map.get(
            modification_type,
            ("Unknown", "Review modification type", "Consult KPMG Handbook Section G"))

        ws.cell(row=5, column=1, value="Classification:").font = LABEL_FONT
        ws.cell(row=5, column=2, value=dtype)
        ws.cell(row=6, column=1, value="Criteria Met:").font = LABEL_FONT
        ws.cell(row=6, column=2, value=criteria)
        ws.cell(row=7, column=1, value="Accounting Treatment:").font = LABEL_FONT
        ws.cell(row=7, column=2, value=treatment)
        ws.merge_cells("B5:F5")
        ws.merge_cells("B6:F6")
        ws.merge_cells("B7:F7")
        for r in [5, 6, 7]:
            ws.cell(row=r, column=2).font = NORMAL_FONT
            ws.cell(row=r, column=2).border = THIN_BORDER
            ws.cell(row=r, column=1).fill = ALT_FILL
            ws.cell(row=r, column=1).border = THIN_BORDER

        # Original PO schedule
        ws.cell(row=9, column=1, value="ORIGINAL CONTRACT — PERFORMANCE OBLIGATIONS").font = LABEL_FONT
        headers = ["Performance Obligation", "Allocated Price", "Recognized to Date", "Remaining", "Status"]
        for c, h in enumerate(headers, 1):
            style_header(ws.cell(row=10, column=c, value=h))

        total_alloc = total_recog = total_remain = 0.0
        for i, po in enumerate(original_pos):
            r   = i + 11
            alt = i % 2 == 1
            alloc  = float(po.get("allocated", 0))
            recog  = float(po.get("recognized", 0))
            remain = float(po.get("remaining", alloc - recog))
            total_alloc  += alloc
            total_recog  += recog
            total_remain += remain
            row_data = [po.get("name", f"PO {i+1}"), alloc, recog, remain, "Active"]
            for c, val in enumerate(row_data, 1):
                cell = ws.cell(row=r, column=c, value=val)
                style_normal(cell, alt)
                if c in [2, 3, 4]:
                    cell.number_format = MONEY_FMT

        total_r = len(original_pos) + 11
        for c, val in enumerate(["TOTAL", total_alloc, total_recog, total_remain, ""], 1):
            cell = ws.cell(row=total_r, column=c, value=val)
            style_total(cell)
            if c in [2, 3, 4]:
                cell.number_format = MONEY_FMT

        # Modification impact
        impact_r = total_r + 2
        ws.cell(row=impact_r, column=1, value="MODIFICATION IMPACT").font = LABEL_FONT
        impact_data = [
            ("New goods/services added", new_goods_services or "None"),
            ("Price change", price_change),
            ("Revised transaction price", original_price + price_change),
            ("KPMG Handbook reference", "Section G — Contract Modifications (pp. 638-702)"),
        ]
        for j, (label, val) in enumerate(impact_data):
            r = impact_r + 1 + j
            ws.cell(row=r, column=1, value=label).font = LABEL_FONT
            cell = ws.cell(row=r, column=2, value=val)
            ws.merge_cells(f"B{r}:F{r}")
            if isinstance(val, float):
                cell.number_format = MONEY_FMT
            for c in [1, 2]:
                ws.cell(row=r, column=c).border = THIN_BORDER
                ws.cell(row=r, column=c).fill = ALT_FILL if j % 2 == 0 else WHITE_FILL

        ws.column_dimensions["A"].width = 32
        ws.column_dimensions["B"].width = 18
        ws.column_dimensions["C"].width = 18
        ws.column_dimensions["D"].width = 18
        ws.column_dimensions["E"].width = 15
        ws.column_dimensions["F"].width = 15

        out_path = OUTPUT_DIR / filename
        wb.save(str(out_path))
        return f"OK: Contract modification analysis created at {out_path}"
    except Exception as e:
        return f"ERROR: {e}"


def tool_read_excel(path: str, sheet_name: str = None, max_rows: int = 100) -> str:
    try:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        sheets = wb.sheetnames
        ws = wb[sheet_name] if sheet_name and sheet_name in sheets else wb.active
        rows = []
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i >= max_rows:
                break
            rows.append("\t".join(str(v) if v is not None else "" for v in row))
        return f"Sheets: {sheets}\nActive: {ws.title}\n\n" + "\n".join(rows)
    except Exception as e:
        return f"ERROR reading Excel: {e}"


def tool_write_memo(filename: str, contract_name: str, content: str) -> str:
    try:
        out_path = OUTPUT_DIR / filename
        header = f"# ASC 606 Technical Accounting Memo\n**Contract:** {contract_name}\n**Date:** {datetime.now().strftime('%Y-%m-%d')}\n**Reference:** KPMG Revenue for Software and SaaS Handbook (Dec 2025)\n\n---\n\n"
        out_path.write_text(header + content, encoding="utf-8")
        return f"OK: Memo written to {out_path}"
    except Exception as e:
        return f"ERROR writing memo: {e}"


import re as _re

def _clean_pdf_text(text: str) -> str:
    """Strip CID font garbage and normalize whitespace from PDF extraction."""
    # Remove (cid:NNN) sequences left by undecodable embedded fonts
    text = _re.sub(r'\(cid:\d+\)', ' ', text)
    # Collapse runs of whitespace / control chars
    text = _re.sub(r'[ \t]{2,}', ' ', text)
    text = _re.sub(r'\n{3,}', '\n\n', text)
    # Drop lines that are >60% garbage (non-printable after cid removal)
    clean_lines = []
    for line in text.splitlines():
        printable = sum(1 for c in line if c.isprintable())
        if not line.strip() or (len(line) > 0 and printable / len(line) > 0.5):
            clean_lines.append(line)
    return '\n'.join(clean_lines).strip()


def tool_read_pdf(path: str,
                  start_page: int = 1,
                  end_page: int = None,
                  max_chars: int = 12000) -> str:
    """Extract text from a PDF using pdfplumber (preferred) or pypdf fallback."""
    p = Path(path)
    if not p.exists():
        return f"ERROR: File not found: {path}"
    if p.suffix.lower() != ".pdf":
        return f"ERROR: Not a PDF file: {path}"

    pages_extracted = []
    total_pages = 0

    # --- pdfplumber (best quality, handles tables) ---
    if pdfplumber is not None:
        try:
            with pdfplumber.open(str(p)) as pdf:
                total_pages = len(pdf.pages)
                s = max(1, start_page) - 1
                e = min(total_pages, end_page) if end_page else total_pages
                for i in range(s, e):
                    page = pdf.pages[i]
                    text = page.extract_text() or ""
                    # Also grab tables as TSV if present
                    tables = page.extract_tables()
                    table_text = ""
                    for tbl in tables:
                        for row in tbl:
                            table_text += "\t".join(
                                (cell or "").strip() for cell in (row or [])
                            ) + "\n"
                    combined = _clean_pdf_text(text)
                    if table_text.strip():
                        combined += "\n[TABLE]\n" + _clean_pdf_text(table_text)
                    pages_extracted.append(f"--- Page {i+1} ---\n{combined.strip()}")
        except Exception as e:
            return f"ERROR (pdfplumber): {e}"

    # --- pypdf fallback ---
    elif _PdfReader is not None:
        try:
            reader = _PdfReader(str(p))
            total_pages = len(reader.pages)
            s = max(1, start_page) - 1
            e = min(total_pages, end_page) if end_page else total_pages
            for i in range(s, e):
                text = _clean_pdf_text(reader.pages[i].extract_text() or "")
                pages_extracted.append(f"--- Page {i+1} ---\n{text.strip()}")
        except Exception as e:
            return f"ERROR (pypdf): {e}"

    else:
        return ("ERROR: No PDF library available. Run:\n"
                "  py -m pip install pdfplumber")

    if not pages_extracted:
        return f"ERROR: No text extracted from {path} (pages {start_page}-{end_page or total_pages})"

    full_text = "\n\n".join(pages_extracted)
    truncated = len(full_text) > max_chars
    result = full_text[:max_chars]

    header = (
        f"PDF: {p.name}  |  Total pages: {total_pages}  "
        f"|  Extracted: pages {start_page}-{end_page or total_pages}"
    )
    if truncated:
        header += f"  |  TRUNCATED at {max_chars} chars — use start_page/end_page to get more"

    return f"{header}\n{'='*60}\n\n{result}"


def tool_read_file(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return f"ERROR: File not found: {path}"
    try:
        return p.read_text(encoding="utf-8", errors="replace")[:8000]
    except Exception as e:
        return f"ERROR: {e}"


def tool_list_outputs() -> str:
    if not OUTPUT_DIR.exists():
        return "Output directory does not exist yet."
    files = list(OUTPUT_DIR.rglob("*"))
    if not files:
        return "No output files yet."
    return "\n".join(
        f"  {f.relative_to(OUTPUT_DIR)} ({f.stat().st_size:,} bytes)"
        for f in sorted(files) if f.is_file()
    )


def tool_run_command(command: str, working_dir: str = None) -> str:
    print(f"\n  \033[33m[AGENT] Wants to run:\033[0m")
    print(f"  \033[90m  {command}\033[0m")
    confirm = input("  Allow? (y/n): ").strip().lower()
    if confirm != "y":
        return "CANCELLED: User declined."
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True, text=True, timeout=120, cwd=working_dir)
        out = result.stdout.strip()
        err = result.stderr.strip()
        parts = []
        if out:
            parts.append(f"STDOUT:\n{out}")
        if err:
            parts.append(f"STDERR:\n{err}")
        return "\n".join(parts) if parts else "(no output)"
    except Exception as e:
        return f"ERROR: {e}"


# ---------------------------------------------------------------
# Tool dispatch
# ---------------------------------------------------------------
TOOL_MAP = {
    "analyze_contract":                      tool_analyze_contract,
    "create_allocation_schedule":            tool_create_allocation_schedule,
    "create_deferred_revenue_schedule":      tool_create_deferred_revenue_schedule,
    "create_variable_consideration_model":   tool_create_variable_consideration_model,
    "create_contract_modification_analysis": tool_create_contract_modification_analysis,
    "read_excel":                            tool_read_excel,
    "write_memo":                            tool_write_memo,
    "read_pdf":                              tool_read_pdf,
    "read_file":                             tool_read_file,
    "list_outputs":                          tool_list_outputs,
    "run_command":                           tool_run_command,
}

def _approve_registry_tool(tool, args: dict) -> bool:
    print(f"\n  \033[33m[AGENT] Requests {tool.risk} tool: {tool.name}\033[0m")
    print(f"  \033[90m  {summarize_arguments(args)}\033[0m")
    if tool.risk == "destructive":
        return input("  Type DELETE to allow permanent deletion: ").strip() == "DELETE"
    if tool.risk == "external":
        return input("  Type ALLOW to authorize the external action: ").strip() == "ALLOW"
    return input("  Allow? (y/n): ").strip().lower() == "y"


REVREC_TOOLS = build_default_registry()
REVREC_TOOLS.register_many(build_finance_tools(TOOLS, TOOL_MAP), category="finance")


def execute_tool(name: str, args: dict) -> str:
    return REVREC_TOOLS.execute(name, args, approve=_approve_registry_tool)

# ---------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------
def log_action(task: str, tool: str, args: dict, result: str, model: str = AGENT_MODEL):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts":     datetime.now().isoformat(),
        "model":  model,
        "task":   task[:200],
        "tool":   tool,
        "args":   {k: str(v)[:200] for k, v in args.items()},
        "result": result[:300],
    }
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

# ---------------------------------------------------------------
# System prompt — KPMG handbook knowledge embedded
# ---------------------------------------------------------------
SYSTEM_PROMPT = """You are AXIO Rev Rec Agent — an expert ASC 606 / Topic 606 revenue recognition analyst.

Your knowledge base is the KPMG Revenue for Software and SaaS Handbook (December 2025, 774 pages).

## ASC 606 FIVE-STEP MODEL (your operating framework)

STEP 1 — Identify the contract (606-10-25-1)
  - Written, oral, or implied agreement
  - Criteria: approved + committed, rights identifiable, payment terms identifiable,
    commercial substance, probable collection of substantially all consideration
  - Combine contracts if: negotiated as package, consideration dependent, or goods/services
    are single PO (606-10-25-9)

STEP 2 — Identify performance obligations (606-10-25-14)
  - Distinct goods/services = capable of being distinct (customer can benefit alone or with
    other readily available resources) AND distinct in context of contract (not highly
    interdependent)
  - Software license: on-premise license is distinct from PCS unless significant customization
  - SaaS: typically single PO — access to software (not a license unless customer can take
    possession and host independently)
  - PCS / Support: separate PO if distinct
  - Material rights (options at discount > SSP discount): separate PO per 606-10-55-42
  - Series of distinct goods/services: treat as single PO if same pattern of transfer
    and same measure of progress (606-10-25-14b)

STEP 3 — Determine transaction price (606-10-32-2)
  - Fixed consideration + variable consideration (estimate: expected value OR most likely)
  - Constraint: include variable consideration only if highly probable no significant reversal
    (606-10-32-11). Factors: susceptibility to external factors, broad range of outcomes,
    long time to resolution, limited experience, wide possible range
  - Significant financing component if >12 months between payment and transfer (606-10-32-15)
  - Non-cash consideration at fair value
  - Usage-based fees (SaaS): royalties exception does NOT apply; estimate as variable consideration
  - Lag reporting NOT permitted under Topic 606

STEP 4 — Allocate transaction price (606-10-32-28)
  - Allocate pro-rata based on relative SSP
  - SSP: observable price (if sold separately) or estimate
  - Estimation methods: adjusted market assessment, expected cost-plus-margin, residual (only
    if SSP highly variable or uncertain)
  - VSOE no longer required — significant change from legacy US GAAP
  - PCS SSP: can express as % of license fee if reflects standalone price
  - Discount allocation: allocate entirely to specific POs if observable evidence (606-10-32-36)
  - Variable consideration allocation: to specific PO if terms relate specifically and
    allocation consistent with allocation objective (606-10-32-39)

STEP 5 — Recognize revenue (606-10-25-23)
  Over-time criteria (any one of three):
    a) Customer simultaneously receives and consumes benefits as entity performs
    b) Entity creates/enhances asset customer controls as it is created/enhanced
    c) No alternative use AND entity has right to payment for performance to date
  Point-in-time: when control transfers (right to payment, legal title, physical possession,
    risks/rewards, customer acceptance)
  Software licenses:
    - Functional IP (on-premise software) = point-in-time (606-10-55-58c)
    - Symbolic IP = over-time
    - License renewal: recognize at start of renewal period
  SaaS: over-time (customer accesses software; no license transferred unless can take
    possession and host independently)

CONTRACT MODIFICATIONS (606-10-25-18 through 25-21)
  1. New contract: remaining goods distinct AND price = SSP → account separately
  2. Termination + new contract: remaining goods distinct BUT price ≠ SSP
  3. Cumulative catch-up: remaining goods NOT distinct → adjust revenue in current period

CONTRACT COSTS (Subtopic 340-40)
  - Incremental acquisition costs: capitalize if expected to recover; amortize over benefit
    period (including renewals if reasonably certain)
  - Fulfillment costs: capitalize if directly related, generate/enhance resources for future
    obligations, expected to recover
  - Practical expedient: expense if amortization period ≤ 1 year

## YOUR TOOLS
- read_pdf: extract text from a PDF contract (ALWAYS use this first when user provides a PDF path)
- analyze_contract: flag POs, variable consideration, risk areas from contract text
- create_allocation_schedule: Excel workbook with SSP allocation + recognition waterfall
- create_deferred_revenue_schedule: Excel deferred revenue rollforward by period
- create_variable_consideration_model: Excel probability-weighted VC analysis with constraint
- create_contract_modification_analysis: Excel modification type assessment + impact
- read_excel: read existing Excel files
- write_memo: produce structured ASC 606 technical accounting memos
- read_file: read any text/contract file
- list_outputs: see files created in this session
- run_command: run PowerShell (with user confirmation)

## PDF CONTRACT WORKFLOW
When the user provides a PDF file path:
1. Call read_pdf(path=...) — extracts the contract text
2. Call analyze_contract(contract_text=<extracted text>, entity_type=...)
3. Call the appropriate Excel model tools based on the analysis
4. Call write_memo to document findings
For large PDFs, read_pdf returns 12,000 chars by default. Use start_page/end_page to get
specific sections (e.g. pricing schedules, SOW, payment terms) if needed.

## OUTPUT RULES
- Always reference specific ASC 606 paragraph numbers (e.g. 606-10-25-19)
- Reference KPMG Handbook sections when relevant
- Flag areas of significant judgment explicitly
- When creating Excel models, use realistic formatting and include checklist sheets
- Memos must be audit-ready: fact pattern, issue, analysis, conclusion
- Never state a definitive conclusion on ambiguous facts — flag for human review
"""

SYSTEM_PROMPT += """

## SHARED AXIO HARNESS
The harness exposes a stable core plus a small task-specific subset, never every registered
tool at once. Use request_tool(name, reason) when a needed registered tool is hidden. After
creating or changing any file, call verification_gate before giving the final answer.
"""


def _finance_preferred(task: str) -> list[str]:
    """Select at most three RevRec tools; the escape hatch covers later phase changes."""
    text = (task or "").lower()
    preferred: list[str] = []
    keyword_tools = (
        ((".pdf", "pdf", "contract"), "read_pdf"),
        (("analy", "asc 606", "ifrs 15", "performance obligation"), "analyze_contract"),
        (("allocation", "ssp"), "create_allocation_schedule"),
        (("deferred revenue", "rollforward"), "create_deferred_revenue_schedule"),
        (("variable consideration", "constraint"), "create_variable_consideration_model"),
        (("modification",), "create_contract_modification_analysis"),
        (("memo",), "write_memo"),
        (("excel", ".xlsx", "workbook"), "read_excel"),
        (("outputs", "files created"), "list_outputs"),
    )
    for keywords, name in keyword_tools:
        if any(keyword in text for keyword in keywords) and name not in preferred:
            preferred.append(name)
    for fallback in ("analyze_contract", "read_pdf", "list_outputs"):
        if fallback not in preferred:
            preferred.append(fallback)
    return preferred[:3]


def _start_revrec_harness(task: str, mode: str):
    REVREC_TOOLS.start_task(task, [BASE, OUTPUT_DIR, Path.cwd()])
    return (
        DynamicToolRouter(
            REVREC_TOOLS,
            task,
            budget=TOOL_VISIBILITY_BUDGET,
            preferred_names=_finance_preferred(task),
            visibility="dynamic",
        ),
        LoopGuard(),
        TrajectoryLogger(mode),
        step_budget(task),
    )


def _revrec_completion_status() -> tuple[bool, str]:
    return REVREC_TOOLS.completion_status()

# ---------------------------------------------------------------
# Convert Ollama tool schemas -> Anthropic format
# ---------------------------------------------------------------
def _tools_for_claude():
    """Reformat TOOLS list from Ollama schema to Anthropic tool schema."""
    result = []
    for t in TOOLS:
        fn = t["function"]
        result.append({
            "name":         fn["name"],
            "description":  fn["description"],
            "input_schema": fn["parameters"],
        })
    return result


# ---------------------------------------------------------------
# Claude API agent loop (used for PDF + complex tasks)
# ---------------------------------------------------------------
def run_agent_claude(task: str):
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key or _anthropic is None:
        print("\033[33m  Claude API not available — falling back to local model\033[0m")
        run_agent(task)
        return

    client  = _anthropic.Anthropic(api_key=api_key)
    router, guard, trajectory, max_steps = _start_revrec_harness(task, "revrec-claude")
    messages = [{"role": "user", "content": task}]
    try:
        from core import pricing as _pricing
    except Exception:
        _pricing = None
    _usage_acc = {}

    print(
        f"\n\033[90m  model: {CLAUDE_MODEL} (Claude API) | tools: dynamic "
        f"<={TOOL_VISIBILITY_BUDGET} of {len(REVREC_TOOLS.tools)} | "
        f"complexity: {classify_complexity(task)} | max steps: {max_steps}\033[0m\n"
    )
    start = time.time()
    gate_nudges = 0

    for iteration in range(max_steps):
        messages = process_history(messages, "claude")
        tools = router.schemas("claude")
        spinner = Spinner(f"[{CLAUDE_MODEL}] step {iteration+1}").start()
        response = None
        for attempt in range(3):
            try:
                _system = (
                    [{"type": "text", "text": SYSTEM_PROMPT,
                      "cache_control": {"type": "ephemeral"}}]
                    if PROMPT_CACHE else SYSTEM_PROMPT
                )
                response = client.messages.create(
                    model      = CLAUDE_MODEL,
                    max_tokens = CLAUDE_MAX_TOKENS,
                    system     = _system,
                    tools      = tools,
                    messages   = messages,
                    thinking      = {"type": "adaptive"},
                    output_config = {"effort": CLAUDE_EFFORT},
                )
                break
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "rate_limit" in err_str:
                    wait = 65 * (attempt + 1)
                    spinner.stop()
                    print(f"\033[33m  Rate limit hit — waiting {wait}s before retry ({attempt+1}/3)...\033[0m")
                    for remaining in range(wait, 0, -5):
                        print(f"\r  \033[90m  retrying in {remaining}s...\033[0m", end="", flush=True)
                        time.sleep(5)
                    print("\r" + " "*40 + "\r", end="")
                    spinner = Spinner(f"[{CLAUDE_MODEL}] step {iteration+1} retry {attempt+1}").start()
                else:
                    spinner.stop()
                    print(f"\033[31m  Claude API error: {e}\033[0m")
                    return
        if response is None:
            spinner.stop()
            print("\033[31m  Rate limit persists after 3 retries. Try again in a few minutes.\033[0m")
            return
        spinner.stop()
        if _pricing is not None:
            _pricing.add(_usage_acc, getattr(response, "usage", None))

        # Collect text + tool_use blocks
        text_parts = []
        tool_uses  = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_uses.append(block)

        # Append assistant turn (full content list)
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use" or not tool_uses:
            final_text = "\n".join(text_parts).strip()
            trajectory.log_step(
                step=iteration + 1,
                task_type=router.task_type,
                active_tools=(*router.active_names, "request_tool"),
                tool_call=None,
                observation_raw=final_text,
                observation_truncated=truncate_observation(final_text),
                event="assistant",
            )
            allowed, reason = _revrec_completion_status()
            if not allowed and gate_nudges < 2:
                gate_nudges += 1
                messages.append({
                    "role": "user",
                    "content": "[HARNESS] " + reason + " Do not finish until verification_gate passes.",
                })
                continue
            if not allowed:
                print(f"\033[31m  Agent stopped without verification: {reason}\033[0m")
                return
            elapsed = round(time.time() - start, 1)
            print(f"\n\033[36m[{CLAUDE_MODEL}]\033[0m {final_text}")
            print(f"\n\033[90m  Done in {iteration+1} step(s), {elapsed}s\033[0m")
            if _pricing is not None:
                print(f"\033[90m  {_pricing.summarize(CLAUDE_MODEL, _usage_acc)}\033[0m")
            return

        # Execute each tool call
        tool_results = []
        interventions = []
        for tu in tool_uses:
            args     = tu.input if isinstance(tu.input, dict) else {}
            args_str = ", ".join(f"{k}={repr(v)[:50]}" for k, v in args.items())
            print(f"  \033[33m{tu.name}\033[0m({args_str})")

            routed = router.handle_unavailable_call(tu.name, args)
            if routed is None:
                result = execute_tool(tu.name, args)
                record = REVREC_TOOLS.records[-1] if REVREC_TOOLS.records else None
                mutation_success = bool(
                    record and record.ok and record.risk in {"write", "destructive"}
                )
            else:
                result = routed
                mutation_success = False
            truncated = truncate_observation(result)
            router.observe(truncated)
            intervention = guard.record(tu.name, args, truncated, mutation_success)
            if intervention:
                interventions.append(intervention)
            trajectory.log_step(
                step=iteration + 1,
                task_type=router.task_type,
                active_tools=(*router.active_names, "request_tool"),
                tool_call={"name": tu.name, "arguments": args},
                observation_raw=result,
                observation_truncated=truncated,
            )
            preview = result[:100].replace("\n", " ")
            print(f"  \033[90m  {preview}{'...' if len(result) > 100 else ''}\033[0m")
            log_action(task, tu.name, args, result, model=CLAUDE_MODEL)

            tool_results.append({
                "type":        "tool_result",
                "tool_use_id": tu.id,
                "content":     truncated,
            })

        if interventions:
            tool_results.append({"type": "text", "text": "\n".join(interventions)})

        # Feed results back
        messages.append({"role": "user", "content": tool_results})
        if guard.should_stop:
            print("\033[31m  Agent stopped: repeated no-progress interventions exhausted the harness guard.\033[0m")
            return

    print(f"\033[33m  [Stopped at adaptive max {max_steps} steps]\033[0m")


# ---------------------------------------------------------------
# Spinner — shows progress while Ollama thinks
# ---------------------------------------------------------------
class Spinner:
    FRAMES = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]

    def __init__(self, label="Thinking"):
        self.label   = label
        self._stop   = threading.Event()
        self._thread = threading.Thread(target=self._spin, daemon=True)

    def _spin(self):
        i = 0
        while not self._stop.is_set():
            frame = self.FRAMES[i % len(self.FRAMES)]
            print(f"\r  \033[36m{frame}\033[0m  {self.label} ...", end="", flush=True)
            time.sleep(0.1)
            i += 1

    def start(self):
        self._thread.start()
        return self

    def stop(self, clear=True):
        self._stop.set()
        self._thread.join()
        if clear:
            print("\r" + " " * 60 + "\r", end="", flush=True)

# ---------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------
def run_agent(task: str, model: str = AGENT_MODEL):
    router, guard, trajectory, max_steps = _start_revrec_harness(task, "revrec-ollama")
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": task},
    ]
    print(
        f"\n\033[90m  model: {model} | tools: dynamic <={TOOL_VISIBILITY_BUDGET} "
        f"of {len(REVREC_TOOLS.tools)} | complexity: {classify_complexity(task)} "
        f"| max steps: {max_steps}\033[0m\n"
    )
    start = time.time()
    gate_nudges = 0

    for iteration in range(max_steps):
        messages = process_history(messages, "ollama")
        active_tools = router.schemas("ollama")
        payload = {
            "model":    model,
            "messages": messages,
            "tools":    active_tools,
            "stream":   False,
        }
        spinner = Spinner(f"[{model}] step {iteration+1}").start()
        try:
            resp = requests.post(OLLAMA_URL, json=payload, timeout=TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            spinner.stop()
        except requests.exceptions.ConnectionError:
            spinner.stop()
            print("\033[31m  Cannot reach Ollama. Run: ollama serve\033[0m")
            return
        except requests.exceptions.ReadTimeout:
            spinner.stop()
            if model != FALLBACK_MODEL:
                print(f"\033[33m  Timeout on {model} after {TIMEOUT}s — retrying with {FALLBACK_MODEL}\033[0m")
                model = FALLBACK_MODEL
                payload["model"] = model
                spinner2 = Spinner(f"[{FALLBACK_MODEL}] step {iteration+1} (retry)").start()
                try:
                    resp = requests.post(OLLAMA_URL, json=payload, timeout=TIMEOUT)
                    resp.raise_for_status()
                    data = resp.json()
                    spinner2.stop()
                except Exception as e2:
                    spinner2.stop()
                    print(f"\033[31m  Fallback also failed: {e2}\033[0m")
                    return
            else:
                print(f"\033[31m  Timeout after {TIMEOUT}s. Try a shorter prompt or run: ollama ps\033[0m")
                return
        except Exception as e:
            spinner.stop()
            print(f"\033[31m  Error: {e}\033[0m")
            return

        msg        = data.get("message", {})
        tool_calls = msg.get("tool_calls", [])
        content    = msg.get("content", "").strip()

        if not tool_calls:
            trajectory.log_step(
                step=iteration + 1,
                task_type=router.task_type,
                active_tools=(*router.active_names, "request_tool"),
                tool_call=None,
                observation_raw=content,
                observation_truncated=truncate_observation(content),
                event="assistant",
            )
            allowed, reason = _revrec_completion_status()
            if not allowed and gate_nudges < 2:
                gate_nudges += 1
                messages.append({"role": "assistant", "content": content})
                messages.append({
                    "role": "user",
                    "content": "[HARNESS] " + reason + " Do not finish until verification_gate passes.",
                })
                continue
            if not allowed:
                print(f"\033[31m  Agent stopped without verification: {reason}\033[0m")
                return
            elapsed = round(time.time() - start, 1)
            print(f"\n\033[36m[{model}]\033[0m {content}")
            print(f"\n\033[90m  Done in {iteration + 1} step(s), {elapsed}s\033[0m")
            return

        messages.append({
            "role":       "assistant",
            "content":    content,
            "tool_calls": tool_calls,
        })

        interventions = []
        for tc in tool_calls:
            fn_def = tc.get("function", {})
            name   = fn_def.get("name", "")
            args   = fn_def.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}

            args_str = ", ".join(f"{k}={repr(v)[:50]}" for k, v in args.items())
            print(f"  \033[33m{name}\033[0m({args_str})")

            routed = router.handle_unavailable_call(name, args)
            if routed is None:
                result = execute_tool(name, args)
                record = REVREC_TOOLS.records[-1] if REVREC_TOOLS.records else None
                mutation_success = bool(
                    record and record.ok and record.risk in {"write", "destructive"}
                )
            else:
                result = routed
                mutation_success = False
            truncated = truncate_observation(result)
            router.observe(truncated)
            intervention = guard.record(name, args, truncated, mutation_success)
            if intervention:
                interventions.append(intervention)
            trajectory.log_step(
                step=iteration + 1,
                task_type=router.task_type,
                active_tools=(*router.active_names, "request_tool"),
                tool_call={"name": name, "arguments": args},
                observation_raw=result,
                observation_truncated=truncated,
            )
            preview = result[:100].replace("\n", " ")
            print(f"  \033[90m  {preview}{'...' if len(result) > 100 else ''}\033[0m")
            log_action(task, name, args, result, model=model)

            messages.append({"role": "tool", "content": truncated})
        if interventions:
            messages.append({"role": "user", "content": "\n".join(interventions)})
        if guard.should_stop:
            print("\033[31m  Agent stopped: repeated no-progress interventions exhausted the harness guard.\033[0m")
            return

    print(f"\033[33m  [Stopped at adaptive max {max_steps} steps]\033[0m")

# ---------------------------------------------------------------
# REPL
# ---------------------------------------------------------------
BANNER = """
\033[1;36m
 █████╗ ██╗  ██╗██╗ ██████╗      ██████╗ ██████╗ ███╗   ██╗███████╗ ██████╗ ██╗     ███████╗
██╔══██╗╚██╗██╔╝██║██╔═══██╗    ██╔════╝██╔═══██╗████╗  ██║██╔════╝██╔═══██╗██║     ██╔════╝
███████║ ╚███╔╝ ██║██║   ██║    ██║     ██║   ██║██╔██╗ ██║███████╗██║   ██║██║     █████╗
██╔══██║ ██╔██╗ ██║██║   ██║    ██║     ██║   ██║██║╚██╗██║╚════██║██║   ██║██║     ██╔══╝
██║  ██║██╔╝ ██╗██║╚██████╔╝    ╚██████╗╚██████╔╝██║ ╚████║███████║╚██████╔╝███████╗███████╗
╚═╝  ╚═╝╚═╝  ╚═╝╚═╝ ╚═════╝      ╚═════╝ ╚═════╝ ╚═╝  ╚═══╝╚══════╝ ╚═════╝ ╚══════╝╚══════╝
\033[0m
\033[90m  ASC 606 Revenue Recognition Agent | KPMG Handbook Dec 2025 | type 'help' or 'exit'\033[0m
"""

from core.file_context import FileContext, CONTRACT_EXTS, SESSION_CONTEXT

SUPPORTED_EXTS = CONTRACT_EXTS   # kept for backwards compat

HELP_TEXT = """
\033[1mWhat this agent does:\033[0m
  Analyzes contracts for ASC 606 compliance, creates Excel models, writes audit memos.
  Knowledge base: KPMG Revenue for Software and SaaS Handbook (Dec 2025, 774 pages).

\033[1mExample tasks:\033[0m
  analyze C:/Users/AXIO/contracts/acme_deal.pdf
  analyze C:/Users/AXIO/contracts/acme_deal.pdf and create the full allocation schedule and memo
  analyze this SaaS contract: [paste contract description]
  create an allocation schedule for a $500k contract with SaaS ($300k/yr) and implementation ($200k)
  build a deferred revenue rollforward for Q1-Q4 2025 with 3 contracts
  model variable consideration: base $1M with 20% bonus if ARR target hit
  write an ASC 606 memo for a contract modification adding 2 new users at $50k

\033[1mFile loading — three ways:\033[0m
  browse          Open folder picker dialog  (select a folder, all contracts load)
  browse files    Open file picker dialog    (select one or more files)
  load <path>     Type a folder or file path manually
  loaded          Show currently loaded files
  unload          Clear all loaded files
  analyze         Run full ASC 606 report stack on all loaded contracts

\033[1mOther commands:\033[0m
  tools        list all available tools
  outputs      list files created in this session
  model <name> switch model (default: qwen3.6:latest)
  help         show this message
  exit         quit

\033[1mOutput location:\033[0m  {}\033[0m
""".format(OUTPUT_DIR)

def should_use_claude(task: str) -> bool:
    """Auto-route to Claude API for PDF tasks, complex multi-step analysis, or --claude flag."""
    # Respect the --claude / FORCE_CLAUDE=1 flag set by axio.py
    if os.environ.get("FORCE_CLAUDE", "").strip() in ("1", "true", "yes"):
        return True
    t = task.lower()
    return any(trigger in t for trigger in CLAUDE_TRIGGERS)


# _scan_contracts replaced by core.file_context.FileContext — see main()


def _build_full_analysis_prompt(contract_paths: list[Path]) -> str:
    """Build the agent prompt that drives the full ASC 606 report stack."""
    paths_block = "\n".join(f"  - {p}" for p in contract_paths)
    return (
        f"Run the FULL ASC 606 / IFRS 15 report stack for every contract file listed below.\n\n"
        f"CONTRACT FILES TO ANALYZE:\n{paths_block}\n\n"
        f"For EACH contract file:\n"
        f"  1. Use read_pdf (for .pdf) or read_file (for .txt/.md/.csv/.docx) to extract the text\n"
        f"  2. Call analyze_contract on the extracted text to identify POs, VC flags, and risk areas\n"
        f"  3. Call create_allocation_schedule to produce the SSP allocation + revenue waterfall Excel\n"
        f"  4. Call create_variable_consideration_model if any variable consideration was detected\n"
        f"  5. Call create_contract_modification_analysis if any amendment / modification language exists\n"
        f"  6. Call create_deferred_revenue_schedule across all contracts once individual analyses are done\n"
        f"  7. Call write_memo to produce a complete audit-ready ASC 606 technical memo\n\n"
        f"Name every output file with the contract filename as prefix (e.g. acme_allocation.xlsx).\n"
        f"Reference specific ASC 606 paragraph numbers and KPMG Handbook sections throughout.\n"
        f"After all contracts are processed, call list_outputs to confirm all files were created."
    )


def main():
    print(BANNER)
    api_key   = os.environ.get("ANTHROPIC_API_KEY", "")
    local_only = os.environ.get("LOCAL_ONLY", "").strip() in ("1", "true", "yes")
    # Under LOCAL_ONLY the cloud path is deactivated: never auto-upgrade to Claude.
    api_ready = bool(api_key) and not local_only
    force_local = False   # set True with 'model local' command

    model = AGENT_MODEL
    if local_only:
        print(f"  Model    : \033[36m{model}\033[0m  (local-only — runs fully on-device)")
        print(f"  Claude API: \033[33mOFF (local-only)\033[0m")
    else:
        print(f"  Model    : \033[36m{model}\033[0m  (auto-upgrades to Claude for PDF/complex tasks)")
        if api_ready:
            print(f"  Claude API: \033[32mReady\033[0m  ({CLAUDE_MODEL})")
        else:
            print(f"  Claude API: \033[33mNot set — PDF analysis will be slow on local models\033[0m")
    print(f"  Outputs  : {OUTPUT_DIR}")
    print(f"  KB       : \033[36mKPMG Revenue for Software & SaaS Handbook, Dec 2025\033[0m\n")

    ctx = SESSION_CONTEXT   # session-wide singleton — shared with Cowork / Code / Chat

    while True:
        loaded_label = f"\033[90m[{ctx.count} contracts]\033[0m " if ctx.count else ""
        try:
            task = input(f"\033[1;35mREVREC>\033[0m {loaded_label}").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nBye.")
            break

        if not task:
            continue
        lower = task.lower()

        if lower == "exit":
            print("Bye.")
            break
        elif lower == "help":
            print(HELP_TEXT)
        elif lower == "tools":
            print("\n\033[1mAvailable tools:\033[0m")
            for t in TOOLS:
                fn = t["function"]
                print(f"  \033[35m{fn['name']:<42}\033[0m {fn['description'][:60]}")
            print()
        elif lower == "outputs":
            print(tool_list_outputs())

        # ── file loading ──────────────────────────────────────────────────
        elif lower == "browse":
            print(ctx.load_browse_folder())
            if ctx.count:
                print(f"  \033[90mType \033[0m\033[35manalyze\033[0m\033[90m to run the full ASC 606 stack.\033[0m")

        elif lower in ("browse files", "browse file"):
            print(ctx.load_browse_files())
            if ctx.count:
                print(f"  \033[90mType \033[0m\033[35manalyze\033[0m\033[90m to run the full ASC 606 stack.\033[0m")

        elif lower.startswith("load "):
            print(ctx.load_path(task[5:].strip()))
            if ctx.count:
                print(f"  \033[90mType \033[0m\033[35manalyze\033[0m\033[90m to run the full ASC 606 stack.\033[0m")

        elif lower in ("loaded", "contracts"):
            print(ctx.list_str())

        elif lower in ("unload", "clear", "clear contracts"):
            print(ctx.clear())

        # ── analyze all loaded contracts ──────────────────────────────────
        elif lower == "analyze":
            if not ctx.count:
                print("  \033[33mNo contracts loaded.  Use \033[35mbrowse\033[0m\033[33m or \033[35mload <path>\033[0m\033[33m first.\033[0m")
            else:
                prompt = _build_full_analysis_prompt(ctx.files)
                use_claude = api_ready and not force_local and should_use_claude(prompt)
                print(f"  \033[90m  routing: {'Claude API' if use_claude else model} | {ctx.count} contract(s)\033[0m")
                if use_claude:
                    run_agent_claude(prompt)
                else:
                    run_agent(prompt, model)

        # ── model switching ───────────────────────────────────────────────
        elif lower == "model claude":
            force_local = False
            print(f"  \033[32mForced to Claude API ({CLAUDE_MODEL})\033[0m")
        elif lower == "model local":
            force_local = True
            print(f"  \033[33mForced to local model ({model}) — PDF tasks may timeout\033[0m")
        elif lower.startswith("model "):
            model = task[6:].strip()
            force_local = True
            print(f"  Model set to: \033[36m{model}\033[0m")

        # ── freeform task → agent ─────────────────────────────────────────
        else:
            final_task = ctx.inject(task, mode="list") if ctx.count else task
            use_claude = api_ready and not force_local and should_use_claude(final_task)
            if use_claude:
                print(f"  \033[90m  routing: Claude API\033[0m")
                run_agent_claude(final_task)
            else:
                run_agent(final_task, model)

if __name__ == "__main__":
    main()
