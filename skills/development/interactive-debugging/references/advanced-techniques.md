# Advanced Debugging Techniques

## When the Program Hangs

A program that runs but never returns *is* information -- something is
stuck. Don't guess at where; interrupt and look.

```
Bug: program hangs (infinite loop or deadlock suspected)

dap pause
  -> the already-blocked debug/continue/step call returns its auto-context
     immediately: current location + locals for whatever was running
  Stopped at process() worker.py:55, locals: i=99999

dap threads
  -> are other threads/goroutines also blocked, or is it just this one?

dap eval "lock.locked()"
  -> test a specific deadlock hypothesis against live state

Root cause: lock acquired but never released on an early-return path.
```

The location where `pause` stops is the first real clue: a tight loop with
a counter that keeps climbing is a spin, not a deadlock; a thread parked
inside a lock/channel/mutex call with no counter moving is waiting on
something that will never arrive.

## Concurrency Bugs

If the code path looks correct but the values don't match what it should
produce, suspect another thread or goroutine mutating shared state
concurrently.

**First move at any concurrent crash or hang:** `dap threads`, then `dap
thread <id>` on every thread, not just the one currently stopped -- the
thread causing the problem is frequently not the one that happened to hit
the breakpoint or the one the runtime reported as stopped.

- **Deadlock signature:** two or more threads/goroutines each blocked
  waiting for a resource a *different* one currently holds. Confirm by
  reading each thread's top frame and cross-checking what it's waiting on
  against what the others hold.
- **Race signature:** a value that's correct at one stop and wrong at the
  next stop of the *same* breakpoint, with no code path in between that
  should have changed it. Look for shared mutable state reached without a
  lock, channel, or other synchronization primitive.

## Digging Into Complex State

A variable that's opaque in the default locals view (an object, a large
struct, a nested collection) can be expanded explicitly:

```bash
dap inspect data --depth 2
```

Remember the node cap noted in the main skill (roughly 100 nodes across the
whole expansion): a `--depth` that's technically large enough won't help if
the structure is wide rather than deep -- narrow with `dap eval
"data.some_field"` instead of expanding the whole tree.

## Bisecting Loops (Wolf Fence)

A loop of known length goes wrong somewhere inside it, and you don't know
where. Rather than stepping through every iteration, binary-search the
iteration count:

```bash
# Loop runs 0..999. Check the midpoint first.
dap debug app.py --break "app.py:45:i == 500"
dap eval "is_valid(result)"
  # True -> the bug is somewhere after iteration 500

# Move the condition to the midpoint of the remaining half, restart.
dap break add "app.py:45:i == 750"
dap restart
  # restart re-runs with the same args and the updated breakpoint set

# Repeat, halving the remaining range each time.
```

About 10 checks isolates the exact iteration in a 1,000-iteration loop --
log2(1000) rounds up to 10 -- versus stepping through the loop by hand,
which is O(n) in the worst case. The technique generalizes to any
monotonic property: the loop doesn't have to be numerically indexed, as
long as you can express "is the invariant still true here" as a
conditional-breakpoint expression and the property flips exactly once
across the range.

## Combining Techniques

These compose. A hang inside a loop that only manifests after many
iterations is: `dap pause` to find where it's stuck, `dap threads` to
confirm it's one thread and not a deadlock, then a conditional breakpoint
near the stuck location bisected against the iteration counter to find
*which* iteration's state first goes wrong -- rather than trying to hold
all three investigations in your head as a single step-by-step walk.
