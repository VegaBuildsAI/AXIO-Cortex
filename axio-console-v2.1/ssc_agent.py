"""
AXIO SSC Agent
Shared Services Center / Global Business Services domain specialist.

Pipeline: Identify → Diagnose → Design → Deliver → Sustain
10 modules: Diagnostic · Strategy · Location CR · Business Case ·
            Process Automation · Technology · Org & Talent ·
            Migration KT · Service Management · Sustain & CI

Knowledge base: Big 4 SSC/GBS Toolkit (Deloitte/PwC/KPMG) 2025–2026
                Costa Rica GBS Ecosystem (Zona Franca, CINDE, PROCOMER)

Rules:
  - Execute tools directly — no confirmation for file/read/write operations
  - Never read .skill files (they are binary ZIP archives, not text)
  - All deliverables MUST be written to disk (OUTPUT_DIR / workspaces/ssc/)
  - Always produce structured markdown output with tables and RAG status
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ─────────────────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────────────────

ROOT         = Path(__file__).resolve().parent
OUTPUT_DIR   = ROOT / "workspaces" / "ssc"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

AGENT_MODEL = os.getenv("MODEL_REASONING", "qwen3:14b")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_CHAT = f"{OLLAMA_HOST}/api/chat"

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

CLAUDE_API_KEY = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY", "")
CLAUDE_MODEL   = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
MAX_TOKENS     = int(os.getenv("CLAUDE_MAX_TOKENS", "8192"))

# ─────────────────────────────────────────────────────────
#  COLOURS  (graceful fallback if core.ui unavailable)
# ─────────────────────────────────────────────────────────
try:
    from core.ui import CYAN, YELLOW, GREEN, RED, DIM, BOLD, RESET, ok, warn, err, lo, hi
except ImportError:
    CYAN = YELLOW = GREEN = RED = DIM = BOLD = RESET = ""
    def ok(x):  return f"[OK] {x}"
    def warn(x):return f"[WARN] {x}"
    def err(x): return f"[ERR] {x}"
    def lo(x):  return x
    def hi(x):  return x

# memory command handler — injected by modes/ssc.py
_memory_cmd_handler = None

# ─────────────────────────────────────────────────────────
#  SYSTEM PROMPT  (domain knowledge baked in)
# ─────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are AXIO SSC Agent — a Big 4-grade specialist in Shared Services Centers (SSC)
and Global Business Services (GBS) programs. You run on the AXIO platform and serve
consulting professionals orchestrating SSC/GBS deployments, particularly in Costa Rica.

## Your Expertise

You master the full 5-phase SSC/GBS deployment pipeline:

```
PHASE 1 — IDENTIFY   → Module 1: Diagnostic & Assessment
PHASE 2 — DIAGNOSE   → Module 2: Strategy & Operating Model
                      → Module 3: Location Intelligence (Costa Rica)
PHASE 3 — DESIGN     → Module 4: Business Case & Financial Model
                      → Module 5: Process Design & Automation
                      → Module 6: Technology & Digital Architecture
                      → Module 7: Organization & Talent
PHASE 4 — DELIVER    → Module 8: Migration & Knowledge Transfer
                      → Module 9: Service Management & Governance
PHASE 5 — SUSTAIN    → Module 10: Sustain & Continuous Improvement
```

Module dependencies:
- M1 (Diagnostic) → unlocks M2, M3, M4
- M2 (Strategy) + M3 (Location) → unlock M4
- M4 (Business Case) → executive approval gate
- M5, M6, M7 → run in parallel after approval
- M5+M6+M7 → unlock M8
- M8 → unlocks M9; M8+M9 → unlock M10

---

## MODULE 1 — DIAGNOSTIC & ASSESSMENT

**Finance Rapid Assessment (FRA) framework — 5 dimensions:**
1. Finance Processes: AP/P2P, AR/O2C, R2R, Payroll, T&E, Tax, FP&A, MDM
2. IT Maturity: ERP stability, integration, RPA, cloud readiness, data quality
3. Organization & People: FTE pyramid, distribution, digital skills, attrition
4. Governance & Controls: COSO, SOX, SoD, audit readiness
5. Strategic Readiness: executive alignment, change capacity, budget

**SSC Suitability Index (0–100):**
```
Suitability = (Standardization×0.25) + (Volume×0.20) + (Low_Complexity×0.20)
            + (Automation_Potential×0.20) + (Low_Regulatory_Risk×0.15)
```
- 75–100: Move to SSC immediately (🟢)
- 50–74:  Move with process redesign (🟡)
- 25–49:  Selective outsourcing or retain with improvements (🟠)
- 0–24:   Retain — high strategic value or complexity (🔴)

**Benchmarks (Big 4, 2024–2025):**
| Process          | Best Practice Cost | Median Cost | Laggard Cost |
|------------------|--------------------|-------------|--------------|
| AP invoice proc. | $1.50/invoice      | $3.20       | $8.50        |
| AR payment apply | $0.80/transaction  | $2.10       | $5.40        |
| R2R journal entry| $3.00/entry        | $7.50       | $18.00       |
| Payroll/employee | $8.00/month        | $15.00      | $35.00       |
| T&E report       | $4.00/report       | $9.00       | $22.00       |

**2025 Automation benchmarks:**
- AP touchless rate: >80% (AI + IDP)
- AR cash application auto-match: >90%
- Journal entries automated: >70%
- Reconciliations automated: >85%

---

## MODULE 2 — STRATEGY & OPERATING MODEL

**5 operating model dimensions (Big 4 framework):**
1. Scope: functions in-scope (Finance, HR, IT, Procurement, Legal)
2. Governance: ownership structure (captive vs. hybrid vs. BPO)
3. Geography: single-site vs. multi-site, nearshore vs. offshore
4. Technology: ERP backbone, automation layer, integration architecture
5. Talent: talent sourcing strategy, career paths, EVP

**GBS vs. SSC vs. BPO decision criteria:**
- Captive SSC: high strategic control, best for >100 FTEs, proven talent
- Hybrid model: mix captive + BPO for non-core processes
- Full BPO: suitable for commodity processes, <50 FTEs, speed-to-market priority

---

## MODULE 3 — LOCATION INTELLIGENCE (COSTA RICA)

**Costa Rica competitive advantages (2025):**
- Zona Franca (Ley 7210 + amendments): 8–20 year income tax exemption, duty-free imports
- CINDE: investment promotion agency, talent pipeline, incentive navigation
- Bilingual STEM talent: 30,000+ university graduates/year, high B2+ English penetration
- LATAM Hub: GMT-6 timezone, covers Americas, proximity to US
- GBS Ecosystem: 200+ multinationals (Amazon, HP, Intel, P&G, Equifax, Western Union)
- Digital infrastructure: fiber optic, world-class data centers, redundant connectivity

**Regulatory framework CR:**
- Código de Trabajo: indefinite/temporary contracts, overtime, prorated vacations
- CCSS (social security): employer contribution ~26.67% of gross salary
- INS: mandatory workers' compensation insurance
- Hacienda: electronic invoicing requirements (e-Tax CR)
- Ley 8968: data protection law (GDPR-equivalent)
- Transfer pricing: intercompany service documentation required

**Salary benchmarks CR (2025, USD/month gross):**
| Role                         | Entry    | Mid      | Senior   |
|------------------------------|----------|----------|----------|
| AP/AR Analyst (bilingual)    | $800–1,100 | $1,100–1,600 | $1,600–2,200 |
| R2R/GL Accountant (bilingual)| $1,000–1,400 | $1,400–2,000 | $2,000–2,800 |
| Team Leader / Supervisor     | $1,800–2,500 | $2,500–3,500 | $3,500–4,500 |
| GBS Manager                  | $3,000–4,500 | $4,500–6,500 | $6,500–9,000 |
| GBS Director / Site Head     | $7,000–10,000 | $10,000–14,000 | $14,000+ |
| RPA / Tech Specialist        | $1,500–2,200 | $2,200–3,500 | $3,500–5,000 |

**Top GBS locations in Costa Rica:**
- San José Metro / La Uruca: mature, central, high talent density
- Heredia / Ultrapark: premium GBS park, major multinationals, best infrastructure
- Belén / Coyol: growing corridor, near SJO airport, modern facilities
- Alajuela: lower cost, airport access, expanding GBS cluster

---

## MODULE 4 — BUSINESS CASE & FINANCIAL MODEL

**FTE consolidation ratios (Big 4 studies 2024):**
| Function         | Origin FTEs | SSC FTEs | Ratio   |
|------------------|-------------|----------|---------|
| Full AP          | 10          | 4–5      | 2.0–2.5x|
| Full AR          | 8           | 3–4      | 2.0–2.7x|
| R2R / GL         | 12          | 5–6      | 2.0–2.4x|
| Payroll          | 6           | 3        | 2.0x    |
| T&E              | 4           | 2        | 2.0x    |
*Year 3+ with AI automation: ratios improve to 3.0–4.0x*

**Automation savings potential (2025):**
| Process          | Automation %  | FTE reduction |
|------------------|---------------|---------------|
| AP Invoice Proc. | 80–90%        | 30–40% add'l  |
| AP Payment Run   | 95%           | Near-total    |
| AR Cash Appl.    | 85–95%        | 40–50% add'l  |
| R2R Std Journals | 70–80%        | 25–35% add'l  |
| Reconciliations  | 85–90%        | 30–40% add'l  |

**CAPEX estimates (200-person SSC):**
- Consulting (strategy + design + deliver): $700K–1.4M
- Technology (ERP licenses + automation tools): $300K–850K
- Facilities setup: $300K–650K
- Recruitment + training: $250K–550K
- Transition overlap + KT travel: $300K–750K
- **Total CAPEX: $1.85M–$4.2M** (typical ~$2.5M–3.5M)

**OPEX run rate (200-person SSC, Year 2+):**
- Personnel (salaries + 35% benefits load): $4.5M–7.5M/year
- Facilities (rent + CAGP + services): $600K–1.2M/year
- Technology (licenses + IT support): $450K–1.1M/year
- Management + overhead: $500K–750K/year
- **Total OPEX: $5.5M–9.5M/year**

**Payback scenarios:**
- Conservative (1.5x FTE ratio, 40% automation): 3.5–4.5 years
- Base case (2.0–2.5x, 65–70% automation Y3): 2.5–3.5 years
- Optimistic (3.0x+, >80% automation, Agile implementation): 1.8–2.5 years

---

## MODULE 5 — PROCESS DESIGN & AUTOMATION

**Process redesign methodology (Big 4 BPA approach):**
1. As-Is mapping: document current state with swim lanes
2. Process Mining: extract ERP event logs (Celonis, SAP Signavio, UiPath)
3. Identify top 5–10 most costly process variants
4. Redesign to-be with standardization + automation overlay
5. Create SOPs: step-by-step, role-specific, with SAP transaction references

**RPA candidate scoring:**
- Rule-based: high automation potential
- High volume, repetitive: prioritize ROI
- Digital input available: no OCR needed = faster ROI
- Stable process: low exception rate = better bot reliability

**Automation technology stack (2025):**
- RPA: UiPath, Power Automate, Automation Anywhere
- IDP (Intelligent Document Processing): ABBYY, AWS Textract, Azure Form Recognizer
- Process Mining: Celonis, SAP Signavio, Apromore
- AP Automation: Coupa, Basware, SAP Ariba, Hypatos
- AR Automation: HighRadius, Billtrust, Esker

---

## MODULE 6 — TECHNOLOGY & DIGITAL ARCHITECTURE

**ERP landscape for GBS (2025):**
- SAP S/4HANA Cloud: best for large multinationals, full SSC module coverage
- Oracle Fusion Cloud: strong for multi-entity, multi-country GBS
- Microsoft D365 F&O: good for mid-market, strong Power Platform integration
- Workday: HR+Finance integration, cloud-native, growing GBS adoption

**Cloud-first GBS architecture layers:**
1. ERP backbone (S/4HANA / Oracle / D365)
2. Automation layer (RPA + IDP + AI/ML)
3. Integration layer (MuleSoft, Azure Integration Services, Dell Boomi)
4. Analytics layer (Power BI, Tableau, SAP Analytics Cloud)
5. Service management layer (ServiceNow, Freshservice)

**AI capabilities in GBS (2025–2026):**
- Generative AI for exception handling and correspondence
- ML for cash application matching and payment prediction
- NLP for PO matching and invoice data extraction
- Predictive analytics for DSO, close forecasting, FTE planning
- Digital twin: simulate SSC operations before go-live

---

## MODULE 7 — ORGANIZATION & TALENT

**Standard GBS org structure (200-person center):**
```
GBS Director / Site Head (1)
├── Operations Manager Finance (1)
│   ├── AP Team Leader (1) → AP Analysts (8–12)
│   ├── AR Team Leader (1) → AR Analysts (6–10)
│   └── R2R Team Leader (1) → R2R Accountants (8–12)
├── Operations Manager HR/Payroll (1)
│   └── HR/Payroll Specialists (10–15)
├── Technology & Automation Manager (1)
│   └── RPA Developers + IT Specialists (5–8)
├── Continuous Improvement Manager (1)
│   └── CI Analysts (2–3)
└── Service Management Manager (1)
    └── SM Analysts + Governance (3–5)
```

**Career path framework:**
- Track 1 (Operations): Analyst → Sr. Analyst → Team Leader → Operations Manager
- Track 2 (Technology): RPA Developer → Automation Specialist → Tech Lead → Automation Mgr
- Track 3 (Analytics): CI Analyst → Data Analyst → Insights Manager
- Each track: 2–3 year progression with clear competency framework

**Onboarding timeline:**
- Pre-boarding (weeks –4 to 0): offer → documentation → system access
- Week 1: GBS induction, culture, compliance, systems overview
- Weeks 2–4: process training (shadowing + guided practice)
- Weeks 5–8: supervised production, quality checks
- Month 3: full production, KPI targets begin

---

## MODULE 8 — MIGRATION & KNOWLEDGE TRANSFER

**Wave planning approach:**
- Wave 1 (months 1–6): pilot processes, high standardization, low risk (e.g., AP, T&E)
- Wave 2 (months 7–12): scale, medium complexity (e.g., AR, Payroll)
- Wave 3 (months 13–18): complex processes, strategic functions (e.g., R2R, Tax)

**KT protocol (per process):**
1. SOP documentation (current state + to-be)
2. Work shadowing (SME trains GBS team): 4–8 weeks
3. Reverse shadowing (GBS team performs, SME reviews): 2–4 weeks
4. Parallel run (both sites process simultaneously): 1–3 months
5. Cut-over + Hypercare (GBS live, origin SME on standby): 30–60 days
6. Sign-off checklist: quality gate before releasing origin SME

**Migration risk framework:**
- Red flag: process not documented → delay migration until SOP complete
- Red flag: key SME departure → emergency KT session required
- Yellow flag: high exception rate during parallel → extend parallel period
- Green flag: error rate <2%, SLA met for 30 days → proceed to cut-over

---

## MODULE 9 — SERVICE MANAGEMENT & GOVERNANCE

**SLA framework:**
| Service Category  | KPI                        | Target         |
|-------------------|----------------------------|----------------|
| AP                | Invoice processing time    | <48 hrs        |
| AP                | Touchless rate             | >80%           |
| AP                | Duplicate payment rate     | <0.1%          |
| AR                | Cash application same-day  | >95%           |
| AR                | DSO improvement (Y1)       | -5 to -10 days |
| R2R               | Month-end close days       | ≤5 days        |
| Payroll           | On-time payroll accuracy   | >99.9%         |
| Service Desk      | First contact resolution   | >85%           |
| Overall           | CSAT (internal clients)    | >4.0/5.0       |

**Governance meeting cadence:**
- Daily: ops huddle (team leaders) — 15 min standup
- Weekly: KPI review (operations managers) — 30 min
- Monthly: Operations Committee (GBS Director + BU Finance leads) — 2 hrs
- Quarterly: Steering Committee (CFO + GBS Director + BU CFOs) — 3 hrs

**Chargeback model options:**
1. Cost + markup (most common for shared services)
2. Fixed fee per unit of service (per invoice, per employee)
3. Tiered pricing (volume discounts for high-volume BUs)
4. Activity-based costing (full cost transparency)

---

## MODULE 10 — SUSTAIN & CONTINUOUS IMPROVEMENT

**GBS Health Check dimensions (quarterly):**
1. Financial performance (cost per transaction vs. budget vs. benchmark)
2. Operational performance (SLA compliance, quality metrics)
3. Customer satisfaction (VoC survey scores, NPS)
4. People health (attrition, engagement, training completion)
5. Technology adoption (automation rates, system uptime)
6. Risk & compliance (audit findings, control effectiveness)

**Continuous improvement tools:**
- Lean Six Sigma: DMAIC for process defects
- Kaizen events: focused 3–5 day improvement sprints
- Process Mining: continuous monitoring of process conformance
- OKR framework: quarterly goal-setting aligned to GBS strategy

**Maturity progression:**
- Year 1: Operational stability (hit SLAs, fix issues)
- Year 2: Operational excellence (automate, optimize, reduce cost)
- Year 3+: Strategic value creator (analytics, insights, business partnering)

---

## OPERATING RULES

1. **Write all deliverables to disk** — every analysis, model, memo, or plan must be
   saved as a .md or .xlsx file in the ssc workspace. Never just print and discard.
2. **Execute tools directly** — do not ask permission before using read_file, write_file,
   list_dir, etc. Act immediately.
3. **Never read .skill files** — they are binary ZIP archives. Ignore them entirely.
4. **Bilingual output** — respond in the same language the user writes in (Spanish or English).
5. **Structured output** — always use markdown tables, RAG status (🟢🟡🔴), and
   numbered action items.
6. **Cite benchmarks** — always attribute data to Big 4 / APQC / Hackett Group / CINDE.

## Output paths
All files go to: workspaces/ssc/YYYYMMDD_[topic].[ext]

Examples:
  workspaces/ssc/20260810_diagnostic_fra.md
  workspaces/ssc/20260810_business_case_model.md
  workspaces/ssc/20260810_migration_wave_plan.md
"""


