// Package waitfor provides condition-based waiting helpers for tests that
// currently guess at timing with time.Sleep. See SKILL.md, "Condition-Based
// Waiting: Stop Guessing at Timing" -- a longer sleep is a symptom fix; the
// underlying race is still there, just less likely to lose.
//
// Adapted from a real flaky-test fix: a worker pool test slept a fixed
// 300ms hoping N jobs would finish, which passed locally and failed under
// CI load. Replacing the sleep with WaitForCount fixed it: pass rate went
// from roughly 70% to 100%, and the test got faster because it no longer
// waited the full 300ms on the fast path.
package waitfor

import (
	"context"
	"fmt"
	"sync"
	"time"
)

// Condition is polled until it returns true or the timeout elapses.
type Condition func() bool

// WaitFor polls cond every interval until it returns true or ctx is done.
// Prefer this over time.Sleep followed by an assertion: it succeeds as soon
// as the condition is true, and fails with a clear message instead of a
// flaky assertion mismatch.
func WaitFor(ctx context.Context, cond Condition, interval time.Duration) error {
	if cond() {
		return nil
	}

	ticker := time.NewTicker(interval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return fmt.Errorf("condition not met: %w", ctx.Err())
		case <-ticker.C:
			if cond() {
				return nil
			}
		}
	}
}

// EventSink is the minimal interface WaitForCount needs -- satisfied by any
// thread-safe counter (a job queue's completed count, a channel-backed
// event log, a metrics registry's local snapshot).
type EventSink interface {
	Count() int
}

// counter is a trivial thread-safe EventSink used by the example below and
// by tests of this package.
type counter struct {
	mu sync.Mutex
	n  int
}

func (c *counter) Inc() {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.n++
}

func (c *counter) Count() int {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.n
}

// WaitForCount waits until sink.Count() reaches at least want, polling
// every 10ms. This is the Go equivalent of the TypeScript waitForEventCount
// helper this example replaces: same shape, same guarantee (poll for the
// actual state, not a guessed duration).
func WaitForCount(sink EventSink, want int, timeout time.Duration) error {
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()

	return WaitFor(ctx, func() bool {
		return sink.Count() >= want
	}, 10*time.Millisecond)
}

// Usage (in a _test.go file):
//
//	// BEFORE (flaky): guesses that 2 jobs finish within 300ms.
//	pool.SubmitAll(jobs)
//	time.Sleep(300 * time.Millisecond)
//	if got := results.Count(); got != 2 {
//	    t.Fatalf("want 2 results, got %d", got)
//	}
//
//	// AFTER (reliable): waits for the actual condition, fails fast with a
//	// clear error if it is never met.
//	pool.SubmitAll(jobs)
//	if err := WaitForCount(results, 2, 5*time.Second); err != nil {
//	    t.Fatal(err)
//	}
