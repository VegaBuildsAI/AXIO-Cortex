# AXIO Node and npm runtime

Treat `package.json` and the active lockfile as live evidence. Do not assume a package manager, script name, Node version, or installed dependency from memory.

1. Call `inspect_node_environment` with the absolute project root.
2. Read `package.json` before changing scripts or dependencies.
3. Prefer `run_npm_script` for declared `test`, `build`, `lint`, `check`, or project-specific verification scripts.
4. Use `run_command` for installation only when the user authorizes execution and the lockfile/package-manager choice is verified.
5. After a successful mutation, run the required scripts and call `verification_gate` with IDs such as `npm:test`, `npm:build`, or `npm:verify:engine`.

`run_npm_script` uses an argument list with `shell=False`, enforces a bounded timeout, and records verification evidence only when the process exits with code 0.