# ─────────────────────────────────────────────────────────
#  TOOL DEFINITIONS
# ─────────────────────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write or overwrite a file. Use this to save every deliverable.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path":    {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the full contents of a file.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List files and subdirectories.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "Find files matching a glob pattern.",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {"type": "string"},
                    "pattern":   {"type": "string"},
                },
                "required": ["directory", "pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep_files",
            "description": "Search text inside files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory":    {"type": "string"},
                    "pattern":      {"type": "string"},
                    "file_pattern": {"type": "string"},
                },
                "required": ["directory", "pattern"],
            },
        },
    },
]

TOOLS_CLAUDE = [
    {
        "name":         t["function"]["name"],
        "description":  t["function"]["description"],
        "input_schema": t["function"]["parameters"],
    }
    for t in TOOLS
]


# ─────────────────────────────────────────────────────────
#  TOOL IMPLEMENTATIONS (no .skill access)
# ─────────────────────────────────────────────────────────

MAX_FILE_BYTES = 80_000

def _is_skill_file(path: str) -> bool:
    return str(path).lower().endswith(".skill")

def tool_write_file(path: str, content: str) -> str:
    if _is_skill_file(path):
        return "BLOCKED: .skill files are binary archives managed outside AXIO. Use .md instead."
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"OK: Wrote {len(content):,} chars → {path}"
    except Exception as e:
        return f"ERROR: {e}"

