# Installing Debug Adapters

`dap` doesn't ship a debugger -- it drives one that's already installed.
Many of these are already present via an IDE extension; check before
installing a second copy.

---

## Python -- debugpy

**Check:** `python3 -m debugpy --version`

**Install:** `pip install debugpy` (add it to the project's dev
dependencies rather than installing globally, so the version stays pinned
alongside the rest of the toolchain -- see `python-packaging`).

**Virtualenv:** `dap` reads `$VIRTUAL_ENV` to find the interpreter.
Activate the venv (`source .venv/bin/activate`) before `dap debug`, or pass
`--python /path/to/venv/bin/python` explicitly. Without either, it falls
back to `python3` on `PATH`, which may not have `debugpy` installed or may
resolve to a different interpreter than the one the service actually runs
under (a common source of "the breakpoint never fires").

---

## Go -- Delve

**Check:** `dlv version`

**Install:**
- macOS: `brew install delve`, or `go install
  github.com/go-delve/delve/cmd/dlv@latest`
- Linux: `go install github.com/go-delve/delve/cmd/dlv@latest`

**macOS note:** debugging permissions may require `sudo DevToolsSecurity
-enable` once per machine.

**Container images:** a hardened/minimal golden image (see
`container-image-apko`) will not have `dlv` baked in by default -- and
shouldn't, in a production image. For remote debugging into a running
container, either build a debug variant image that includes `dlv`, or use
`kubectl debug` to bring a debug toolchain into the pod's process namespace
without changing the shipped image. See
`kubernetes-remote-debugging.md` in this directory.

---

## Node.js / TypeScript -- js-debug

`dap` auto-discovers `js-debug` from common locations:
- VS Code extensions (`~/.vscode/extensions/`)
- Cursor extensions (`~/.cursor/extensions/`)
- A standalone install at `~/.dap-cli/js-debug/`

**Check:** look in the paths above, or try `dap debug --backend js-debug
script.js` -- if it fails to find an adapter, install below.

**Standalone install** (only if none of the above is found): fetch the
latest `js-debug-dap-*.tar.gz` release from
`github.com/microsoft/vscode-js-debug/releases` and extract it to
`~/.dap-cli/js-debug/`.

Also supports Chrome DevTools debugging for browser-side JavaScript, which
is out of scope for this org's backend/service-focused use of `dap`.

---

## Rust / C / C++ -- lldb-dap

**Check:** `lldb-dap --version`

**Install:**
- macOS: `brew install llvm` (v18 or newer required)
- Linux: `apt install lldb`, or the equivalent for your distro

After a Homebrew install, put the Homebrew `llvm` bin directory ahead of
the system one on `PATH` (`export PATH="$(brew --prefix llvm)/bin:$PATH"`).

**Known gotcha:** the `lldb-dap` bundled with Xcode Command Line Tools
(v17) is missing the `--connection` flag `dap` requires. Use the Homebrew
`llvm` package (v18+) instead of the Xcode-provided one.

---

## .NET -- documented extension point, not shipped

No backend in `dap`'s current release drives a .NET debugger. This is a
gap being called out deliberately, not an oversight in this write-up: this
org runs .NET 8/10 services, and there is no verified `dap debug
service.dll` path today.

Two DAP-native .NET debuggers exist and would be the candidates for a
future backend, since `dap`'s daemon and Unix-socket protocol layer are
debugger-agnostic:

| Debugger | Maintainer | Transport | Redistribution |
| --- | --- | --- | --- |
| `netcoredbg` | Samsung (open source) | DAP over stdio/socket | Freely redistributable -- the more plausible fit for a standalone CLI backend |
| `vsdbg` | Microsoft | DAP over stdio/socket | Restricted to Microsoft's own tooling (VS/VS Code C# extension) -- harder to bundle into a third-party CLI |

Implementing either would mean satisfying `dap`'s `Backend` interface
(spawn the adapter process, build `launch`/`attach` argument maps, resolve
a PID-attach path) the same way the existing `debugpy` and `dlv` backends
do. Until that lands -- in `dap` upstream or in a fork this org chooses to
maintain -- debug .NET services with an IDE's own remote debugger (Rider or
VS Remote Debugger over SSH or into a container), or lean on
`dotnet-otel-patterns`'s trace/log tooling instead of a live debugger.
