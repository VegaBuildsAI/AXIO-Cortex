# Handoff para auditoría en Claude Code — Cortex Memory Resilience

Fecha de implementación y verificación: 2026-08-24  
Repositorio: `C:\Users\AXIO\AXIO Model Improvement\axio-console-v2.1`  
Raíz canónica de datos: `C:\Users\AXIO\.axio`  
Objetivo de este documento: permitir una auditoría independiente, reproducible y preferentemente de solo lectura.

## 1. Objetivo solicitado

Convertir Cortex/IOAF en un cerebro central vivo con estas garantías:

1. Chat, Cowork y Code reciben siempre el conocimiento canónico compartido.
2. Cada modo conserva además su propia memoria y sus sesiones.
3. Postgres en Docker es la fuente primaria cuando está disponible.
4. JSON, journals y Chroma sostienen la operación local si Postgres falla.
5. Las escrituras pendientes se reproducen automáticamente cuando Postgres vuelve.
6. Un cierre inesperado no debe perder el turno que el usuario ya envió.
7. CLI y UI utilizan una sola raíz local: `C:\Users\AXIO\.axio`.
8. La migración no elimina ni sobrescribe los almacenes heredados.

## 2. Resultado observado al entregar

La verificación real produjo:

```text
AXIO_DATA_ROOT=C:\Users\AXIO\.axio
CHROMA_DIR=C:\Users\AXIO\.axio\chroma-resilient
Postgres embeddings=491
Chroma counts={'chat': 3, 'cowork': 1, 'code': 14, 'console': 473}
Pending events=0
data_root_is_unified=PASS
postgres_is_primary=PASS
global_profile_present=PASS
cowork_receives_profile=PASS
shared_modes_include_console=PASS
outbox_drained=PASS
chroma_matches_postgres=PASS
```

Pruebas ejecutadas:

- Suite Python completa: 61 pruebas aprobadas.
- UI: build de producción aprobado.
- UI: 2/2 pruebas de HTML renderizado aprobadas.
- `git diff --check`: código de salida 0; solamente avisos esperados de conversión LF/CRLF.
- Compilación Python y parseo de scripts PowerShell aprobados.

No se hizo una caída deliberada del contenedor Postgres de producción. El failover y el replay se probaron con backend fallido simulado en las pruebas unitarias. Esta diferencia debe mantenerse explícita en el dictamen.

## 3. Arquitectura resultante

### Escritura normal con Postgres disponible

```text
mensaje del usuario
    -> snapshot JSON atómico en journals
    -> evento durable en outbox
    -> UPSERT de sesión/mensajes en Postgres
    -> confirmación y eliminación del evento pendiente
    -> respuesta del modelo
    -> nuevo snapshot + UPSERT
```

El mensaje del usuario se persiste antes de invocar al modelo. Por esto, un cierre entre el prompt y la respuesta deja una sesión recuperable, aunque posiblemente incompleta.

### Lectura y recall

```text
Postgres saludable
    -> lectura primaria desde Postgres
    -> actualización del espejo JSON/local

Postgres no disponible
    -> Chroma local para recall semántico
    -> búsqueda local por palabras como último fallback
    -> hechos estructurados JSON siempre disponibles
```

### Recuperación de escrituras

Cada operación remota pendiente se guarda como un archivo JSON individual en:

```text
C:\Users\AXIO\.axio\outbox\pending
```

`reconcile_pending()` vuelve a ejecutar eventos idempotentes y solo elimina el archivo pendiente después de una escritura remota exitosa.

### Perfil global

El perfil canónico está en `console.global_profile`. Se inyecta de forma determinista en el prefijo de memoria de Chat, Cowork y Code; no depende de que una búsqueda vectorial considere relevante la identidad.

### Aislamiento por modo

Se conservan hechos, sesiones, journals y colecciones por modo. El conocimiento global de `console` se agrega al contexto compartido sin fusionar destructivamente las memorias privadas de Chat, Cowork o Code.

## 4. Archivos implementados o modificados para este alcance

Importante: el working tree ya contenía modificaciones y archivos sin seguimiento antes de esta tarea. No debe atribuirse todo el diff actual a esta implementación. No se limpiaron, descartaron ni hicieron commit de cambios preexistentes.

### Núcleo de memoria

- `core/config.py`
  - Raíz configurable mediante `AXIO_DATA_ROOT`.
  - `CHROMA_DIR = AXIO_DATA_ROOT / "chroma-resilient"`.
  - Directorios separados para `journals` y `outbox`.
- `core/memory_durability.py` — nuevo.
  - Escritura JSON atómica con `flush`, `fsync` y reemplazo.
  - Snapshots de sesiones activas.
  - Cola durable de eventos pendientes.
- `core/memory_backends/postgres_backend.py`
  - Healthcheck real.
  - IDs estables y UPSERT idempotente.
  - Persistencia incremental de sesiones y mensajes.
  - Exportación de embeddings para reconstruir Chroma.
- `core/memory.py`
  - Postgres primario con fallback local.
  - Espejo JSON/Chroma.
  - `console.global_profile` determinista.
  - Outbox y `reconcile_pending()`.
  - Persistencia incremental y finalización de sesiones.
  - Eliminación coordinada Postgres/Chroma.
