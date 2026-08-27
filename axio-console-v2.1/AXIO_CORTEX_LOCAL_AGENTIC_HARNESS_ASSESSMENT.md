# AXIO CORTEX — LOCAL AGENTIC CODE HARNESS ASSESSMENT

## Mission

Actúa como **Senior AI Systems Architect + Senior Software Engineer + Agentic Systems Researcher** dentro de **AXIO Code**.

Tu objetivo NO es validar mis ideas ni producir una respuesta optimista.

Tu objetivo es realizar una **auditoría técnica real, basada en evidencia**, del harness actual de AXIO Code y determinar qué cambios concretos pueden mejorar a **Gemma 4 12B** como motor local de coding agent / autonomous software-engineering agent.

Trabaja en **PLAN MODE** primero.

No implementes cambios hasta completar:
1. inspección del repositorio local,
2. investigación web,
3. revisión de código de repositorios externos,
4. comparación arquitectónica,
5. diagnóstico,
6. plan priorizado.

---

# 1. REGLAS DE EJECUCIÓN

## 1.1 Evidence-first

No asumas capacidades.

Toda recomendación debe estar respaldada por al menos una de estas fuentes:

- código del repositorio local AXIO,
- código fuente de repositorios GitHub estudiados,
- documentación oficial,
- benchmark reproducible,
- paper técnico,
- evidencia obtenida mediante ejecución o tests.

Distingue siempre:

```text
OBSERVED
INFERRED
EXTERNALLY VERIFIED
NOT VERIFIED
```

No presentes inferencias como hechos.

---

## 1.2 Usa las herramientas disponibles

Usa activamente las tools disponibles en AXIO Code.

Incluye cuando sean relevantes:

```text
read_file
search_files
list_dir
web_search
web_fetch
web_extract
run_command
run_tests
git_diff
git_status
github/repository tools disponibles
```

Si existe una herramienta específica para GitHub, úsala.

Si no existe, usa:

```text
web_search
web_fetch
web_extract
git clone
```

cuando la política/runtime lo permita.

No respondas diciendo que no tienes acceso a internet si las herramientas web están disponibles.

---

# 2. PRIMERA FASE — AUDITAR AXIO CODE

Antes de revisar proyectos externos, inspecciona el repositorio local de AXIO.

Identifica:

```text
agent loop
model adapter
Ollama integration
Claude integration
tool registry
tool schemas
tool descriptions
tool router
planner
Plan Mode
executor
verification gate
state management
conversation history
context management
skills
web tools
GitHub tools
shell execution
PowerShell execution
file editing
testing
error recovery
step limits
logging
telemetry
benchmark framework
```

Construye un mapa de arquitectura real.

No deduzcas la arquitectura solo por nombres de archivos.

Lee las implementaciones.

---

# 3. INVESTIGACIÓN EXTERNA OBLIGATORIA

Accede a cada uno de los siguientes repositorios.

No revises solamente README.

Inspecciona código fuente relevante.

## 3.1 mini-SWE-agent

Repository:

```text
https://github.com/SWE-agent/mini-swe-agent
```

Analiza:

```text
agent loop
environment abstraction
model adapter
message/history design
tool interface
execution loop
termination
sandbox/runtime
trajectory logging
token/context strategy
error handling
```

Pregunta crítica:

> ¿Qué hace mini-SWE-agent con menos complejidad que AXIO y por qué funciona?

---

## 3.2 SWE-agent

Repository:

```text
https://github.com/SWE-agent/SWE-agent
```

Investiga especialmente:

```text
Agent-Computer Interface
tool design
tool descriptions
command structure
environment interaction
observation handling
edit strategies
verification
trajectory management
```

Determina si las tools de AXIO están diseñadas como un buen ACI para un modelo de 12B.

---

## 3.3 OpenHands

Repository:

```text
https://github.com/OpenHands/OpenHands
```

Analiza:

```text
agent
runtime
actions
observations
event stream
state
sandbox
tool execution
planner/executor patterns
model abstraction
error recovery
```

No propongas copiar OpenHands completo.

Busca patrones reutilizables.

---

## 3.4 Cline

Repository:

```text
https://github.com/cline/cline
```

Analiza:

```text
Plan/Act
tool lifecycle
skills
rules
MCP
context management
approval model
execution state
headless execution
model provider abstraction
```

Compara directamente con AXIO Plan Mode.

