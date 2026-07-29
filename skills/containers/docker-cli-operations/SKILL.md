---
name: docker-cli-operations
description: "Run, inspect and debug containers with the Docker CLI."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [docker, cli, containers, volumes, networks, logs, exec]
    category: containers
    related_skills: [dockerfile-authoring, container-runtime-debugging, docker-compose-patterns, linux-process-management]
---
# Docker CLI Operations

The day-to-day Docker CLI: running containers correctly, managing volumes and
networks, reading logs, and cleaning up without destroying something in use.

## When to Use

Use when running a container for the first time, debugging why a container
exited, managing persistent data, connecting containers on a network, or
reclaiming disk space from Docker's accumulated state.

## Running containers

```bash
docker run -d --name myapp -p 8080:80 nginx:1.27
docker run -it --rm ubuntu:24.04 bash          # interactive, auto-remove on exit
docker run -d --restart unless-stopped myapp   # survive daemon/host restart
docker run -d -e KEY=value -e ANOTHER=val myapp
docker run -d --env-file .env myapp
docker run -d --memory=512m --cpus=1.5 myapp
docker run -d -v /host/path:/container/path myapp     # bind mount
docker run -d -v myvolume:/data myapp                  # named volume
```

| Flag | Effect |
| --- | --- |
| `-d` | Detached (background) |
| `-it` | Interactive with a TTY — for shells, not services |
| `--rm` | Remove the container on exit — good for one-off/debug runs |
| `--name` | A stable name instead of a random one |
| `-p host:container` | Publish a port |
| `--restart` | `no`, `on-failure[:N]`, `unless-stopped`, `always` |
| `-v` / `--mount` | Volumes/bind mounts; `--mount` is more explicit and preferred in scripts |

`--restart always` restarts even after a deliberate `docker stop` followed by
a daemon restart; `unless-stopped` respects an explicit stop. This mirrors
the same distinction as systemd's `Restart=always` vs `on-failure`.

## Inspecting running containers

```bash
docker ps                          # running only
docker ps -a                       # everything, including exited
docker ps --filter status=exited
docker inspect myapp                # full JSON: config, mounts, network, state
docker inspect -f '{{.State.ExitCode}}' myapp
docker top myapp                    # processes inside, from the host's view
docker stats                        # live CPU/memory/network per container
docker port myapp                   # published port mappings
```

`docker inspect` with `-f` (Go template) extracts a single field, which is
what makes it scriptable:

```bash
docker inspect -f '{{.NetworkSettings.IPAddress}}' myapp
docker inspect -f '{{.State.Health.Status}}' myapp
```

## Logs

```bash
docker logs myapp
docker logs -f myapp                    # follow
docker logs --since 10m myapp
docker logs --tail 100 -f myapp
docker logs -t myapp                    # with timestamps
```

`docker logs` reads whatever the container's logging driver captured —
by default, stdout/stderr of PID 1 in the container. A process that logs to
a file *inside* the container instead of stdout will not appear here at
all; fix the application to log to stdout, or `docker exec` in to read the
file directly.

## Executing inside a running container

```bash
docker exec -it myapp bash
docker exec -it myapp sh              # when bash isn't installed (Alpine, distroless)
docker exec myapp env
docker exec -u root myapp whoami      # as a different user than the container's default
```

`docker exec` runs an *additional* process in the container's existing
namespaces — it does not restart or affect the main process. `distroless`
images have no shell at all; use `docker cp` or `kubectl debug`-style
ephemeral debug containers instead (see `container-runtime-debugging`).

## Copying files

```bash
docker cp myapp:/app/config.yaml ./local-config.yaml
docker cp ./local-file.txt myapp:/tmp/
```

Works even on a stopped container, and works regardless of whether the
container has a shell — useful for a distroless image with no `exec` option.

## Volumes

```bash
docker volume create myvolume
docker volume ls
docker volume inspect myvolume
docker volume rm myvolume
docker volume prune                    # remove all UNUSED volumes
```

