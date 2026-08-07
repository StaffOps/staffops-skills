---
name: docker-compose-patterns
description: "Compose multi-container apps with healthchecks and profiles."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [docker-compose, compose, multi-container, healthcheck, dependencies]
    category: containers
    related_skills: [docker-cli-operations, dockerfile-authoring]
---
# Docker Compose Patterns

Defining multi-container applications declaratively: service dependencies
that actually wait for readiness (not just process start), environment
layering across dev/staging, and the profile/override patterns that keep one
`compose.yaml` usable everywhere.

## When to Use

Use when running an app plus its dependencies (database, cache, queue)
locally, defining a reproducible dev environment, or structuring
environment-specific overrides without duplicating the whole file.

## A complete example

```yaml
# compose.yaml
services:
  api:
    build: .
    ports:
      - "8080:8080"
    environment:
      DATABASE_URL: postgres://user:pass@db:5432/app
    depends_on:
      db:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 10s
      timeout: 3s
      retries: 3
      start_period: 15s

  db:
    image: postgres:16
    environment:
      POSTGRES_PASSWORD: pass
    volumes:
      - dbdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 3s
      retries: 5

volumes:
  dbdata:
```

## depends_on: order vs readiness

```yaml
depends_on:
  db:
    condition: service_started    # only waits for the container to START
depends_on:
  db:
    condition: service_healthy    # waits for the HEALTHCHECK to pass
```

**Plain `depends_on: [db]` (or `condition: service_started`) only guarantees
startup order, not readiness.** Postgres's container process starts in
milliseconds; the database itself takes longer to accept connections. An app
that depends on `service_started` will race the database and fail its first
few connection attempts — `condition: service_healthy` is what actually
waits.

This means every service that another depends on needs a real
`healthcheck:` — without one, `condition: service_healthy` has nothing to
wait for and Compose will refuse to start (or wait forever, depending on
version).

## Healthchecks

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
  interval: 10s      # how often to check
  timeout: 3s         # how long a single check may take
  retries: 3           # consecutive failures before "unhealthy"
  start_period: 15s    # grace period during startup, failures don't count yet
```

`start_period` matters for anything with a real startup cost (JVM warmup, a
migration step) — without it, a slow-but-healthy start can be marked
unhealthy before the app has had a chance to become ready, and dependents
waiting on `service_healthy` will fail even though the app would have
succeeded moments later.

`CMD` runs the command directly (array form, no shell); `CMD-SHELL` runs it
through `/bin/sh -c`, needed for shell features like pipes:

```yaml
test: ["CMD-SHELL", "pg_isready -U postgres || exit 1"]
```

## Environment layering

Compose merges `compose.yaml` with an optional `compose.override.yaml`
automatically, and lets you specify additional files explicitly:

```bash
docker compose up                                        # base + override, automatically
docker compose -f compose.yaml -f compose.prod.yaml up    # base + prod, explicit
```

```yaml
# compose.override.yaml -- loaded automatically, meant for local dev
services:
  api:
    volumes:
      - .:/app              # live-reload the source
    environment:
      DEBUG: "true"
    ports:
      - "9229:9229"          # debugger port, dev only
```

```yaml
# compose.prod.yaml -- loaded explicitly, never automatically
services:
  api:
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 512M
```

Later files override matching keys from earlier ones; lists are replaced,
not merged, except where Compose specifically documents append behavior
(like additional `environment` entries under some configurations) — when in
doubt, verify with `docker compose config` (below).

Compose also reads a `.env` file in the project directory automatically and
substitutes `${VAR}` / `${VAR:-default}` references anywhere in the YAML
(not just under `environment:`) — this is separate from `env_file:`, which
only injects variables into a specific service's container environment:

```yaml
services:
  api:
    image: myapp:${TAG:-latest}   # substituted from .env or the shell at parse time
    env_file:
      - .env.api                  # injected into the container's env, not used for substitution
```

An undefined variable in a `${VAR}` reference silently substitutes an empty
string rather than failing the build — `docker compose config` (below)
catches this before it becomes a confusing runtime error.

## Profiles: optional services

```yaml
services:
  api:
    image: myapp

  debug-tools:
    image: netshoot
    profiles: ["debug"]

  seed-data:
    image: myapp
    command: ["./seed.sh"]
    profiles: ["setup"]