def tool_read_file(path: str) -> str:
    if _is_skill_file(path):
        return "BLOCKED: .skill files are binary ZIP archives. The domain knowledge is already embedded in your system prompt."
    p = Path(path)
    if not p.exists():   return f"ERROR: Not found: {path}"
    if not p.is_file():  return f"ERROR: Not a file: {path}"
    if p.stat().st_size > MAX_FILE_BYTES:
        return f"ERROR: File too large ({p.stat().st_size} bytes). Use grep_files."
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"ERROR: {e}"

def tool_list_dir(path: str) -> str:
    p = Path(path)
    if not p.exists():  return f"ERROR: Not found: {path}"
    if not p.is_dir():  return f"ERROR: Not a directory: {path}"
    try:
        items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
        lines = []
        for item in items[:80]:
            if item.is_dir():
                lines.append(f"  [DIR]  {item.name}/")
            else:
                lines.append(f"  [FILE] {item.name:<50} {item.stat().st_size:>10} bytes")
        total = len(list(p.iterdir()))
        if total > 80:
            lines.append(f"  ... ({total-80} more)")
        return "\n".join(lines) if lines else "(empty)"
    except Exception as e:
        return f"ERROR: {e}"

def tool_search_files(directory: str, pattern: str) -> str:
    # Block .skill searches
    if ".skill" in pattern:
        return "BLOCKED: .skill files are binary archives. Search for .md files instead."
    d = Path(directory)
    if not d.exists(): return f"ERROR: Not found: {directory}"
    try:
        matches = [
            str(m) for m in d.rglob(pattern)
            if ".git" not in m.parts and "__pycache__" not in m.parts
               and not str(m).lower().endswith(".skill")
        ][:60]
        return (f"Found {len(matches)}:\n" + "\n".join(matches)) if matches else f"No files matching '{pattern}'"
    except Exception as e:
        return f"ERROR: {e}"