- `core/mode_memory.py`
  - UUID completo y estable por sesión.
  - `record_user()` antes de llamar al modelo.
  - `record_assistant()` después de obtener la respuesta.
  - Comandos de estado, fuentes, pendientes y reconciliación.
- `core/session.py`
  - `fsync` agregado al guardado atómico.
- `core/memory_runtime.py`
  - Healthcheck contra Postgres.
  - Reconciliación al iniciar.
  - Sincronización completa inicial versión 2.
  - Eliminación coordinada de chunks obsoletos.

### Integración en los modos

- `modes/chat.py`
- `modes/cowork.py`
- `modes/code.py`

En los tres, `record_user()` ocurre antes de la inferencia y `record_assistant()` después. Revisar especialmente rutas de error, early returns y `KeyboardInterrupt`.

### Configuración, migración y operación

- `.env`
  - Solo se agregó/configuró `AXIO_DATA_ROOT=C:\Users\AXIO\.axio`; no registrar ni mostrar secretos durante la auditoría.
- `.env.example`
  - Documenta la raíz canónica.
- `run_ui.ps1`
  - UI apuntada a `%USERPROFILE%\.axio`.
- `scripts/seed_cortex_memory.py`
  - Identidad movida a `console.global_profile`.
- `scripts/migrate_ioaf_resilience.py` — nuevo.
  - Copia únicamente archivos faltantes desde `.axio-data`.
  - No elimina ni sobrescribe archivos existentes.
- `scripts/mirror_postgres_to_chroma.py` — nuevo.
  - Reconstruye el espejo exacto desde los embeddings canónicos.
- `scripts/verify_memory_resilience.py` — nuevo.
  - Verificador integrado de raíz, backend, perfil, outbox y paridad.
- `scripts/backup_cortex.ps1` — nuevo.
  - `pg_dump` diario y retención limitada a la carpeta exacta de backups.
- `scripts/install_memory_tasks.ps1` — nuevo.
  - Instala cuatro tareas para el usuario actual.
- `start_axio_memory.cmd`
  - Migración, sync inicial y espejo Chroma.
- `run_memory_runtime.cmd`
  - Usa el entorno virtual y el puerto actual 5432.

### Pruebas y documentación

- `tests/test_memory_resilience.py` — nuevo.
- Se ampliaron pruebas de backend, persistencia de sesiones, recall cross-mode y ModeMemorySession.
- `AGENTS.md` y `AXIO_CORTEX_MEMORY.md` fueron actualizados con la arquitectura operativa.

## 5. Migración realizada

Se ejecutó `scripts/migrate_ioaf_resilience.py` con estas propiedades:

- Destino obligatorio: `C:\Users\AXIO\.axio`.
- Se copió un archivo heredado faltante.
- No se borró el árbol `.axio-data`.
- No se borró el Chroma anterior `C:\Users\AXIO\.axio\chroma`.
- Se creó un espejo limpio separado en `C:\Users\AXIO\.axio\chroma-resilient`.
- El outbox terminó con cero eventos pendientes.

Esta conservación fue intencional para permitir rollback o comparación forense.

## 6. Automatizaciones instaladas

Tareas de Windows para el usuario actual:

1. `AXIO Cortex Startup`
2. `AXIO Memory Sync` — cada 30 minutos.
3. `AXIO Memory Consolidate` — cada noche.
4. `AXIO Cortex Backup` — cada noche a las 02:30.

Últimos resultados observados:

```text
AXIO Memory Sync   LastTaskResult=0
AXIO Cortex Backup LastTaskResult=0
```

Backup confirmado:

```text
C:\Users\AXIO\.axio\backups\axio-cortex-20260824-194332.sql
Size: 4,656,684 bytes
```

## 7. Procedimiento recomendado de auditoría

Comenzar en modo de solo lectura. No ejecutar migración, mirror, seed, consolidación ni instalación de tareas durante la primera pasada.

### Paso A — leer contratos y cambios

```powershell
cd "C:\Users\AXIO\AXIO Model Improvement\axio-console-v2.1"
git status --short
git diff --check
git diff -- core/config.py core/memory.py core/mode_memory.py core/session.py
git diff -- core/memory_backends/postgres_backend.py
git diff -- modes/chat.py modes/cowork.py modes/code.py
```

Revisar también los archivos nuevos indicados en la sección 4, porque `git diff` no muestra el contenido de archivos untracked sin opciones adicionales.

### Paso B — pruebas locales

```powershell
.\.venv\Scripts\python.exe -m unittest discover tests -v
Push-Location ui
npm.cmd run test
Pop-Location
```

### Paso C — estado de Cortex sin mutación intencional

El verificador usa las rutas reales y puede reconciliar outbox si existieran eventos, por lo que es operacionalmente benigno pero no estrictamente read-only:

```powershell
.\.venv\Scripts\python.exe scripts\verify_memory_resilience.py
```

Resultado esperado: todos los checks `PASS`, 491 embeddings en Postgres y paridad exacta por modo en Chroma. Si la base cambió legítimamente desde este handoff, auditar igualdad y fuentes en vez de exigir literalmente 491.

