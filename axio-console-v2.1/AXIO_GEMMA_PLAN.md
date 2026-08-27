# AXIO Code — Fix & Skill Curation Plan (29 Tools)

> **⚠️ SUPERSEDED (2026-08-25).** This plan was written against the old standalone-Gemma
> codebase (`C:\Users\AXIO\axio-console\`, where `modes/gemma_code.py` was an 11-tool
> harness). The live project here has since been **unified**: `modes/gemma_code.py` is a
> shim over `modes/code.py`, the registry now has **38 tools**, and the audit fixes below
> (M1, M2, L1–L5) are already-done or not-applicable. Kept for history only — do not
> execute against this repo. See the implemented work: `core/web_intent.py`, the Web
> Evidence Gate in `modes/code.py`, the GitHub toolset in `core/code_tools/github_tools.py`,
> Chat/Cowork web-augmentation, and `skills/axio-coding/references/`.

## Para ejecutar en Claude Code Plan Mode
**Origen:** Auditoría senior · Screenshot verificado · Agosto 2026  
**Alcance:** `modes/gemma_code.py` · `modes/code.py` · `skills/` · `prompts/`

---

## ESTADO REAL DEL SISTEMA

```
AXIO CODE  |  29 tools  |  Plan Mode  |  verification gate
Local agent: READY (gemma4:12b)    Claude API: OFF (local-only)
```

### Catálogo completo — 29 tools verificados

| # | Tool | Categoría | Descripción |
|---|------|-----------|-------------|
| 1 | `read_file` | read | UTF-8 bounded. Obligatorio antes de editar. |
| 2 | `write_file` | write | Crear o reemplazar un archivo atómicamente. |
| 3 | `edit_file` | write | Reemplazar exactamente una ocurrencia única. |
| 4 | `apply_patch` | write | Reemplazos validados multi-archivo atómicamente; si falla validación, no cambia nada. |
| 5 | `list_dir` | read | Contenido de directorio bounded. |
| 6 | `create_dir` | write | Crear directorio y padres. |
| 7 | `delete_file` | destructive | Eliminar un archivo exacto. Requiere aprobación reforzada. |
| 8 | `search_files` | read | Glob recursivo excluyendo Git/cache. |
| 9 | `grep_files` | read | Búsqueda case-insensitive bounded en contenido. |
| 10 | `inspect_python_environment` | read | Inspecciona intérprete Python, venv, dependencias, distribuciones. No cambia estado. |
| 11 | `run_python` | execute | Ejecuta un archivo .py con argumentos y timeout. Requiere aprobación humana. |
| 12 | `inspect_node_environment` | read | Inspecciona versiones Node/npm, scripts, lockfiles, node_modules. No cambia estado. |
| 13 | `run_npm_script` | execute | Ejecuta un script de package.json con timeout. Requiere aprobación humana. |
| 14 | `git_status` | read | Branch y worktree status sin modificar el repo. |
| 15 | `git_diff` | read | Diff unstaged/staged bounded, opcionalmente por paths. |
| 16 | `read_docx` | read | Extrae texto bounded de un DOCX sin modificarlo. |
| 17 | `run_command` | execute | PowerShell cuando ningún tool dedicado aplica. Requiere aprobación humana. |
| 18 | `verification_gate` | read | Confirma que todos los checks requeridos pasaron. **Debe pasar antes de TASK_COMPLETE.** |
| 19 | `web_search` | read | Búsqueda web via SearXNG local-first. Resultados estructurados. |
| 20 | `web_fetch` | read | Fetch de URL pública con límites de redirect, SSRF, content-type, bytes y timeout. |
| 21 | `web_extract` | read | Extrae texto legible de respuesta cacheada de web_fetch. Elimina scripts/estilos/nav. |
| 22 | `browser_open` | read | Abre URL en Chromium headless persistente. Bloquea localhost y file URLs. |
| 23 | `browser_snapshot` | read | Retorna texto rendered y stable refs de elementos interactivos. |
| 24 | `browser_click` | execute | Click en link o botón via ref de browser_snapshot. Requiere aprobación. |
| 25 | `index_workspace` | index | Construye/refresca índice híbrido FTS5 + Ollama-embeddings. Solo escribe datos de índice. |
| 26 | `semantic_search` | read | Búsqueda semántica híbrida (FTS5 + embedding + filename). Retorna chunks line-addressable. |
| 27 | `search_docs` | read | Busca caché local de docs de librerías y refresca via SearXNG cuando se necesita. |
| 28 | `scaffold_project` | write | Crea proyecto completo desde template AXIO aprobado. Nunca sobreescribe destino existente. |
| 29 | `scaffold_module` | write | Crea un módulo Python/FastAPI/React dentro de un proyecto existente. Nunca sobreescribe. |

---

## VEREDICTO DE AUDITORÍA — gemma_code.py

**CRÍTICOS:** Ninguno.  
**MEDIUM (2)** · **LOW (5)** — detallados abajo.

---

## EJECUCIÓN — Pasos para Claude Code

### FASE 1 — Leer antes de tocar

```
1.  [read_file] Leer C:\Users\AXIO\axio-console\modes\gemma_code.py
2.  [read_file] Leer C:\Users\AXIO\axio-console\modes\code.py
3.  [read_file] Leer C:\Users\AXIO\axio-console\skills\gemma4\SKILL.md
4.  [read_file] Leer C:\Users\AXIO\axio-console\skills\gemma4\PLAN_MODE.md
5.  [read_file] Leer C:\Users\AXIO\axio-console\skills\gemma4\CODE_BEST_PRACTICES.md
6.  [read_file] Leer C:\Users\AXIO\axio-console\prompts\gemma4_code_system.md
7.  [read_file] Leer C:\Users\AXIO\axio-console\prompts\gemma4_plan_system.md
8.  [read_file] Leer C:\Users\AXIO\axio-console\prompts\system_coding_agent.md
```

---

### FASE 2 — Fixes en gemma_code.py (7 ediciones)

#### FIX M1 — task_id type coercion
**Función:** `_tool_task_update`

Buscar:
```python
def _tool_task_update(task_id: int, status: str, result: str = "", tracker: TaskTracker = None) -> str:
    if tracker is None:
        return "ERROR: No task tracker active."
```
Reemplazar con:
```python
def _tool_task_update(task_id, status: str, result: str = "", tracker: TaskTracker = None) -> str:
    if tracker is None:
        return "ERROR: No task tracker active."
    try:
        task_id = int(task_id)
    except (ValueError, TypeError):
        return f"ERROR: task_id must be an integer, got: {repr(task_id)}"
```
```
9.  [edit_file] FIX M1 — coerción task_id en _tool_task_update
```

#### FIX M2 — model divergence tras clear
**Función:** `run()` handler `clear`

Buscar:
```python
        elif lower == "clear":
            tracker.clear()
            plan.clear()
            session.clear()
            print(f"  {ok('Task list, plan, and session state cleared.')}\n")
```
Reemplazar con:
```python
        elif lower == "clear":
            tracker.clear()
            plan.clear()
            session.clear()
            model = session.model          # sync local var after reset
            print(f"  {ok('Task list, plan, and session state cleared.')}\n")
```
```
10. [edit_file] FIX M2 — sync model local var tras session.clear()
```

#### FIX L1 — Enforce PLAN_MAX_STEPS
**Función:** `_generate_plan()` — última línea

Buscar: `return steps`  
Reemplazar con: `return steps[:PLAN_MAX_STEPS]`
```
11. [edit_file] FIX L1 — aplicar cap PLAN_MAX_STEPS al retorno de _generate_plan
```

#### FIX L2 — Direct task path auto-summary
**Función:** `run()` rama `else:` final del REPL

Buscar:
```python
        else:
            final_task = SESSION_CONTEXT.inject(user_input, mode="list") if SESSION_CONTEXT.count else user_input
            _run_agent(final_task, model, ollama, logger, session, tracker)
```
Reemplazar con:
```python
        else:
            final_task = SESSION_CONTEXT.inject(user_input, mode="list") if SESSION_CONTEXT.count else user_input
            _run_agent(final_task, model, ollama, logger, session, tracker)
            if tracker.tasks:
                tracker.print_all()
            if session.written_files:
                print(f"  {BOLD}Auto-verification:{RESET}")
                _verify_session(session)
```
```
12. [edit_file] FIX L2 — auto-summary en direct task path
```

#### FIX L3 — Image insertion order
**Función:** `_run_agent()` bloque vision

Buscar:
```python
        for img in session.images:
            messages.insert(1, img)
```
Reemplazar con:
```python
        messages[1:1] = session.images
```
```
13. [edit_file] FIX L3 — imagen insertion order preservado
```

#### FIX L4 — JSON parse failure explícito
**Función:** `_run_agent()` bloque args deserialization

Buscar:
```python
                try:    args = json.loads(args)
                except: args = {}
```
Reemplazar con:
```python
                try:
                    args = json.loads(args)
                except json.JSONDecodeError as _je:
                    print(f"  {warn(f'Bad JSON args from model for {name}: {_je}')}")
                    args = {}
```
```
14. [edit_file] FIX L4 — JSON parse failure con warning explícito
```

#### FIX L5 — Limpiar imports muertos
```
15. [grep_files] Verificar que ClaudeClient, ModelRouter, textwrap, Any no se usan en gemma_code.py
16. [edit_file] FIX L5 — reemplazar "from core.models import OllamaClient, ClaudeClient, ModelRouter" 
                         con "from core.models import OllamaClient"
                         y eliminar "import textwrap" y "from typing import Any"
17. [verify_file] Verificar C:\Users\AXIO\axio-console\modes\gemma_code.py
```

---

### FASE 3 — Skill Coverage Analysis (29 tools)

#### Gap analysis completo

| Tool | ¿Skill existente? | Acción |
|------|------------------|--------|
| `read_file` | ✓ SKILL.md | — |
| `write_file` | ✓ SKILL.md | — |
| `edit_file` | ✓ SKILL.md | — |
| `apply_patch` | ✗ **NUEVO** | Crear sección en skills/code/SKILL.md |
| `list_dir` | ✓ SKILL.md | — |
| `create_dir` | ✓ SKILL.md | — |
| `delete_file` | ✓ SKILL.md | — |
| `search_files` | ✓ SKILL.md | — |
| `grep_files` | ✓ SKILL.md | — |
| `inspect_python_environment` | ✗ **NUEVO** | Crear sección |
| `run_python` | ✗ **NUEVO** | Crear sección |
| `inspect_node_environment` | ✗ **NUEVO** | Crear sección |
| `run_npm_script` | ✗ **NUEVO** | Crear sección |
| `git_status` | parcial (CODE_BEST_PRACTICES git workflow) | Crear sección tool-level |
| `git_diff` | parcial | Crear sección tool-level |
| `read_docx` | ✗ **NUEVO** | Crear sección |
| `run_command` | ✓ SKILL.md + CODE_BEST_PRACTICES | — |
| `verification_gate` | ✗ **NUEVO — crítico** | Crear sección completa |
| `web_search` | ✗ **NUEVO** | Crear sección + workflow |
| `web_fetch` | ✗ **NUEVO** | Crear sección + workflow |
| `web_extract` | ✗ **NUEVO** | Crear sección + workflow |
| `browser_open` | ✗ **NUEVO** | Crear sección + workflow |
| `browser_snapshot` | ✗ **NUEVO** | Crear sección + workflow |
| `browser_click` | ✗ **NUEVO** | Crear sección + workflow |
| `index_workspace` | ✗ **NUEVO** | Crear sección |
| `semantic_search` | ✗ **NUEVO** | Crear sección |
| `search_docs` | ✗ **NUEVO** | Crear sección |
| `scaffold_project` | ✗ **NUEVO** | Crear sección |
| `scaffold_module` | ✗ **NUEVO** | Crear sección |

**Resultado:** 9 tools cubiertos · 20 tools sin skill · Se necesita crear `skills/code/SKILL.md`

---

### FASE 4 — Crear skills/code/SKILL.md (nuevo, 29 tools)

```
18. [list_dir] Verificar C:\Users\AXIO\axio-console\skills\
19. [create_dir] Crear C:\Users\AXIO\axio-console\skills\code\
20. [write_file] Crear C:\Users\AXIO\axio-console\skills\code\SKILL.md con contenido completo
```

**Contenido de skills/code/SKILL.md:**

```markdown
# AXIO Code Agent — Skill Reference (29 Tools)
## Para qwen3.6:35b-a3b | gemma4:12b (local-only mode)
> Source of truth: prompts/system_coding_agent.md
> Este archivo extiende ese prompt con patrones, workflows y antipatrones.

---

## Identidad

| Campo | Valor |
|-------|-------|
| Modelo principal | qwen3.6:35b-a3b (MoE agentic) |
| Modelo local | gemma4:12b (local-only) |
| Plan Mode | Sí — two-phase PLAN → EXECUTE |
| Verification Gate | Obligatorio antes de TASK_COMPLETE |

---

## Reglas no negociables

1. `read_file` ANTES de cualquier `edit_file`, `write_file`, `apply_patch`
2. `list_dir` ANTES de crear archivos en un directorio
3. `verification_gate` ANTES de TASK_COMPLETE — sin excepciones
4. Rutas absolutas siempre
5. `run_python`, `run_npm_script`, `browser_click`, `run_command` → pedir aprobación
6. `delete_file` → pedir confirmación explícita del usuario

---

## Sección 1 — File Tools (4 tools)

### `edit_file` vs `apply_patch` — cuándo usar cuál

| Situación | Tool correcto |
|-----------|--------------|
| Un cambio quirúrgico en un archivo | `edit_file` |
| Múltiples cambios en el mismo archivo | `apply_patch` |
| Cambios coordinados en varios archivos | `apply_patch` (atómico — si falla, nada cambia) |
| Refactor que toca 3+ archivos | `apply_patch` |

**Regla:** Si el old_text no es 100% único en el archivo → usar `apply_patch` con contexto adicional para identificar la ubicación exacta.

### `read_docx`
- Usar cuando el usuario pasa un archivo `.docx` como input
- Lee texto bounded — no modifica el archivo
- Para archivos muy grandes, pedir al usuario que extraiga la sección relevante primero

---

## Sección 2 — Environment & Execution (4 tools)

### Python workflow
```
inspect_python_environment   ← primero: confirmar intérprete, venv activo, dependencias
run_python <archivo.py>      ← ejecutar solo archivos existentes, con argumentos estructurados
```
**Antipatrón:** No usar `run_command python script.py` cuando existe `run_python`.

### Node workflow
```
inspect_node_environment     ← confirmar versión Node/npm, ver scripts disponibles en package.json
run_npm_script <script>      ← ejecutar solo scripts declarados en package.json
```
**Antipatrón:** No usar `run_command npm run ...` cuando existe `run_npm_script`.

### `run_command`
- Último recurso cuando ningún tool dedicado aplica
- Casos válidos: `pip install`, `git commit`, `pytest`, operaciones de sistema
- Siempre mostrar output completo al usuario antes de continuar

---

## Sección 3 — Git Tools (2 tools)

### Workflow estándar
```
git_status                   ← antes de cualquier operación git
git_diff                     ← revisar cambios antes de commit o reporte
```
**Usar antes de:** escribir archivos en un repo existente (para entender el estado actual).  
**Usar después de:** una serie de ediciones (para confirmar qué cambió).  
**`git_diff` paths:** limitar a los archivos modificados para mantener el output bounded.

---

## Sección 4 — verification_gate (crítico)

`verification_gate` es el **único** mecanismo que autoriza TASK_COMPLETE.

### Cuándo llamarlo
- Después de TODAS las mutaciones del plan (writes, edits, patches, comandos)
- Antes de reportar "tarea completada" al usuario
- Si falla → NO reportar TASK_COMPLETE, diagnosticar primero

### Qué debe verificar
```
□ Todos los archivos escritos existen (verify paths)
□ Tests pasan si se pidieron (run_python pytest o run_npm_script test)
□ No hay errores de sintaxis en código Python (run_python con import check)
□ Secrets no hardcodeados (grep_files para API_KEY, PASSWORD, SECRET)
□ run_command/run_python no retornó EXIT CODE != 0
```

### Secuencia correcta
```
[ejecutar plan completo]
→ verification_gate      ← confirmar todos los checks
→ TASK_COMPLETE          ← solo si verification_gate pasa
```

---

## Sección 5 — Web & Research Tools (3 tools)

### Workflow de investigación web
```
web_search "query específica"     ← obtener URLs relevantes
web_fetch <url>                   ← descargar contenido (cacheado localmente)
web_extract <cached_response>     ← extraer texto limpio (sin scripts/nav/estilos)
```

### Cuándo usar cada uno
| Tool | Cuándo |
|------|--------|
| `web_search` | No sé qué URL buscar — necesito descubrir fuentes |
| `web_fetch` | Conozco la URL exacta de la documentación o recurso |
| `web_extract` | Tengo la respuesta de web_fetch y necesito texto limpio para procesar |

**Antipatrón:** No usar `browser_open` para páginas estáticas que `web_fetch` puede leer.

---

## Sección 6 — Browser Tools (3 tools)

### Cuándo usar browser vs web tools
- `web_fetch` → páginas estáticas, APIs, documentación (más rápido, más seguro)
- `browser_open` → páginas con JavaScript que requieren render (SPAs, dashboards)

### Workflow browser
```
browser_open <url>              ← abrir página en Chromium headless
browser_snapshot                ← leer estado rendered + obtener refs de elementos
browser_click <ref>             ← click en elemento por su ref (requiere aprobación)
```

### Restricciones
- No abre: localhost, file://, private networks, downloads
- `browser_click` bloquea: form submit, uploads, downloads
- Si la página requiere login → no proceder sin instrucción explícita del usuario

---

## Sección 7 — Semantic Search (3 tools)

### Workflow de indexación
```
index_workspace <path>          ← indexar una vez al inicio (FTS5 + Ollama embeddings)
semantic_search "query"         ← buscar semánticamente (chunks line-addressable)
```

### Cuándo indexar vs grep
| Tool | Cuándo |
|------|--------|
| `grep_files` | Buscar texto exacto o patrón específico |
| `semantic_search` | Buscar por concepto ("¿dónde se maneja autenticación?") |

**Prerequisito:** `index_workspace` debe ejecutarse antes de `semantic_search` en cada sesión. Si el workspace cambió significativamente, re-indexar.

### `search_docs`
- Para buscar documentación de librerías (FastAPI, SQLAlchemy, pytest, etc.)
- Usa caché local + SearXNG — no requiere internet si el caché está caliente
- Usar antes de `web_fetch` para docs de librerías conocidas

---

## Sección 8 — Scaffold Tools (2 tools)

### `scaffold_project`
- Crea un proyecto NUEVO completo desde una template AXIO aprobada
- **Nunca sobreescribe** un destino existente
- Usar `list_dir` primero para confirmar que el destino no existe

### `scaffold_module`
- Crea un módulo (Python, FastAPI-domain, React) DENTRO de un proyecto existente
- **Nunca sobreescribe** archivos existentes
- Usar `list_dir` primero para ver la estructura existente

### Templates disponibles (verificar con list_dir en el directorio de templates AXIO)
```
scaffold_project → list templates disponibles antes de usar
scaffold_module  → list module types disponibles antes de usar
```

---

## Sección 9 — task_update Sequencing

Secuencia obligatoria por cada paso del plan:

```
task_update(id, "in_progress")     ← al EMPEZAR el paso
[ejecutar herramientas del paso]
task_update(id, "completed", "resumen ≤ 80 chars")  ← si ÉXITO
task_update(id, "failed",    "descripción del error") ← si FALLO
```

**Nunca marcar `completed` si:**
- `write_file` retornó ERROR
- `verification_gate` falló
- `run_python` / `run_command` retornó EXIT CODE != 0

---

## Sección 10 — Recuperación de Errores

| Tool | Error frecuente | Acción correcta |
|------|----------------|-----------------|
| `read_file` | File not found | `list_dir` en directorio padre |
| `edit_file` | Exact text not found | `read_file` para obtener texto exacto actual |
| `apply_patch` | Validation failed | `read_file` en cada archivo afectado, ajustar patch |
| `write_file` | ERROR writing | `create_dir` para el directorio padre |
| `run_python` | EXIT CODE: 1 | Leer STDERR, diagnosticar, no reintentar ciegamente |
| `run_npm_script` | Script not found | `inspect_node_environment` para ver scripts disponibles |
| `verification_gate` | Check failed | Diagnosticar el check fallido, corregir, re-verificar |
| `semantic_search` | Index not found | Ejecutar `index_workspace` primero |
| `scaffold_project` | Destination exists | `list_dir` para encontrar nombre alternativo |

**Regla de oro:** ERROR de cualquier tool → no avanzar. Máximo 2 reintentos con diagnóstico.

---

## Sección 11 — Reporte final (TASK_COMPLETE)

Antes de TASK_COMPLETE, siempre reportar:

1. **Qué se construyó** — descripción en 1-3 líneas
2. **Archivos creados/modificados** — rutas absolutas completas
3. **Checks de verificación** — qué pasó el verification_gate
4. **Próximos pasos** — qué debe hacer el usuario ahora
```

```
21. [verify_file] Verificar C:\Users\AXIO\axio-console\skills\code\SKILL.md
```

---

### FASE 5 — Actualizar skills/gemma4/SKILL.md

Agregar nota de mantenimiento + secciones task_update y error recovery (idénticas a code/SKILL.md secciones 9 y 10, adaptadas para 11 tools de Gemma).

```
22. [read_file] Leer inicio actual de skills\gemma4\SKILL.md
23. [edit_file] Agregar nota de mantenimiento al inicio:
    "> Nota: prompts/gemma4_code_system.md y prompts/gemma4_plan_system.md son source of truth.
    >  Este SKILL.md extiende con patrones y referencia. Mantener sincronizados."
24. [edit_file] Agregar Sección 8 — task_update Sequencing (ver skills/code/SKILL.md sección 9)
25. [edit_file] Agregar Sección 9 — Error Recovery (ver skills/code/SKILL.md sección 10)
26. [verify_file] Verificar C:\Users\AXIO\axio-console\skills\gemma4\SKILL.md
```

---

### FASE 6 — Verificación final

```
27. [verify_file] Verificar C:\Users\AXIO\axio-console\modes\gemma_code.py
28. [verify_file] Verificar C:\Users\AXIO\axio-console\skills\code\SKILL.md
29. [verify_file] Verificar C:\Users\AXIO\axio-console\skills\gemma4\SKILL.md
```

**Test de humo post-plan:**
```powershell
cd C:\Users\AXIO\axio-console
py axio.py code
# → tools  (verificar que muestra 29 tools)
# → plan create a FastAPI health endpoint in C:\test_axio\
# → execute
# Verificar: task_update actualiza, verification_gate pasa, TASK_COMPLETE reporta archivos
```

---

## Resumen de cambios

| Archivo | Acción | Razón |
|---------|--------|-------|
| `modes/gemma_code.py` | 6 ediciones (M1 M2 L1 L2 L3 L4) + limpieza L5 | Bugs de auditoría |
| `skills/code/SKILL.md` | **CREAR** — 29 tools completos | No existía, 20 tools sin cobertura |
| `skills/gemma4/SKILL.md` | Agregar 2 secciones + nota | Gap task_update + error recovery |

**Archivos NO tocados:** `modes/code.py`, `axio.py`, `prompts/`, `PLAN_MODE.md`, `CODE_BEST_PRACTICES.md`

---

*Plan v2 — basado en screenshot verificado 29 tools · AXIO Cowork · Agosto 2026*

---

## DIAGNÓSTICO — Por qué los tools web no se usaron (bug confirmado)

**Sesión analizada:** Gemma respondió una consulta de actualidad usando conocimiento interno.  
**Evidencia:** Ninguna llamada a `web_search`, `web_fetch` ni `browser_open` en el log.  
**Causa raíz:** El harness actual tiene 5 fallos sistémicos:

| # | Fallo | Efecto |
|---|-------|--------|
| F1 | El system prompt explica los tools web pero no los obliga | Gemma los ignora en consultas de solo lectura |
| F2 | No hay detección de intención web | El agente no sabe que debería navegar |
| F3 | No hay Web Evidence Gate | `TASK_COMPLETE` se acepta sin evidencia web |
| F4 | `verification_gate` solo protege código, no calidad de respuesta | Respuestas alucinadas pasan la gate |
| F5 | Chat y Cowork usan `chat_stream` sin tool loop | Solo Code tiene herramientas; Chat/Cowork siempre alucinan sobre actualidad |

**Corrección correcta:** Harness determinista — detectar intención → forzar tools → bloquear respuesta sin evidencia.

---

## FASE 7 — Web Evidence Gate en system prompts

### 7A — Actualizar `prompts/system_coding_agent.md`

Agregar sección al final del archivo (después de "Default Stack"):

```markdown
## Web Evidence Policy (non-negotiable)

When a query requires current information — news, prices, recent events, people, links,
citations, or anything that changes over time — you MUST:

1. Call `web_search` with a precise query BEFORE generating any response
2. Call `web_fetch` on at least one result URL to read actual content
3. Call `web_extract` to get clean text from the fetched page
4. Base your answer on the fetched content, not internal knowledge
5. Cite exact URLs inline in your response

### Trigger keywords (mandatory web search)
latest · noticias · actual · actualidad · hoy · today · now · ahora
busca · investiga · investiga en internet · cita · fuentes · links · urls
recent · precio actual · último · últimas · 2024 · 2025 · 2026 · current

### Blocked responses (TASK_COMPLETE is not allowed if)
- Query contained a trigger keyword AND no web_search/web_fetch/browser_open was called
- Response claims "I searched" or "I found" without a corresponding tool call
- Response says "I don't have access to real-time data" — you DO have web_search

### Correct pattern
user: "Busca las últimas noticias sobre IA"
agent: web_search("IA noticias agosto 2026") → web_fetch(url) → web_extract → respond with URLs
```

```
30. [read_file]  Leer prompts\system_coding_agent.md
31. [edit_file]  Agregar Web Evidence Policy al final de system_coding_agent.md
32. [verify_file] Verificar prompts\system_coding_agent.md
```

### 7B — Actualizar `prompts/gemma4_code_system.md`

Agregar la misma sección Web Evidence Policy (adaptada para gemma4).

```
33. [read_file]  Leer prompts\gemma4_code_system.md
34. [edit_file]  Agregar Web Evidence Policy al final de gemma4_code_system.md
35. [verify_file] Verificar prompts\gemma4_code_system.md
```

---

## FASE 8 — Harness determinista en código Python

### 8A — Crear `core/web_intent.py` (nuevo módulo)

```
36. [list_dir]   Verificar C:\Users\AXIO\axio-console\core\
37. [write_file] Crear C:\Users\AXIO\axio-console\core\web_intent.py
```

**Contenido de `core/web_intent.py`:**

```python
"""
AXIO Web Intent Detector + Evidence Gate
----------------------------------------
Determina si una query requiere evidencia web y fuerza el uso de tools.
"""

from __future__ import annotations

# ── Palabras clave que disparan búsqueda web obligatoria ──────────────────
WEB_TRIGGER_KEYWORDS: frozenset[str] = frozenset({
    # Tiempo
    "latest", "latest news", "hoy", "today", "now", "ahora",
    "reciente", "recent", "último", "últimas", "ultima", "ultimas",
    "2024", "2025", "2026", "actual", "actualidad",
    # Acción de búsqueda
    "busca", "buscar", "investiga", "investigar", "search",
    "encuentra", "find online", "look up",
    # Evidencia / citas
    "cita", "citar", "fuentes", "fuente", "links", "urls", "url",
    "referencias", "reference", "cite",
    # Noticias / mercado
    "noticias", "news", "precio actual", "current price",
    "stock", "cotización", "market", "mercado",
})

# ── Tools que cuentan como evidencia web ─────────────────────────────────
WEB_EVIDENCE_TOOLS: frozenset[str] = frozenset({
    "web_search", "web_fetch", "web_extract",
    "browser_open", "browser_snapshot",
})

# ── Prefijo inyectado cuando se detecta intención web ────────────────────
WEB_FORCE_INSTRUCTION = (
    "\n\n⚠️  WEB EVIDENCE REQUIRED (AXIO harness rule):\n"
    "This query requires current information. You MUST:\n"
    "  1. Call web_search with a precise query — do this FIRST\n"
    "  2. Call web_fetch on at least one result URL\n"
    "  3. Call web_extract to get clean text\n"
    "  4. Base your response on the fetched content\n"
    "  5. Cite exact URLs in the response\n"
    "DO NOT respond using internal knowledge alone. "
    "TASK_COMPLETE is blocked until web evidence is present.\n"
)


def detect_web_intent(query: str) -> bool:
    """Return True if the query triggers mandatory web search."""
    q = query.lower()
    return any(kw in q for kw in WEB_TRIGGER_KEYWORDS)


def inject_web_instruction(query: str) -> str:
    """Append web evidence instruction to query if web intent detected."""
    if detect_web_intent(query):
        return query + WEB_FORCE_INSTRUCTION
    return query


def check_evidence_gate(
    query: str,
    tools_called: set[str],
) -> tuple[bool, str]:
    """
    Returns (passed: bool, reason: str).
    Gate fails if query required web evidence but no web tool was called.
    """
    if not detect_web_intent(query):
        return True, "no web intent — gate not required"
    used_web = tools_called & WEB_EVIDENCE_TOOLS
    if used_web:
        return True, f"web evidence present: {', '.join(sorted(used_web))}"
    return False, (
        "Web Evidence Gate FAILED — query required current information "
        "but no web tool was called (web_search / web_fetch / browser_open). "
        "Re-run with explicit web instruction."
    )
```

```
38. [verify_file] Verificar C:\Users\AXIO\axio-console\core\web_intent.py
```

---

### 8B — Integrar Web Evidence Gate en `modes/gemma_code.py`

**Cambio 1 — Importar el módulo:**

Buscar en el bloque de imports:
```python
from core.file_context import SESSION_CONTEXT
```
Agregar después:
```python
from core.web_intent   import inject_web_instruction, check_evidence_gate, detect_web_intent
```

**Cambio 2 — Trackear tools llamados en `_run_agent`:**

Buscar:
```python
    start = time.time()

    for iteration in range(MAX_ITERS):
```
Reemplazar con:
```python
    start       = time.time()
    tools_called: set[str] = set()

    for iteration in range(MAX_ITERS):
```

**Cambio 3 — Registrar cada tool llamado:**

Buscar (en el loop de tool_calls):
```python
            result  = execute_tool(name, args)
```
Reemplazar con:
```python
            tools_called.add(name)
            result  = execute_tool(name, args)
```

**Cambio 4 — Web Evidence Gate al finalizar:**

Buscar (al final de `_run_agent`, la línea del logger "done"):
```python
            logger.log_tool(task, "_done", {}, content, model)
            return
```
Reemplazar con:
```python
            logger.log_tool(task, "_done", {}, content, model)
            gate_ok, gate_msg = check_evidence_gate(task, tools_called)
            if not gate_ok:
                print(f"\n  {warn('WEB EVIDENCE GATE:')} {gate_msg}")
                print(f"  {lo('Tip: type  web_search <query>  to search manually.')}\n")
            return
```

**Cambio 5 — Inyectar instrucción web en direct task path:**

En `run()`, rama `else:` (direct task), buscar:
```python
            final_task = SESSION_CONTEXT.inject(user_input, mode="list") if SESSION_CONTEXT.count else user_input
            _run_agent(final_task, model, ollama, logger, session, tracker)
```
Reemplazar con:
```python
            final_task = SESSION_CONTEXT.inject(user_input, mode="list") if SESSION_CONTEXT.count else user_input
            final_task = inject_web_instruction(final_task)
            _run_agent(final_task, model, ollama, logger, session, tracker)
```

**Cambio 6 — Inyectar en execute (plan mode):**

En `run()`, rama `elif lower == "execute":`, buscar:
```python
            _run_agent(task_text, model, ollama, logger, session, tracker)
```
Reemplazar con:
```python
            task_text = inject_web_instruction(task_text)
            _run_agent(task_text, model, ollama, logger, session, tracker)
```

```
39. [read_file]   Leer modes\gemma_code.py (para obtener texto exacto)
40. [edit_file]   Cambio 1 — import web_intent en gemma_code.py
41. [edit_file]   Cambio 2 — tools_called set en _run_agent
42. [edit_file]   Cambio 3 — tools_called.add(name) en tool loop
43. [edit_file]   Cambio 4 — Evidence gate al finalizar _run_agent
44. [edit_file]   Cambio 5 — inject_web_instruction en direct task path
45. [edit_file]   Cambio 6 — inject_web_instruction en execute plan path
46. [verify_file] Verificar modes\gemma_code.py
```

---

### 8C — Integrar Web Evidence Gate en `modes/code.py`

Mismos 6 cambios aplicados a `code.py` (el agente qwen3.6 con 29 tools).  
Localizar las funciones equivalentes: `_run_agent` o el loop de tool-calling principal.

```
47. [read_file]   Leer modes\code.py
48. [edit_file]   Agregar import from core.web_intent
49. [edit_file]   Agregar tools_called set + .add(name) en tool loop
50. [edit_file]   Agregar evidence gate check al finalizar
51. [edit_file]   Inyectar web instruction antes de llamar _run_agent
52. [verify_file] Verificar modes\code.py
```

---

### 8D — Tool Subsetting por tipo de query (opcional — V2)

Cuando el modelo recibe 29 schemas de golpe, puede confundirse sobre cuál usar.
Implementar `_select_tools(query)` que devuelve el subconjunto relevante:

```python
# En core/web_intent.py — agregar función:

TOOL_SUBSETS = {
    "coding": {
        "read_file","write_file","edit_file","apply_patch","list_dir",
        "create_dir","delete_file","search_files","grep_files",
        "run_python","run_npm_script","run_command","git_status","git_diff",
        "inspect_python_environment","inspect_node_environment",
        "verification_gate","scaffold_project","scaffold_module","read_docx",
    },
    "research": {
        "web_search","web_fetch","web_extract",
        "browser_open","browser_snapshot","browser_click",
        "search_docs","read_file","read_docx",
    },
    "semantic": {
        "index_workspace","semantic_search","grep_files","search_files","read_file",
    },
}

CODING_KEYWORDS = frozenset({
    "crear", "create", "escribir", "write", "editar", "edit", "fix", "arregla",
    "refactor", "implementa", "implement", "función", "function", "clase", "class",
    "módulo", "module", "api", "endpoint", "test", "script", "archivo", "file",
})

def select_tools(query: str, all_tools: list[dict]) -> list[dict]:
    """Return the relevant tool subset based on query intent."""
    q = query.lower()
    is_web      = detect_web_intent(q)
    is_coding   = any(kw in q for kw in CODING_KEYWORDS)
    is_semantic = any(kw in q for kw in {"busca en workspace", "semantic", "similar", "embedding"})

    if is_web and not is_coding:
        allowed = TOOL_SUBSETS["research"]
    elif is_semantic and not is_coding:
        allowed = TOOL_SUBSETS["semantic"]
    else:
        return all_tools   # coding o mixto → todos los tools

    return [t for t in all_tools if t["function"]["name"] in allowed]
```

```
53. [edit_file] Agregar select_tools() a core\web_intent.py
54. [edit_file] Integrar select_tools() en gemma_code.py _run_agent — 
                pasar select_tools(task, TOOLS) en vez de TOOLS directamente
55. [edit_file] Integrar select_tools() en code.py de la misma forma
```

---

## FASE 9 — Actualizar skills con Web Harness

### Agregar sección a `skills/code/SKILL.md` (creado en Fase 4)

```markdown
## Sección 12 — Web Evidence Harness (AXIO-specific)

### Detección de intención web
El harness detecta automáticamente queries que requieren información actual y:
1. Inyecta una instrucción obligatoria en el mensaje del usuario
2. Activa el Web Evidence Gate al finalizar

### Palabras clave que disparan el gate
latest · noticias · actual · busca · investiga · hoy · today · fuentes · links · 2024-2026

### Lo que hace el agente cuando se activa el gate
1. `web_search` con query precisa — PRIMERO
2. `web_fetch` en al menos una URL de resultados
3. `web_extract` para texto limpio
4. Responder basándose en el contenido real, no en conocimiento interno
5. Citar URLs exactas en la respuesta

### Si el gate falla al finalizar
El harness emite un warning visible. El agente NO debe responder con TASK_COMPLETE.
Re-ejecutar con instrucción web explícita:
`web_search <query específica>`

### Tool subsetting automático
Para queries de solo investigación, el harness pasa solo los 9 tools de research.
Para queries de coding, pasa los 21 tools de desarrollo.
Para queries mixtas, pasa los 29 tools completos.
```

```
56. [read_file]   Leer skills\code\SKILL.md
57. [edit_file]   Agregar Sección 12 — Web Evidence Harness
58. [verify_file] Verificar skills\code\SKILL.md
```

---

## FASE 10 — Verificación final completa

```
59. [verify_file] Verificar core\web_intent.py
60. [verify_file] Verificar modes\gemma_code.py
61. [verify_file] Verificar modes\code.py
62. [verify_file] Verificar prompts\system_coding_agent.md
63. [verify_file] Verificar prompts\gemma4_code_system.md
64. [verify_file] Verificar skills\code\SKILL.md
65. [verify_file] Verificar skills\gemma4\SKILL.md
```

**Test de smoke — Web Evidence Gate:**
```powershell
cd C:\Users\AXIO\axio-console
py axio.py code
# Escribir: "Busca las últimas noticias sobre agentes de IA"
# Esperado:
#   1. web_search se llama automáticamente
#   2. web_fetch en al menos 1 URL
#   3. Respuesta con URLs citadas
#   4. Sin mensaje de gate fallido
```

**Test de smoke — gate fail (debe avisar):**
```powershell
# Escribir: "¿Cuáles son las últimas noticias?" y forzar respuesta sin tools
# Esperado: warning "WEB EVIDENCE GATE FAILED" visible en consola
```

---

## Resumen final de cambios (versión actualizada)

| Archivo | Acción | Prioridad |
|---------|--------|-----------|
| `modes/gemma_code.py` | 7 fixes auditoría + 6 cambios web gate | ALTA |
| `modes/code.py` | 5 cambios web gate | ALTA |
| `core/web_intent.py` | **CREAR** — módulo de detección + gate + subsetting | ALTA |
| `prompts/system_coding_agent.md` | Agregar Web Evidence Policy | ALTA |
| `prompts/gemma4_code_system.md` | Agregar Web Evidence Policy | ALTA |
| `skills/code/SKILL.md` | **CREAR** + Sección 12 web harness | MEDIA |
| `skills/gemma4/SKILL.md` | Secciones 8, 9 + nota mantenimiento | MEDIA |

**Archivos NO tocados:** `axio.py`, `PLAN_MODE.md`, `CODE_BEST_PRACTICES.md`

---

*Plan v3 — Diagnóstico web + harness determinista incorporados · AXIO Cowork · Agosto 2026*