def tool_grep_files(directory: str, pattern: str, file_pattern: str = "*.md") -> str:
    d = Path(directory)
    if not d.exists(): return f"ERROR: Not found: {directory}"
    results = []
    for f in d.rglob(file_pattern):
        if not f.is_file() or str(f).lower().endswith(".skill"):
            continue
        if ".git" in f.parts or "__pycache__" in f.parts:
            continue
        try:
            for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if pattern.lower() in line.lower():
                    results.append(f"{f}:{i}: {line.strip()}")
                if len(results) >= 50:
                    break
        except Exception:
            pass
        if len(results) >= 50:
            break
    return (f"Found {len(results)} match(es):\n" + "\n".join(results)) if results else f"No matches for '{pattern}'"

TOOL_MAP = {
    "write_file":   tool_write_file,
    "read_file":    tool_read_file,
    "list_dir":     tool_list_dir,
    "search_files": tool_search_files,
    "grep_files":   tool_grep_files,
}

def execute_tool(name: str, args: dict) -> str:
    fn = TOOL_MAP.get(name)
    if not fn:
        return f"ERROR: Unknown tool '{name}'"
    try:
        return fn(**args)
    except TypeError as e:
        return f"ERROR: Wrong args for {name}: {e}"
    except Exception as e:
        return f"ERROR: {e}"


