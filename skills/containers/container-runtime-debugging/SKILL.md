---
name: container-runtime-debugging
description: "Debug crashing, hanging or misbehaving containers."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [docker, debugging, oom, crashloop, namespaces, cgroups, exit-code]
    category: containers
    related_skills: [docker-cli-operations, linux-process-management]
---
# Container Runtime Debugging

Diagnosing a container that crashes, restarts endlessly, hangs, or behaves
differently than the same code running directly on the host. Containers add
a layer of indirection (namespaces, cgroups, a different filesystem view)
that changes where to look, not what's fundamentally wrong.

## When to Use

Use when a container exits immediately, crash-loops, appears to hang with no
output, or a process behaves correctly on the host but fails identically the
same way inside a container.

## Start with the exit code

```bash
docker inspect -f '{{.State.ExitCode}} {{.State.Error}} {{.State.OOMKilled}}' myapp
```

| Exit code | Meaning |
| --- | --- |
| 0 | Clean exit |
| 1 | General application error |
| 125 | The `docker run` command itself failed (bad flag, etc.) |
| 126 | Container command found but not executable |
| 127 | Container command not found — often a typo in `CMD`/`ENTRYPOINT`, or a shell-form vs exec-form mistake |
| 137 | SIGKILL — check `OOMKilled` first; also `docker stop` after its grace period |
| 139 | SIGSEGV — a genuine crash in the binary |
| 143 | SIGTERM — a normal, graceful stop |

`.State.OOMKilled` distinguishes "the app crashed" from "the container's
memory limit killed it" for the otherwise-identical exit code 137 — always
check it before assuming a bug in the application.

## The container that exits immediately

```bash
docker run myapp                      # WITHOUT -d, to see the actual output
docker logs myapp
docker run -it --entrypoint sh myapp  # override the entrypoint to poke around
```

Common causes: the main process is not meant to run in the foreground (many
daemons daemonize by default and immediately exit, taking the container down
with them — needs a `-f`/foreground flag), a missing environment variable
the app requires at startup, or a shell-form `CMD` swallowing the real exit
code.

```dockerfile
CMD myapp --flag        # shell form: runs via /bin/sh -c, PID 1 is the shell
CMD ["myapp", "--flag"] # exec form: myapp itself IS pid 1
```

Shell form matters for signal handling — see below.

## Signals not reaching the application

A container's PID 1 does not get default kernel signal handling; the app
must explicitly handle `SIGTERM`, or the container simply waits out the
`docker stop` grace period and gets `SIGKILL`ed (visible as an unexpectedly
slow stop, then exit 137/143 confusion).

```bash
docker stop -t 30 myapp     # give it 30s instead of the 10s default
docker inspect -f '{{.Config.StopSignal}}' myapp
```

**Shell-form `CMD` is a common cause**: `CMD myapp` runs as `/bin/sh -c
"myapp"`, so the shell is PID 1 and the signal goes to the *shell*, not to
`myapp`. Depending on the shell, it may or may not forward `SIGTERM` to its
child. Exec-form `CMD ["myapp"]` makes the app itself PID 1, receiving
signals directly.

```dockerfile
# Shell wraps the process; signals may not propagate correctly.
CMD myapp
# App is PID 1 directly; signals go straight to it.
CMD ["myapp"]
# When a shell IS needed (variable expansion, etc.), exec replaces the shell:
CMD ["sh", "-c", "exec myapp --config ${CONFIG_PATH}"]
```

The `exec` inside the shell form is the fix: it replaces the shell process
with `myapp` instead of running it as a child, so `myapp` becomes PID 1.

## Crash-looping (Restart=always territory)

```bash
docker inspect -f '{{.RestartCount}}' myapp
docker logs --tail 50 myapp             # the LAST attempt's output, usually the useful one
docker events --filter container=myapp  # a timeline of start/die/restart
```

A restart policy hides the crash from `docker ps` (it shows "Up" again a
moment later) — `RestartCount` and `docker events` are what reveal that it's
actually looping. Temporarily override the restart policy while debugging so
a failed run stays inspectable instead of immediately restarting:

```bash
docker update --restart=no myapp
docker start -a myapp        # attached, so you see the crash directly
```

## Resource limits: OOM and CPU throttling

```bash
docker inspect -f '{{.State.OOMKilled}}' myapp
docker stats myapp --no-stream
cat /sys/fs/cgroup/system.slice/docker-<id>.scope/memory.events   # oom_kill counter
cat /sys/fs/cgroup/system.slice/docker-<id>.scope/cpu.stat        # throttling
```