| Type | Managed by | Survives container removal | Use when |
| --- | --- | --- | --- |
| Named volume | Docker | Yes | Persistent data, portable across hosts |
| Bind mount | You (host path) | Yes (it's just a host path) | Local dev, mounting source code |
| tmpfs | Docker, in-memory | No | Secrets or scratch data that must never hit disk |

```bash
docker run -d --mount type=tmpfs,destination=/app/secrets myapp
```

A named volume's actual data lives under `/var/lib/docker/volumes/` on the
host — inspect it there directly only as a last resort; prefer
`docker run --rm -v myvolume:/data alpine ls /data` to look inside safely.

## Networks

```bash
docker network ls
docker network create mynet
docker network inspect mynet
docker run -d --network mynet --name db postgres
docker run -d --network mynet --name api myapp    # can reach `db` by name
docker network connect mynet existing-container
docker network disconnect mynet existing-container
```

Containers on the same **user-defined** network resolve each other by
container name automatically, via Docker's embedded DNS. The default
`bridge` network does **not** provide this — it's a common reason
"container A can't reach container B by name" turns out to be both
containers sitting on the default network instead of a shared user-defined
one.

```bash
docker network create mynet
docker run -d --network mynet --name db postgres
docker run -it --network mynet alpine ping db     # works
docker run -it --network bridge alpine ping db    # fails: different network, no DNS
```

## Cleanup

```bash
docker ps -aq | xargs -r docker rm            # remove all stopped containers
docker container prune                         # same, built-in
docker image prune                              # remove dangling (untagged) images
docker image prune -a                           # remove ALL unused images
docker volume prune                              # remove unused volumes
docker system prune -a --volumes                 # everything unused, aggressively
docker system df                                 # see what's using space, before pruning
```

**Always run `docker system df` before an aggressive prune** — `--volumes`
removes unused named volumes, which is unrecoverable if that volume held data
nobody had a running container attached to at the time.

## Debugging a container that exits immediately

```bash
docker run myapp                    # WITHOUT -d, see the actual output/error
docker logs myapp                   # if it already exited
docker inspect -f '{{.State.ExitCode}}' myapp
docker inspect -f '{{.State.Error}}' myapp
docker run -it --entrypoint sh myapp   # override the entrypoint to get a shell instead
```

Exit code conventions carry over directly from the process running as PID 1
inside the container — 137 is SIGKILL (often the OOM killer, or `docker
stop` after its grace period), 143 is SIGTERM (a normal stop). This is the
quick check; for the full exit-code table, shell-form `CMD` signal issues,
and crash-loop diagnosis, see `container-runtime-debugging`. For the
underlying signal/exit-code mapping outside Docker, see
`linux-process-management`.

## Resource limits and why they matter

```bash
docker run -d --memory=512m --memory-swap=512m --cpus=1.5 myapp
docker stats myapp --no-stream       # current usage vs limit, one-shot
```

`--memory-swap` equal to `--memory` disables swap for the container
entirely; leaving it unset allows swap up to `2x --memory` by default, which
can mask a memory problem by turning an OOM kill into severe slowness
instead. These map directly onto cgroup v2 `memory.max` — see
`linux-process-management` for what's actually enforcing the limit.

## Pitfalls

- **Expecting containers to see each other by name on the default `bridge`
  network** — only user-defined networks provide embedded DNS.
- **`docker system prune --volumes` without checking `docker system df`
  first** — can delete data with no warning beyond "unused".
- **Assuming `docker logs` shows everything** — only stdout/stderr of PID 1;
  a process logging to a file inside the container is invisible to it.
- **`docker stop` timing out and force-killing** — the default grace period
  is 10s; a slow-shutdown app needs `--stop-timeout` raised, or it will
  always exit 137 instead of cleanly.
- **Bind-mounting over an image's existing directory in dev** — can hide
  files that exist in the image but not on the host, causing confusing
  "missing file" errors that don't reproduce in the built image.
- **Not pinning image tags** — `myapp:latest` is not reproducible; a
  redeploy can silently pull a different image than what was tested.

## Reference

- `dockerfile-authoring` — building the images these commands run
- `container-runtime-debugging` — deeper diagnosis when a container misbehaves
- `docker-compose-patterns` — orchestrating multiple containers together
- `linux-process-management` — signals, `/proc`, and cgroups underneath these commands