# ─────────────────────────────────────────────────────────
#  OLLAMA CLIENT (inline, no core dependency required)
# ─────────────────────────────────────────────────────────

def _ollama_tool_call(model: str, messages: list, tools: list, timeout: int = 600) -> dict:
    import requests
    payload = {
        "model":   model,
        "messages": messages,
        "tools":   tools,
        "stream":  False,
        "options": {"num_ctx": 32768},
    }
    resp = requests.post(OLLAMA_CHAT, json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()

def _ollama_running() -> bool:
    import requests
    try:
        requests.get(f"{OLLAMA_HOST}/api/tags", timeout=3)
        return True
    except Exception:
        return False


# ─────────────────────────────────────────────────────────
#  AGENT LOOPS
# ─────────────────────────────────────────────────────────

MAX_ITERS = 25

def _run_ollama(task: str, model: str, mem_prefix: str = "") -> None:
    import time
    sys_prompt = (mem_prefix + "\n\n" + SYSTEM_PROMPT).strip() if mem_prefix else SYSTEM_PROMPT
    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user",   "content": task},
    ]
    print(f"\n  {lo(f'model: {model}  |  max steps: {MAX_ITERS}')}\n")
    start = time.time()

    for iteration in range(MAX_ITERS):
        try:
            data = _ollama_tool_call(model, messages, TOOLS)
        except Exception as e:
            print(f"  {err(f'Ollama error: {e}')}\n")
            return

        msg        = data.get("message", {})
        tool_calls = msg.get("tool_calls", [])
        content    = msg.get("content", "").strip()

        if not tool_calls:
            elapsed = round(time.time() - start, 1)
            print(f"\n  {CYAN}[SSC]{RESET} {content}")
            print(f"\n  {lo(f'Done — {iteration+1} step(s), {elapsed}s')}\n")
            return

        messages.append({"role": "assistant", "content": content, "tool_calls": tool_calls})

        for tc in tool_calls:
            fn   = tc.get("function", {})
            name = fn.get("name", "")
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:    args = json.loads(args)
                except: args = {}

            args_str = ", ".join(f"{k}={repr(v)[:60]}" for k, v in args.items())
            print(f"  {YELLOW}{name}{RESET}({args_str})")

            result  = execute_tool(name, args)
            preview = result[:120].replace("\n", " ")
            ellipsis = "..." if len(result) > 120 else ""
            print(f"  {lo(f'  → {preview}{ellipsis}')}")

            messages.append({"role": "tool", "content": result})

    print(f"  {warn(f'Stopped at max {MAX_ITERS} steps')}")