### Paso D — tareas programadas

```powershell
Get-ScheduledTask -TaskName "AXIO Cortex Startup","AXIO Memory Sync","AXIO Memory Consolidate","AXIO Cortex Backup" |
    Select-Object TaskName,State,Actions,Triggers

Get-ScheduledTaskInfo -TaskName "AXIO Memory Sync"
Get-ScheduledTaskInfo -TaskName "AXIO Cortex Backup"
```

### Paso E — auditoría específica de resistencia

Intentar demostrar o refutar:

1. Un prompt se guarda antes de iniciar la inferencia.
2. Un evento del outbox no se borra si Postgres falla.
3. El mismo evento puede reproducirse dos veces sin duplicar filas.
4. Un read exitoso de Postgres actualiza el espejo local.
5. Cowork recibe `global_profile` aunque el recall vectorial devuelva cero resultados.
6. Las memorias por modo permanecen separadas.
7. La ruta de fallback no oculta silenciosamente corrupción local.
8. El runtime no elimina chunks fuera del conjunto exacto que administra.
9. Los scripts no contienen rutas destructivas amplias ni exponen credenciales.
10. La UI y la CLI resuelven la misma raíz independientemente del directorio actual.

## 8. Prueba controlada de caída pendiente

No detener el contenedor productivo como parte automática de la auditoría.

Si Michael autoriza una ventana controlada, el ensayo pendiente sería:

1. Capturar conteos y hashes/IDs antes del ensayo.
2. Detener únicamente `axio-cortex-postgres`.
3. Crear una sesión de prueba claramente etiquetada.
4. Confirmar journal local, recall por Chroma y evento pendiente en outbox.
5. Levantar el mismo contenedor.
6. Ejecutar reconciliación.
7. Confirmar outbox vacío y una sola copia de cada fila en Postgres.
8. Eliminar datos de prueba solo con autorización explícita y targets exactos.

Sin este ensayo, la tolerancia a caída está demostrada por código, pruebas con fallo simulado y paridad live, pero no por una interrupción real del servicio.

## 9. Riesgos y puntos que merecen escrutinio

- El working tree está sucio y mezcla cambios anteriores con esta implementación. Auditar por comportamiento y por los símbolos concretos, no por tamaño total del diff.
- Chroma anterior contiene entradas heredadas adicionales; por eso se preservó y se creó `chroma-resilient` como espejo limpio.
- La persistencia por mensaje aumenta escrituras en disco y Postgres. Revisar impacto si la frecuencia de uso crece considerablemente.
- `reconcile_pending()` puede ejecutarse en rutas frecuentes. Confirmar que su costo permanece acotado y que los eventos malformados no bloquean el resto.
- Verificar que ninguna excepción de Postgres sea interpretada erróneamente como éxito antes de reconocer un evento.
- Revisar concurrencia si dos procesos AXIO escriben o reconcilian el mismo outbox simultáneamente.
- Revisar retención de journals, sesiones, Chroma y backups; el backup tiene retención, pero otros almacenes pueden crecer indefinidamente.
- Confirmar que RevRec conserva su aislamiento intencional y que cualquier acceso global adicional sea una decisión explícita.

## 10. Criterios de aceptación para Claude Code

Emitir un dictamen separado por severidad y con referencias `archivo:línea`:

- **PASS** si no se encuentran fallos que puedan perder, duplicar, aislar incorrectamente o filtrar memoria.
- **PASS WITH RISKS** si la arquitectura funciona pero quedan riesgos operativos no bloqueantes.
- **FAIL** si existe una ruta reproducible de pérdida silenciosa, duplicación no idempotente, divergencia permanente, mezcla indebida entre modos o exposición de secretos.

No corregir hallazgos durante la primera auditoría. Entregar primero:

1. Hallazgos ordenados por severidad.
2. Evidencia y reproducción.
3. Qué garantías sí quedaron demostradas.
4. Qué quedó sin demostrar.
5. Plan mínimo de corrección, sin ejecutar, para aprobación de Michael.

## 11. Prompt sugerido para Claude Code

```text
Audita la implementación descrita en CLAUDE_CODE_CORTEX_MEMORY_AUDIT_HANDOFF.md.
Trabaja primero en modo estrictamente read-only: no edites archivos, no detengas Docker,
no ejecutes migraciones, seeds, mirror, consolidación ni instalación de tareas.

No asumas que el handoff es correcto. Intenta refutar sus garantías con evidencia del
código, las pruebas y el estado observable. Presta especial atención a persistencia antes
de inferencia, atomicidad, idempotencia, concurrencia del outbox, prioridad real de
Postgres, fallback Chroma/JSON, separación por modo, perfil global determinista y raíces
CLI/UI. Distingue cambios preexistentes del alcance de memoria cuando sea posible.

Entrega hallazgos primero, ordenados por severidad, con archivo y línea. Después incluye:
garantías verificadas, pruebas ejecutadas, limitaciones, riesgos residuales y un plan mínimo
de corrección. No implementes correcciones hasta recibir autorización explícita.
```