```

```bash
docker compose up                        # api only -- profiled services are skipped
docker compose --profile debug up        # api + debug-tools
docker compose --profile setup run seed-data
```

Profiles are the correct way to keep optional/occasional services (a
one-time seeder, a debug sidecar) in the same file without them starting on
every `up`.

## Networking between services

Every service in a Compose file joins a default network automatically and
can reach every other service **by its service name** — this is the
Compose-level equivalent of the user-defined Docker network DNS behavior:

```yaml
services:
  api:
    environment:
      DATABASE_URL: postgres://db:5432/app   # "db" resolves via Compose's network
  db:
    image: postgres:16
```

No `--network` flag or manual network creation needed for services in the
same file — that manual step only matters when connecting a Compose-managed
service to something outside the Compose project.

## Named volumes vs bind mounts

```yaml
services:
  db:
    volumes:
      - dbdata:/var/lib/postgresql/data   # named volume: Docker-managed, portable
      - ./config:/etc/app:ro               # bind mount: host path, read-only

volumes:
  dbdata:               # must be declared at the top level to be a named volume
```

Forgetting the top-level `volumes:` declaration silently turns what looks
like a named volume reference into an anonymous one recreated on every
`down` — data loss on the next `docker compose down && up` cycle. Always
declare named volumes explicitly.

## Scaling and replicas (local, not a real orchestrator)

```bash
docker compose up --scale worker=3
```

```yaml
services:
  worker:
    image: myapp
    # a fixed host port conflicts across replicas -- don't publish one
    # for a service you intend to scale
```

Compose scaling is useful for local load-testing a worker pool; it is not a
substitute for a real scheduler (Kubernetes, Swarm) for production traffic
distribution.

## Inspecting the resolved configuration

```bash
docker compose config              # the FINAL merged config, after all overrides
docker compose config --services   # just the service names
docker compose ps
docker compose logs -f api
docker compose exec api sh
```

`docker compose config` is the single most useful debugging command when
layered files produce an unexpected result — it shows exactly what Compose
resolved, removing the guesswork about merge order.

## Pitfalls

- **`depends_on` without `condition: service_healthy`** — only orders
  container start, not application readiness; races against slow-starting
  dependencies.
- **A dependency with no `healthcheck:`** — `service_healthy` has nothing to
  check.
- **Missing `start_period`** — a slow-but-fine startup gets marked unhealthy.
- **Forgetting the top-level `volumes:` declaration** — silently becomes an
  anonymous volume, lost on `down`.
- **Publishing a fixed host port on a service you `--scale`** — the
  replicas fight over the same port and fail to start.
- **Assuming override files merge lists** — verify with
  `docker compose config` instead of assuming.
- **Committing `compose.override.yaml` with dev-only secrets** — it loads
  automatically for everyone; keep secrets out of it or gitignore it.
- **Adding a top-level `version:` key** — obsolete since the Compose
  Specification merged the old 2.x/3.x schemas; the `docker compose` CLI
  (v2) ignores it and prints a warning. Newer files should be named
  `compose.yaml` (still recognized: `docker-compose.yaml`) with no
  `version:` key at all.
- **Assuming an unset `${VAR}` fails the build** — it silently substitutes
  an empty string; check `docker compose config` for surprises.

## Reference

- `docker-cli-operations` — the underlying `docker` commands Compose wraps
- `dockerfile-authoring` — building the images referenced by `build:`

## When NOT to use

- Production Kubernetes deployments — use `helm-chart-app` or `argocd-patterns`
- Single-container operations (run/exec/logs) — use `docker-cli-operations`
- Debugging a specific container that crashes — use `container-runtime-debugging`

## Related skills

- `docker-cli-operations` — single-container commands used within compose workflows
- `container-runtime-debugging` — diagnosing crashes in compose services
- `dockerfile-authoring` — writing the Dockerfiles that compose services build
- `helm-chart-app` — when the compose stack graduates to Kubernetes