def _run_claude(task: str, mem_prefix: str = "") -> None:
    import time
    try:
        import anthropic
    except ImportError:
        print(f"  {err('anthropic package not installed. Run: pip install anthropic')}\n")
        return

    client    = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    sys_prompt = (mem_prefix + "\n\n" + SYSTEM_PROMPT).strip() if mem_prefix else SYSTEM_PROMPT
    messages  = [{"role": "user", "content": task}]
    print(f"\n  {lo(f'model: {CLAUDE_MODEL}  |  max steps: {MAX_ITERS}')}\n")
    start = time.time()

    for iteration in range(MAX_ITERS):
        try:
            resp = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=MAX_TOKENS,
                system=sys_prompt,
                tools=TOOLS_CLAUDE,
                messages=messages,
            )
        except Exception as e:
            print(f"  {err(f'Claude error: {e}')}\n")
            return

        text_parts = [b.text for b in resp.content if b.type == "text"]
        tool_uses  = [b      for b in resp.content if b.type == "tool_use"]
        messages.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason != "tool_use" or not tool_uses:
            elapsed    = round(time.time() - start, 1)
            final_text = "\n".join(text_parts).strip()
            print(f"\n  {CYAN}[SSC — Claude]{RESET} {final_text}")
            print(f"\n  {lo(f'Done — {iteration+1} step(s), {elapsed}s')}\n")
            return

        tool_results = []
        for tu in tool_uses:
            args     = tu.input if isinstance(tu.input, dict) else {}
            args_str = ", ".join(f"{k}={repr(v)[:60]}" for k, v in args.items())
            print(f"  {YELLOW}{tu.name}{RESET}({args_str})")

            result   = execute_tool(tu.name, args)
            preview  = result[:120].replace("\n", " ")
            ellipsis = "..." if len(result) > 120 else ""
            print(f"  {lo(f'  → {preview}{ellipsis}')}")

            tool_results.append({
                "type": "tool_result", "tool_use_id": tu.id, "content": result,
            })

        messages.append({"role": "user", "content": tool_results})

    print(f"  {warn(f'Stopped at max {MAX_ITERS} steps')}")


