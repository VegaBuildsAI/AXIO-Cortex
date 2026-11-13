# How to build the racer with AXIO Code (local, gemma4:12b)

`RACER_BUILD.md` is the agent spec, kept under 3,731 characters so `read_file` hands it to the
model whole (tool results longer than 4,000 characters are cut). `RACER_BUILD.full.md` is the
original long version, for humans; don't load it or the whole folder, only the one file.

```powershell
cd "C:\Users\AXIO\AXIO Model Improvement\axio-console-v2.1"
$env:LOCAL_ONLY = "1"
$env:AXIO_CODE_MAX_STEPS = "80"
py axio.py code
```

Then type:

```
load workspaces\racer\RACER_BUILD.md
```
```
Read the loaded spec with read_file and implement it end to end: follow its Steps until SELFTEST OK, then verification_gate.
```

- You'll approve each `py` command (compile and self-test). If the agent pauses, type `continue`
  or `fix the failing selftest`.
- The agent writes the logic and self-test first, then adds the GUI in a second edit, so no single
  tool call has to produce the whole file.
- Optional: `$env:AXIO_CODE_TOOL_ROUTING_MODE = "dynamic"` shows gemma 8 relevant tools instead
  of all 45.

Play it yourself afterwards:

```powershell
cd "C:\Users\AXIO\AXIO Model Improvement\axio-console-v2.1\workspaces\racer"
py racer.py
```
