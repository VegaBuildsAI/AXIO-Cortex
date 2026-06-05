# AXIO — Partner Presentation Talking Points
**Audience:** Business / Finance Partner (INCAE)
**Format:** 10-slide deck | ~20 minutes + Q&A
**Prepared by:** Michael Vega | msvv11@gmail.com | May 2026

---

## Slide 1 — The Problem
**Headline:** *Every AI conversation you've ever had started from zero.*

**What to say:**
Think about the last time you used ChatGPT or any AI tool. You explained your project. You gave context. You got an answer. You closed the window. The next day — you started over. The tool remembered nothing. This is not a minor inconvenience. It's a fundamental architectural flaw in how AI tools are built today. Every session is stateless. Every session is amnesiac. You're paying for intelligence that forgets you the moment you leave.

**Key point to land:** The problem isn't AI capability — it's AI memory.

---

## Slide 2 — The Insight
**Headline:** *The longer you use a tool, the better it should know you.*

**What to say:**
Every conversation contains signal. What you're working on, what decisions you've made, what problems you keep returning to. Today that signal evaporates. We asked: what if it didn't? What if AI sessions were cumulative — each one building on the last, getting smarter over time? That's the thesis behind AXIO.

**Key point to land:** This is a design choice, not a technical limitation.

---

## Slide 3 — What AXIO Is
**Headline:** *A local-first AI orchestration platform that remembers.*

**What to say:**
AXIO is not another chatbot. It's an operating layer — a platform that sits between you and multiple AI models, routing each task to the right one, and maintaining a persistent memory of everything you've worked on. Three principles: **Stateful** (it remembers), **Cumulative** (it gets smarter), **Sovereign** (your data stays on your machine).

**Key point to land:** AXIO is infrastructure, not just a product.

---

## Slide 4 — How the Memory Works (IOAF)
**Headline:** *Three layers of memory, always running.*

**What to say (keep it simple — no technical jargon):**
Imagine three filing systems working in parallel. The first is like a transcript — it records every conversation verbatim. The second is like a smart assistant who, at the end of every meeting, writes a summary and files it by topic — so next week you can say "what did we discuss about the Boone County contract?" and it finds the right session by *meaning*, not keyword. The third is like a contact card — it remembers facts: your name, your active projects, your preferences. All three load automatically when you start a new session.

**Key point to land:** Before you type your first word, AXIO already knows your context.

---

## Slide 5 — Four Specialized Modes
**Headline:** *One platform, four domain experts.*

**What to say:**
AXIO has four specialist modes, each with its own AI model assignment and toolset:
- **Chat** — general conversation with memory. Think of it as an assistant that actually remembers your projects.
- **Code** — an autonomous coding agent. It reads files, writes files, edits code. It builds things.
- **Cowork** — a file-aware workspace assistant. Point it at a folder; it indexes everything and routes each question intelligently.
- **RevRec** — and this is the one I want to show you specifically.

**Key point to land:** The platform grows with you — use one mode or all four.

---

## Slide 6 — The RevRec Agent (Your Demo Slide)
**Headline:** *ASC 606 / IFRS 15 revenue recognition, automated.*

**What to say:**
Revenue recognition under ASC 606 is one of the most time-consuming and error-prone tasks in enterprise finance. Our RevRec agent reads a contract PDF, identifies performance obligations, calculates transaction price allocations, builds deferred revenue schedules, and generates audit-ready Excel outputs — with full variable consideration and contract modification analysis. It has 17 specialized tools. It outputs directly to Excel. It runs in minutes, not days.

**Show:** The Contracts example folder — the four real-world contract PDFs and the corresponding Excel allocation schedules, deferred revenue models, and variable consideration analyses.

**Key point to land:** This is not a demo — these are real contract outputs from a working system.

---

## Slide 7 — Smart Routing: The Right Model for the Right Task
**Headline:** *Intelligent, cost-aware model orchestration.*

**What to say (business framing — avoid tech jargon):**
Not every question deserves an expensive AI model. We built a routing engine that reads your prompt and assigns it to the right tool — instantly. Exact arithmetic goes to a Python calculator (100% accurate, zero AI cost). Revenue analysis goes to the model that scored highest on ASC 606 benchmarks. Complex reasoning escalates to Claude. Simple questions stay local. The system decides — based on data, not guesswork.

**Key point to land:** You get the best answer at the lowest cost, automatically.

---

## Slide 8 — Sovereignty & Privacy
**Headline:** *Your data stays yours.*

**What to say:**
Every file AXIO generates — sessions, summaries, memories, audit logs — lives on your machine. No conversation history is sent to a cloud server. No vendor controls access to your own past sessions. The Anthropic Claude API is an optional escalation tier — powerful, but not the backbone. The backbone runs locally. This matters enormously for any organization handling sensitive financial contracts, client data, or proprietary analysis.

**Key point to land:** Enterprise-grade privacy without enterprise-grade complexity.

---

## Slide 9 — Built on Benchmarks, Not Assumptions
**Headline:** *Every routing decision is backed by data.*

**What to say:**
We didn't guess which AI model to use for which task. We built a benchmark engine. We ran four standardized tasks against every model in our fleet — coding, architecture, revenue analysis, and arithmetic. We scored every response with a rubric-based evaluator. When qwen3:14b scored 85/100 on revenue analysis and outperformed the coding model on ASC 606 tasks, we updated the routing table to match. The system learns from its own performance data.

**Key point to land:** AXIO is self-optimizing. The routing gets better as the benchmarks get richer.

---

## Slide 10 — What's Next & The Opportunity
**Headline:** *The architecture is in place. The data is accumulating.*

**What to say:**
AXIO v2.1 is a working, deployed platform. What we're building toward is something larger: a longitudinal record of how an organization thinks — what it builds, what problems it returns to, what it has already solved. That record becomes training data. It becomes a model that is genuinely fine-tuned to your domain vocabulary and decision patterns. The roadmap includes a web UI, multi-contract batch processing in RevRec, and cross-mode memory recall. But the foundation is already running.

**This is where you open the conversation:** What I'd love to understand is where you see the biggest friction in your work today — and whether AXIO's memory architecture or the RevRec capability is the angle most relevant to what you're building.

---

## Tips for the Meeting

**Lead with the problem, not the technology.** The forgetting problem lands with everyone. Start there.

**The RevRec demo is your strongest asset.** Show the real contract PDFs and real Excel outputs. That's a working product, not a pitch.

**Don't over-explain the architecture.** Slides 4 and 7 (memory + routing) should be brief. Say enough to show there's real engineering behind it, then move on. If they want depth, they'll ask.

**End with a question, not a close.** You met this person today — the goal of this meeting is to open the relationship, not close a deal. Find out what problem they're sitting on.

**Have the FigJam diagrams ready as a backup.** If they ask how the memory system works visually, the three FigJam boards are clean and impressive:
- Memory System: https://www.figma.com/board/iNJUG5sGf7YYCEJRV99IOv
- Routing Architecture: https://www.figma.com/board/NM2PhZHkCeRrhDF3cqnR0Y
- Four-Mode Workflow: https://www.figma.com/board/GTXZvCwuku1cf6UdBXDXvD

---

*Ready to build the slide deck? Approve this flow and I'll generate the full .pptx.*