The container's actual cgroup ID (the full 64-char one) is in `docker
inspect -f '{{.Id}}'`. The `system.slice/docker-<id>.scope` path above
assumes the default `systemd` cgroup driver; with the older `cgroupfs`
driver the same files live under `/sys/fs/cgroup/docker/<id>/` instead —
check `docker info -f '{{.CgroupDriver}}'` if the systemd path doesn't
exist. See `linux-process-management`'s cgroups v2 material for reading
these files — the same mechanism, just reached through Docker's path
convention instead of systemd's `system.slice`.

A container that's slow rather than crashed is worth checking for CPU
throttling (`cpu.stat`'s `nr_throttled`) before assuming an application bug
— a too-tight `--cpus` limit produces exactly this symptom.

## "Works on my host, fails in the container"

Usually one of:

- **Missing environment variable** — the host shell has it exported; the
  container's environment is isolated. `docker exec myapp env` shows what
  the container actually sees.
- **File not present** — a `.dockerignore` entry, or a file created by a
  step that ran on the host but wasn't `COPY`'d into the image.
- **Different libc** — Alpine's musl vs a host's/other base's glibc; a
  precompiled binary or native extension can fail to load or behave
  differently.
- **Networking assumptions** — `localhost` inside a container is the
  container itself, not the host. A service expecting to reach something on
  the host's `localhost` needs the container's actual network setup (a
  shared network, `host.docker.internal`, or `--network host`).
- **UID/permission mismatch** — a bind-mounted host directory owned by the
  host user may not be writable by the container's (different) user.

```bash
docker exec myapp env                       # what the container actually sees
docker exec myapp cat /etc/os-release       # confirm the actual base image
docker exec myapp id                        # UID/GID the process runs as
docker run --rm myapp ldd /app/binary       # missing shared libraries, if applicable
```

## No shell in the image (distroless, scratch)

```bash
docker cp myapp:/app/somefile ./           # copy files out without exec
docker inspect myapp                        # config, mounts, env -- no shell needed
```

For anything requiring an interactive look inside a shell-less container,
attach an ephemeral debug container sharing its namespaces (`--pid=container:`
and `--network=container:` have worked since Docker 1.12; this is a
long-standing pattern, not a new one — the rough equivalent of `kubectl
debug` for Kubernetes):

```bash
docker run -it --rm --pid=container:myapp --network=container:myapp \
    --cap-add SYS_PTRACE busybox sh
```

This gets a shell with visibility into the target container's process
namespace (so `ps` shows its processes) and network namespace (so
`localhost` matches its view), without needing a shell inside the target
image itself.

## Networking inside a container

```bash
docker exec myapp ip addr                  # if iproute2 is present
docker port myapp
docker network inspect bridge | grep -A3 myapp
ss -tlnp                                    # on the HOST, what's actually listening/published
```

"Connection refused" from outside a container almost always means the
application inside bound to `127.0.0.1` instead of `0.0.0.0` — a bind to
localhost is only reachable from inside that same network namespace, which
`docker exec` shares but the host and other containers do not.

## Pitfalls

- **Reading exit 137 as "the app crashed"** — check `OOMKilled` first; it's
  frequently the container's own memory limit.
- **Shell-form `CMD`** — breaks signal propagation to the actual process;
  use exec form or `exec` inside the shell.
- **Debugging while `--restart` is active** — the container restarts before
  you can inspect the failed state; disable it temporarily.
- **Binding to `127.0.0.1` inside the container** — unreachable from
  outside; bind to `0.0.0.0`.
- **Assuming `localhost` inside a container means the host** — it means the
  container's own network namespace.
- **Forgetting a bind-mounted directory's ownership doesn't automatically
  match the container's user** — permission errors that don't reproduce on
  the host.

## Reference

- `docker-cli-operations` — the commands used throughout this skill
- `linux-process-management` — signals, `/proc`, cgroups in depth

## When NOT to use

- Image build failures (not runtime) — use `dockerfile-authoring`
- Docker Compose stack orchestration issues — use `docker-compose-patterns`
- Kubernetes pod crash loops (not bare Docker) — use `eks-management` or `eks-node-troubleshooting`

## Related skills

- `docker-cli-operations` — `docker exec`, `docker logs`, `docker inspect` for live debugging
- `dockerfile-authoring` — when the fix requires rebuilding the image
- `container-image-optimization` — when bloated images cause OOM or slow starts
- `interactive-debugging` — when you need breakpoints inside the container process
- `docker-compose-patterns` — when the issue is inter-container networking/deps
