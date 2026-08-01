# Kubernetes Remote Debugging

`dap debug --attach host:port` needs a debug adapter already listening
somewhere reachable. In this org's container-native workloads (see
`eks-management`), getting that port reachable from your shell means
`kubectl port-forward`, and getting a debugger running inside the pod in
the first place is the part that actually differs by environment and by
how careful you need to be about the target's blast radius.

There are two workflows, and they trade off differently against
`k8s-safety`:

## Workflow A -- DEV/HML pod with a debug listener already built in

Appropriate when the service's DEV image is allowed to carry a debugger
(it usually should not be the same image promoted to PRD -- see
`container-image-apko` for the golden-image policy behind why a hardened
image stays minimal).

1. Confirm the debug listener is actually enabled for this pod. For a
   Python service this typically means the entrypoint conditionally starts
   under `debugpy` when an env var is set, e.g.:

   ```bash
   # inside the container's entrypoint, gated by an env var set via Helm values
   python -m debugpy --listen 0.0.0.0:5678 --wait-for-client -m uvicorn app:app
   ```

   You cannot inject `debugpy` into an already-running Python process from
   outside it without ptrace-level tricks that this org doesn't rely on --
   the listener has to be started as (or very early in) the process, which
   means this is a decision made at deploy time, not at debug time.

2. Forward the port (read-only under `k8s-safety`, no approval needed):

   ```bash
   kubectl config current-context
   kubectl get pods -n <namespace> -l app=<service>
   kubectl port-forward pod/<pod-name> -n <namespace> 5678:5678
   ```

3. Attach from another shell:

   ```bash
   dap debug --attach localhost:5678 --backend debugpy --session <pod-name>
   ```

For Go, the equivalent is starting the binary under `dlv --headless
--listen=:2345 --api-version=2 exec ./server` as the container's
entrypoint (again, an image/Helm-values decision, not something you toggle
after the pod is already running), then:

```bash
kubectl port-forward pod/<pod-name> -n <namespace> 2345:2345
dap debug --attach localhost:2345 --backend dlv --session <pod-name>
```

## Workflow B -- ephemeral container, no image rebuild (PRD-safe pattern)

Preferred whenever the target pod's image should stay exactly as shipped
-- including any PRD investigation, and any DEV/HML pod where nobody
thought to bake in a debug listener ahead of time. `kubectl debug` attaches
a throwaway container into the pod's existing process/network namespace
without modifying the pod's spec permanently.

```bash
# Requires approval under k8s-safety -- this creates an ephemeral
# container, which is a mutating operation, unlike port-forward.
kubectl debug -it <pod-name> -n <namespace> \
  --image=<debug-image-with-dlv-or-debugpy> \
  --target=<container-name>
```

Inside the ephemeral container's shell, the target container's processes
are visible in the same PID namespace because of `--target`, which sets
the ephemeral container's `targetContainerName` (`--share-processes` is a
different flag that only applies to the separate `--copy-to` workflow,
which clones the whole pod instead of attaching to the live one -- it does
nothing here and should not be included in this command). Find the
target process and attach the debugger to it from inside the ephemeral
container:

```bash
# Go example, from inside the ephemeral container
ps aux | grep server            # find the target PID in the shared namespace
dlv attach --headless --listen=:2345 --api-version=2 <PID>
```

Then, from your own shell, `kubectl port-forward` to the ephemeral
container's exposed debug port (the exact mechanism depends on whether the
ephemeral container binds a port reachable via the pod's existing network
namespace -- it shares the pod's network namespace by default, so binding
`:2345` inside the ephemeral container makes it reachable the same way as
Workflow A):

```bash
kubectl port-forward pod/<pod-name> -n <namespace> 2345:2345
dap debug --attach localhost:2345 --backend dlv --session <pod-name>-ephemeral
```

This is why `kubectl debug` and `kubectl port-forward` show up on
different sides of the `k8s-safety` approval line even though they're used
together here: forwarding a port is read-only observation of the network
path, but adding an ephemeral container is a mutation of the pod's runtime
state (a new container in its spec, however short-lived), and needs the
same explicit-approval treatment as any other write operation against a
live cluster.

## Never do this against live production traffic

Attaching a blocking debugger (`--pid`, or `--attach` to a listener you
just started) to the container that is actually serving requests means
every request in flight on that process stalls for as long as you're
paused at a breakpoint. If the investigation must happen against PRD data
or PRD-only reproduction conditions, prefer Workflow B against a pod that
has already been cordoned off from the traffic path (scaled out of the
Service's endpoints, or a dedicated forensic replica), not the pod
currently receiving load.

## .NET

Neither workflow above has a working backend today -- see
`backend-install.md`'s .NET section. If a `netcoredbg`-backed `dap` fork
exists in the future, the same two workflows apply unchanged: Workflow A
starts the service under `netcoredbg --interpreter=vscode` instead of
`dlv --headless`/`debugpy --listen`, and Workflow B attaches `netcoredbg`
to the shared-namespace PID from inside the ephemeral container the same
way. Until then, use an IDE's own remote debugger over the same
`kubectl port-forward`, or rely on `dotnet-otel-patterns` trace/log
tooling instead of a live attach.