---

## 3.5 Goose

Repository:

```text
https://github.com/block/goose
```

Analiza:

```text
model provider abstraction
agent engine
extensions
MCP
local model support
Ollama
tool discovery
session state
```

Determina qué separación arquitectónica debería adoptar AXIO.

---

## 3.6 OpenCode

Busca primero el repositorio oficial vigente.

No asumas que una URL antigua sigue siendo la correcta.

Analiza:

```text
Plan/Build
agent loop
Ollama integration
tool model
terminal execution
context management
provider abstraction
```

Compara:

```text
Gemma 4 + OpenCode
vs
Gemma 4 + AXIO Code
```

---

# 4. BENCHMARK / EVALUATION REPOS

Revisa código y metodología de los siguientes proyectos.

## 4.1 BFCL / Gorilla

```text
https://github.com/ShishirPatil/gorilla
```

Evalúa cómo medir en AXIO:

```text
Tool Selection Accuracy
Argument Accuracy
Invalid Tool Rate
Unnecessary Tool Rate
Tool Recovery Rate
Multi-call Accuracy
Parallel Tool Accuracy
Multi-turn Accuracy
Tool Hallucination Rate
```

Diseña una versión:

```text
AXIO-BFCL
```

orientada a las tools reales del sistema.

---

## 4.2 SWE-bench

```text
https://github.com/SWE-bench/SWE-bench
```

Analiza:

```text
evaluation harness
task format
containers
patch evaluation
test execution
scoring
Verified subset
```

Determina la forma mínima viable de ejecutar un subset local con Gemma 4.

---

## 4.3 Terminal-Bench

Busca el repositorio oficial actual de Terminal-Bench.

Analiza:

```text
task definition
environment
terminal interaction
grader
agent interface
runtime isolation
```

Determina si AXIO Code puede conectarse directamente o necesita un adapter.

---

## 4.4 Aider benchmark

```text
https://github.com/Aider-AI/aider
```

Investiga la carpeta/framework de benchmark.

Analiza especialmente:

```text
edit formats
pass rate
syntax errors
malformed responses
timeouts
lazy coding
test execution
```

Propón pruebas equivalentes para AXIO.

---

## 4.5 LiveCodeBench

```text
https://github.com/LiveCodeBench/LiveCodeBench
```

Separa claramente:

```text
MODEL CAPABILITY
```

de:

```text
AGENT HARNESS CAPABILITY
```

LiveCodeBench debe usarse principalmente para medir el modelo.

---

## 4.6 tau2-bench

```text
https://github.com/sierra-research/tau2-bench
```

Analiza:

```text
tool-agent interaction
policy adherence
state
multi-turn execution
task success
```

Determina qué conceptos son reutilizables en AXIO Code y AXIO RevRec.

---

## 4.7 Inspect AI

```text
https://github.com/UKGovernmentBEIS/inspect_ai
```

y:

```text
https://github.com/UKGovernmentBEIS/inspect_evals
```

Evalúa seriamente si Inspect AI puede convertirse en:

```text
AXIO CORTEX EVAL ENGINE
```

Revisa:

```text
model adapters
custom tools
agents
scorers
sandbox
MCP
local inference
eval datasets
logging
results
```

No recomiendes Inspect AI solamente porque parece conveniente.

Determina integración, esfuerzo, dependencias y limitaciones.

---

# 5. SKILLS ARCHITECTURE

Investiga:

```text
https://github.com/agentskills/agentskills
https://github.com/anthropics/skills
https://github.com/openai/skills
```

Analiza el estándar y las implementaciones.

Determina si AXIO debería adoptar una estructura compatible:

```text
skills/
  repository-analysis/
    SKILL.md
  python-debug/
    SKILL.md
  test-driven-fix/
    SKILL.md
  github-research/
    SKILL.md
  web-research/
    SKILL.md
  api-integration/
    SKILL.md
  mcp-development/
    SKILL.md
  verification/
    SKILL.md
```

Evalúa específicamente la separación:

```text
TOOL = capacidad ejecutable
SKILL = procedimiento / conocimiento operativo para combinar tools
```

---

# 6. TOOL ARCHITECTURE REVIEW

AXIO actualmente tiene aproximadamente 38 tools.

No asumas que más tools es mejor.

Evalúa experimentalmente tres estrategias:

```text
A. FULL TOOLSET
Gemma 4 + todas las tools disponibles

B. ROUTED TOOLSET
Gemma 4 + 6-12 tools seleccionadas dinámicamente

C. MINIMAL / TERMINAL-CENTRIC
Gemma 4 + conjunto mínimo similar a mini-SWE-agent
```

Mide:

```text
tool selection errors
wrong arguments
unnecessary calls
completion rate
steps required
token consumption
latency
recovery rate
task success
```

Determina si AXIO necesita:

```text
TOOL REGISTRY
      |
TASK CLASSIFIER
      |
TOOL ROUTER
      |
ACTIVE TOOL SUBSET
      |
MODEL
```

---

# 7. TOOL QUALITY / ACI AUDIT

Para cada tool importante de AXIO analiza:

```text
name
description
schema
argument clarity
overlap with other tools
preconditions
postconditions
side effects
failure behavior
recovery
verification
```

Identifica tools ambiguas o redundantes.

Clasifica cada tool:

```text
KEEP
RENAME
MERGE
SPLIT
RESTRICT
REMOVE
```

Ejemplo de estándar deseado:

```yaml
name: apply_patch

purpose: >
  Apply deterministic replacements to existing code.

use_when:
  - modifying existing implementation
  - exact target is known

do_not_use_when:
  - creating new files
  - target is ambiguous

requires:
  - file inspected first

postconditions:
  - inspect diff
  - run relevant verification

failure_recovery:
  - reread target
  - recompute patch
  - retry
```

---

# 8. AGENT LOOP REVIEW

Reconstruye el loop actual de AXIO desde el código.

Luego compáralo contra:

```text
USER TASK
    |
INTENT
    |
SKILL SELECTION
    |
TOOL SELECTION
    |
PLAN
    |
EXECUTE
    |
OBSERVE
    |
UPDATE STATE
    |
VERIFY
   / \
FAIL PASS
 |     |
REPLAN COMPLETE
```

Determina qué componentes faltan.

Evalúa:

```text
planning quality
execution state
observations
replanning
recovery
termination
verification
loop detection
no-progress detection
context growth
```

---

# 9. STEP BUDGET / LOOP CONTROL

Evalúa el actual:

```text
max_steps = 20
```

contra un esquema adaptativo:

```yaml
budget:
  simple:
    max_steps: 10

  normal:
    max_steps: 20

  complex:
    max_steps: 50

  benchmark:
    max_steps: 100

limits:
  repeated_tool_call: 3
  identical_error: 2
  no_progress_steps: 4
```

No implementes estos valores automáticamente.

Valídalos contra comportamiento real del código.

---

# 10. CONTEXT ENGINEERING

Gemma 4 12B es un modelo local.

La optimización de contexto es crítica.

Audita:

```text
system prompt size
tool schema token cost
number of exposed tools
conversation growth
tool output size
web content size
repository content
duplicate context
summarization
context pruning
retrieval
working memory
persistent memory
```

Diseña una política para evitar llenar el contexto con:

```text
38 tool schemas
raw logs
large files
web pages
duplicated source
```

Evalúa estrategias:

```text
dynamic tool exposure
tool-result compression
repository map
symbol retrieval
rolling summary
task state object
working memory
artifact references
```

---

# 11. MODEL ADAPTER REVIEW

Audita cómo AXIO llama a Ollama/Gemma.

Investiga documentación oficial actual de:

```text
Gemma 4
Ollama Gemma 4
Ollama tool calling
thinking configuration
context configuration
structured outputs
```

Verifica:

```text
context length
temperature
top_p
top_k
repeat penalty
thinking
tool calling format
JSON/schema enforcement
streaming
timeouts
keep_alive
```

No cambies parámetros basándote solo en intuición.

Propón experimentos A/B.

---

# 12. SKILL ROUTER

Evalúa implementar:

```text
TASK
 |
SKILL MATCHER
 |
LOAD ONLY RELEVANT SKILL
 |
TOOL ROUTER
 |
MODEL
```

Ejemplo:

```text
"fix failing pytest"
```

debería activar algo como:

```text
python-debug
test-driven-fix
```

y exponer solamente las tools relevantes.

---

# 13. VERIFICATION GATE

Audita el verification gate actual.

Debe poder responder con evidencia:

```text
What changed?
Why?
What was executed?
What passed?
What failed?
Was the task actually completed?
```

Evalúa gates como:

```text
syntax_check
unit_tests
targeted_tests
lint
type_check
git_diff
regression_check
task_specific_assertion
```

No fuerces todos los gates para todas las tareas.

Diseña verificación basada en riesgo/tipo de tarea.

---

# 14. OBSERVABILITY / TELEMETRY

Determina qué debe registrar AXIO por cada trajectory:

```json
{
  "task_id": "",
  "model": "",
  "skill": [],
  "tools_exposed": [],
  "tools_used": [],
  "steps": 0,
  "tool_errors": 0,
  "replans": 0,
  "tokens_input": 0,
  "tokens_output": 0,
  "latency_ms": 0,
  "verification": {},
  "success": false
}
```

Propón almacenamiento local simple primero.

Preferencia:

```text
JSONL
SQLite
```

antes de infraestructura compleja.

---

# 15. TRAINING / POST-TRAINING — NO IMPLEMENTAR TODAVÍA

Investiga:

```text
https://github.com/SWE-bench/SWE-smith
```

Determina cómo podría usarse posteriormente para:

```text
trajectory collection
synthetic tasks
SFT
LoRA
RL
```

Pero aplica esta regla:

> No recomendar fine-tuning mientras existan fallos importantes en harness, tools, context, verification o evaluation.

Primero optimizar sistema.

Después optimizar pesos.

---

# 16. ADVANCED BENCHMARKS

Investiga, pero clasifica como fase posterior:

```text
ProgramBench
CodeClash
AgentDojo
AssistantBench
The Agent Company
BrowseComp
```

Confirma repositorios oficiales antes de analizarlos.

No introduzcas estas dependencias si no agregan una capacidad evaluativa nueva.

---

# 17. BENCHMARK DESIGN PARA AXIO

Diseña:

```text
AXIO CORTEX EVAL SUITE
```

con capas separadas.

## Layer 1 — Model

```text
coding
reasoning
structured output
context
```

## Layer 2 — Tool Use

```text
selection
arguments
relevance
multi-tool
recovery
```

## Layer 3 — Repository Engineering

```text
navigation
localization
patching
testing
regression
```

## Layer 4 — Autonomous Agent

```text
planning
execution
replanning
verification
completion
```

## Layer 5 — Real AXIO Tasks

Crea pruebas reales del repositorio AXIO.

Ejemplos:

```text
find bug
fix failing test
add tool
refactor module
implement REST endpoint
research dependency
update configuration
diagnose runtime error
multi-file feature
```

---

# 18. COMPARACIÓN DE HARNESSES

El benchmark estratégico debe medir:

```text
SAME MODEL
SAME MACHINE
SAME TASK
DIFFERENT HARNESS
```

Comparar:

```text
Gemma 4 + AXIO Code
Gemma 4 + mini-SWE-agent
Gemma 4 + OpenCode
Gemma 4 + Cline
Gemma 4 + Goose
```

Cuando sea técnicamente posible.

Esto permite medir:

```text
HARNESS QUALITY
```

sin confundirlo con:

```text
MODEL QUALITY
```

---

# 19. MÉTRICAS PRINCIPALES

Produce como mínimo:

```text
Task Success Rate
Verified Completion Rate
Tool Selection Accuracy
Argument Accuracy
Tool Hallucination Rate
Unnecessary Tool Rate
Recovery Rate
Replan Rate
Average Steps
Median Steps
Latency
Token Consumption
Patch Success Rate
Test Pass Rate
Regression Rate
Context Utilization
```

---

# 20. CRITERIO SOTA

No declares:

```text
AXIO is SOTA
```

sin evidencia.

Define niveles.

## Level 0

```text
chat model with tools
```

## Level 1

```text
reliable tool-using coding assistant
```

## Level 2

```text
autonomous coding agent with verification
```

## Level 3

```text
benchmark-validated local software engineering agent
```

## Level 4

```text
competitive with leading local/open coding harnesses
```

## Level 5

```text
state-of-the-art local agentic system
```

Para Level 5 exige:

```text
reproducible benchmark results
public comparison methodology
same-model harness comparison
strong SWE/terminal benchmark performance
low tool failure rate
verified autonomous completion
```

---

# 21. PLAN MODE OUTPUT — OBLIGATORIO

Antes de modificar código entrega:

# A. CURRENT AXIO ARCHITECTURE

Arquitectura real encontrada.