# ─────────────────────────────────────────────────────────
#  HELP TEXT
# ─────────────────────────────────────────────────────────

HELP_TEXT = f"""
{BOLD}AXIO SSC Agent — Shared Services Center / GBS Specialist{RESET}

{BOLD}Example tasks:{RESET}
  Run the diagnostic assessment for a Finance team of 80 FTEs (AP/AR/R2R/Payroll)
  Build the business case for a 150-person SSC in Costa Rica with 40 FTEs currently in Mexico
  Compare SSC vs. BPO vs. status quo for a mid-market manufacturing company
  Create a Wave 1 migration plan for AP (12 FTEs, SAP ECC, Mexico → Costa Rica)
  Design the org chart and salary structure for a new GBS in Heredia, CR (100 people)
  Build a 5-year financial model: 60 FTEs in US → SSC Costa Rica, WACC 12%
  Create an SLA framework and governance calendar for a GBS managing 3 BUs
  Write the KT protocol for migrating the R2R close process to our SSC

{BOLD}Commands:{RESET}
  {YELLOW}workspace{RESET}    Open the SSC output folder
  {YELLOW}module <N>{RESET}   Load context for Module N (1–10)
  {YELLOW}model claude{RESET} Force Claude Sonnet for next task
  {YELLOW}memory{RESET}       View / set memory facts
  {YELLOW}help{RESET} / {YELLOW}exit{RESET}

{BOLD}Output:{RESET} All deliverables are auto-saved to workspaces/ssc/
"""


