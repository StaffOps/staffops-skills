#!/usr/bin/env bash
# Docker CLI Cheat Sheet — copy-paste commands

# ═══ BUILD ═══════════════════════════════════════════════════════
docker build -t myapp:v1 .
docker build --platform linux/amd64,linux/arm64 -t myapp:v1 --push .
docker build --no-cache -t myapp:v1 .                    # force fresh build
docker build --target builder -t myapp:debug .           # stop at stage

# ═══ RUN ═════════════════════════════════════════════════════════
docker run --rm -it alpine sh                            # ephemeral shell
docker run --rm -d -p 8080:8080 --name app myapp:v1     # detached with port
docker run --rm -v "$(pwd):/src" -w /src golang:1.25 go test ./...  # throwaway build
docker run --rm --network host myapp:v1                  # use host network
docker run --rm -e MY_VAR=value --env-file .env myapp:v1 # env vars
docker run --rm --memory=512m --cpus=1.0 myapp:v1       # resource limits
docker run --rm --user 65534:65534 myapp:v1             # run as nobody

# ═══ INSPECT ═════════════════════════════════════════════════════
docker ps                                                # running containers
docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
docker logs -f --tail 100 <container>                    # follow logs
docker logs --since 5m <container>                       # last 5 minutes
docker inspect <container> | jq '.[0].State'             # container state
docker inspect <container> | jq '.[0].NetworkSettings.Networks'
docker stats --no-stream                                 # resource usage snapshot
docker top <container>                                   # processes in container

# ═══ EXEC / DEBUG ════════════════════════════════════════════════
docker exec -it <container> sh                           # shell into running
docker exec <container> cat /etc/os-release              # check distro
docker cp <container>:/app/config.yaml ./config.yaml     # copy file out
docker diff <container>                                  # filesystem changes

# ═══ IMAGES ══════════════════════════════════════════════════════
docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"
docker image prune -f                                    # remove dangling
docker image prune -a --filter "until=72h"               # remove unused >3d
docker history --no-trunc myapp:v1                       # layer breakdown
docker manifest inspect myapp:v1                         # multi-arch info
docker save myapp:v1 | gzip > myapp-v1.tar.gz           # export image
docker load < myapp-v1.tar.gz                           # import image

# ═══ CLEANUP ═════════════════════════════════════════════════════
docker system df                                         # disk usage
docker system prune -f                                   # containers+images+networks
docker system prune -a --volumes                         # EVERYTHING (careful!)
docker volume prune -f                                   # unused volumes
docker network prune -f                                  # unused networks

# ═══ REGISTRY ════════════════════════════════════════════════════
docker login registry.example.com
docker tag myapp:v1 registry.example.com/team/myapp:v1
docker push registry.example.com/team/myapp:v1
docker pull --platform linux/arm64 myapp:v1              # specific arch
crane digest registry.example.com/team/myapp:v1         # get SHA without pull