# B. EXTERNAL REPOSITORY FINDINGS

Una tabla:

| Project | Pattern | Evidence | AXIO relevance | Adopt? |
|---|---|---|---|---|

# C. AXIO GAPS

Clasifica:

```text
CRITICAL
HIGH
MEDIUM
LOW
```

# D. TOOL AUDIT

```text
KEEP
RENAME
MERGE
REMOVE
NEW
```

# E. HARNESS ASSESSMENT

Score 0-100:

```json
{
  "agent_loop": 0,
  "planning": 0,
  "tool_architecture": 0,
  "tool_use": 0,
  "context_engineering": 0,
  "repository_reasoning": 0,
  "error_recovery": 0,
  "verification": 0,
  "observability": 0,
  "benchmark_readiness": 0,
  "overall": 0
}
```

# F. PRIORITIZED ROADMAP

Para cada cambio:

```text
Priority
Problem
Evidence
Proposed change
Files/modules affected
Expected impact
Implementation complexity
Risk
How to verify
```

# G. DO NOT CHANGE

Lista de componentes que ya están bien diseñados y no deben tocarse innecesariamente.

# H. IMPLEMENTATION PLAN

Orden exacto de implementación.

No hagas un rewrite completo si puede resolverse incrementalmente.

---

# 22. IMPLEMENTATION PRINCIPLES

Cuando llegue el momento de ejecutar cambios:

```text
READ BEFORE WRITE
MINIMAL PATCH
PRESERVE EXISTING ARCHITECTURE
NO UNNECESSARY DEPENDENCIES
NO SPECULATIVE REWRITES
TEST AFTER CHANGE
INSPECT DIFF
VERIFY REQUIREMENTS
```

Cada cambio debe justificar:

```text
WHY THIS CHANGE
WHY THIS FILE
WHY THIS DESIGN
HOW IT WAS VERIFIED
```

---

# 23. RESEARCH QUALITY

Para búsquedas web:

Prioridad de fuentes:

```text
1. official repositories
2. official documentation
3. papers
4. benchmark documentation
5. authoritative engineering sources
6. community sources only when necessary
```

Para cada repositorio:

```text
confirm repository identity
confirm recent activity
inspect source
inspect architecture
inspect docs
inspect benchmark claims
```

No uses estrellas de GitHub como evidencia de superioridad técnica.

---

# 24. FINAL DECISION FRAMEWORK

Después del research responde:

## KEEP

Qué mantener.

## IMPROVE

Qué mejorar.

## REPLACE

Qué reemplazar.

## ADD

Qué falta.

## DEFER

Qué no vale la pena todavía.

---

# 25. TARGET ARCHITECTURE

Usa esta arquitectura solamente como hipótesis inicial.

Debes validarla contra el código real:

```text
                    AXIO CORTEX
                         |
          +--------------+--------------+
          |                             |
      MODEL LAYER                  AGENT LAYER
          |                             |
  Gemma / Qwen / Claude        Planner / Executor
          |                             |
          +--------------+--------------+
                         |
                    SKILL ROUTER
                         |
                    TOOL ROUTER
                         |
                   TOOL REGISTRY
                         |
       +-----------------+----------------+
       |                 |                |
   filesystem           web              shell
   git/github           MCP             testing
       |                 |                |
       +-----------------+----------------+
                         |
                    RUNTIME
                         |
                 VERIFICATION GATE
                         |
                    TELEMETRY
                         |
                     AXIO EVAL
                         |
      +------------------+-------------------+
      |                  |                   |
     BFCL             SWE-bench        Terminal-Bench
```

No implementes esta arquitectura ciegamente.

Confirma qué piezas ya existen.

---

# 26. PRIMARY RESEARCH QUESTION

Toda la investigación debe finalmente responder:

> **¿Qué cambios medibles en el AXIO harness permiten que Gemma 4 12B alcance su máximo rendimiento como agente de software local, y cómo podemos demostrarlo experimentalmente frente al mismo modelo ejecutado en otros harnesses?**

---

# 27. SUCCESS CONDITION

No consideres terminado el assessment hasta haber producido:

```text
local architecture audit
external repo code review
tool/ACI audit
context audit
agent loop audit
verification audit
benchmark architecture
prioritized roadmap
measurable success criteria
implementation plan
```

La salida debe permitir ejecutar el siguiente paso sin volver a investigar desde cero.