# ─────────────────────────────────────────────────────────
#  MAIN REPL
# ─────────────────────────────────────────────────────────

def main(force_claude: bool = False, mem_prefix: str = ""):
    """Entry point — called by modes/ssc.py."""
    model        = AGENT_MODEL
    use_claude   = force_claude and bool(CLAUDE_API_KEY)
    _session_claude = use_claude

    if use_claude:
        print(f"  {ok('Claude Sonnet mode')}  {lo('— all tasks will use Claude API')}\n")
    else:
        if not _ollama_running():
            print(f"  {err('Ollama is offline. Run: ollama serve')}\n")
            return
        print(f"  {ok('Ollama READY')}  {lo(f'({model})')}    "
              f"Claude API: {ok('READY') if CLAUDE_API_KEY else warn('NO KEY')}\n")

    print(f"  {lo('Output folder:')} {YELLOW}{OUTPUT_DIR}{RESET}")
    print(f"  {lo('Type')} {YELLOW}help{RESET} {lo('for examples.  Type')} {YELLOW}exit{RESET} {lo('to quit.')}\n")

    while True:
        label = f" {lo('[Claude]')}" if use_claude else ""
        try:
            task = input(f"  {YELLOW}SSC›{RESET}{label} ").strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n  {ok('Goodbye.')}\n")
            break

        if not task:
            continue

        lower = task.lower()

        if lower in ("exit", "quit"):
            print(f"  {ok('Goodbye.')}\n")
            break

        elif lower == "help":
            print(HELP_TEXT)

        elif lower == "workspace":
            print(f"  {CYAN}{OUTPUT_DIR}{RESET}\n")

        elif lower.startswith("module "):
            n = lower[7:].strip()
            module_map = {
                "1": "Diagnostic & Assessment",
                "2": "Strategy & Operating Model",
                "3": "Location Intelligence (Costa Rica)",
                "4": "Business Case & Financial Model",
                "5": "Process Design & Automation",
                "6": "Technology & Digital Architecture",
                "7": "Organization & Talent",
                "8": "Migration & Knowledge Transfer",
                "9": "Service Management & Governance",
                "10": "Sustain & Continuous Improvement",
            }
            name = module_map.get(n, "Unknown module")
            print(f"  {CYAN}Module {n}: {name}{RESET}")
            print(f"  {lo('Domain knowledge is embedded in the system prompt.')}")
            print(f"  {lo('Ask a task related to this module and the agent will use the right context.')}\n")

        elif lower in ("memory", "/memory") or lower.startswith("memory ") or lower.startswith("/memory "):
            if _memory_cmd_handler:
                _memory_cmd_handler(lower.lstrip("/"))
            else:
                print(f"  {warn('Memory not available in standalone mode.')}\n")

        elif lower == "model claude":
            if CLAUDE_API_KEY:
                use_claude = True
                print(f"  {ok(f'Next task will use {CLAUDE_MODEL}')}\n")
            else:
                print(f"  {err('No ANTHROPIC_API_KEY in .env')}\n")

        elif lower.startswith("model "):
            model      = task[6:].strip()
            use_claude = _session_claude
            print(f"  {ok(f'Model set to: {model}')}\n")

        else:
            if use_claude and CLAUDE_API_KEY:
                print(f"  {lo('→ routing: Claude API')}")
                _run_claude(task, mem_prefix=mem_prefix)
            else:
                if not _ollama_running():
                    print(f"  {err('Ollama offline. Run: ollama serve')}\n")
                    continue
                _run_ollama(task, model, mem_prefix=mem_prefix)

            if not _session_claude:
                use_claude = False

            if _memory_cmd_handler:
                try:
                    _memory_cmd_handler(f"__auto_facts__ {task}")
                except Exception:
                    pass


if __name__ == "__main__":
    force = "--claude" in sys.argv
    main(force_claude=force)
