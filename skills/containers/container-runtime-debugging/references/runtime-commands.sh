#!/usr/bin/env bash
# Container Runtime Debugging — crictl / nerdctl / ctr
# Use ON THE NODE (ssh/nsenter), not from your laptop

# ═══ CRICTL (CRI — works with containerd/CRI-O) ════════════════
# Config: /etc/crictl.yaml → runtime-endpoint: unix:///run/containerd/containerd.sock

crictl ps                                      # running containers
crictl ps -a                                   # all (including exited)
crictl pods                                    # list pods (CRI concept)
crictl pods --state Ready                      # only ready pods
crictl inspect <container-id>                  # full container JSON
crictl inspect <cid> | jq '.status.state'      # container state
crictl logs <container-id>                     # stdout/stderr
crictl logs --tail 50 <container-id>           # last 50 lines
crictl exec -it <container-id> sh             # shell into container
crictl stats                                   # resource usage
crictl images                                  # list pulled images
crictl rmi <image-id>                          # remove image
crictl inspecti <image-id>                     # image details

# Pod-level operations
crictl runp pod-config.json                    # create pod sandbox
crictl stopp <pod-id>                          # stop pod
crictl rmp <pod-id>                            # remove pod

# ═══ NERDCTL (Docker-compatible CLI for containerd) ═════════════
nerdctl ps                                     # like docker ps
nerdctl logs -f <container>
nerdctl exec -it <container> sh
nerdctl inspect <container>
nerdctl images --format "{{.Repository}}:{{.Tag}} {{.Size}}"
nerdctl system prune -a                        # cleanup

# Namespace matters (k8s uses k8s.io namespace):
nerdctl -n k8s.io ps                           # k8s containers
nerdctl -n k8s.io images                       # k8s images

# ═══ CTR (low-level containerd CLI) ═════════════════════════════
ctr --namespace k8s.io containers list         # raw container list
ctr --namespace k8s.io images list             # raw image list
ctr --namespace k8s.io tasks list              # running tasks (PIDs)
ctr --namespace k8s.io content ls              # content store
ctr --namespace k8s.io snapshots ls            # filesystem snapshots

# ═══ DEBUGGING STUCK CONTAINERS ═════════════════════════════════
# Container won't start:
crictl inspect <cid> | jq '.status.reason'
crictl inspect <cid> | jq '.info.runtimeSpec.process'  # see entrypoint
journalctl -u containerd --since "5min ago"   # containerd logs

# OOMKilled:
crictl inspect <cid> | jq '.status.resources.linux.memory_limit_in_bytes'
dmesg | grep -i "oom\|killed"

# Image pull failures:
crictl pull --creds user:pass registry/image:tag
journalctl -u containerd | grep -i "pull\|auth\|tls"

# ═══ USEFUL NODE-LEVEL COMMANDS ═════════════════════════════════
# Filesystem usage per container:
du -sh /var/lib/containerd/io.containerd.snapshotter.v1.overlayfs/snapshots/*/fs 2>/dev/null | sort -rh | head

# Containerd socket check:
ctr version

# Restart containerd (last resort):
systemctl restart containerd
