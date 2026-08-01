// Condition-based waiting helpers for tests that currently guess at timing
// with Task.Delay(). See SKILL.md, "Condition-Based Waiting: Stop Guessing
// at Timing" -- a longer delay is a symptom fix; the underlying race is
// still there, just less likely to lose.
//
// Adapted from a real flaky-test fix in a background worker suite: a test
// awaited Task.Delay(300) hoping a Channel-based queue would drain 2
// items, which passed locally and failed in CI under load. Replacing the
// delay with WaitForAsync fixed it: pass rate went from roughly 70% to
// 100%, and the test got faster on the fast path.

using System;
using System.Threading;
using System.Threading.Tasks;

namespace Examples.SystematicDebugging;

public static class ConditionBasedWaiting
{
    /// <summary>
    /// Polls <paramref name="condition"/> every <paramref name="interval"/>
    /// until it returns a non-null value, or throws
    /// <see cref="TimeoutException"/> after <paramref name="timeout"/>.
    ///
    /// Use this instead of <c>await Task.Delay(N)</c> followed by an
    /// assertion -- it returns as soon as the condition is true and fails
    /// with a clear message if it never is.
    /// </summary>
    public static async Task<T> WaitForAsync<T>(
        Func<T?> condition,
        TimeSpan timeout,
        TimeSpan? interval = null,
        string description = "condition",
        CancellationToken cancellationToken = default)
        where T : class
    {
        var pollInterval = interval ?? TimeSpan.FromMilliseconds(10);
        var deadline = DateTime.UtcNow + timeout;

        while (DateTime.UtcNow < deadline)
        {
            if (condition() is { } value)
            {
                return value;
            }

            await Task.Delay(pollInterval, cancellationToken);
        }

        throw new TimeoutException(
            $"timed out waiting for {description} after {timeout}");
    }

    /// <summary>
    /// Overload for value-type conditions (counts, enum states) where the
    /// success predicate is separate from the returned value.
    /// </summary>
    public static async Task<T> WaitForAsync<T>(
        Func<T> valueSource,
        Func<T, bool> isReady,
        TimeSpan timeout,
        TimeSpan? interval = null,
        string description = "condition",
        CancellationToken cancellationToken = default)
        where T : struct
    {
        var pollInterval = interval ?? TimeSpan.FromMilliseconds(10);
        var deadline = DateTime.UtcNow + timeout;

        while (DateTime.UtcNow < deadline)
        {
            var value = valueSource();
            if (isReady(value))
            {
                return value;
            }

            await Task.Delay(pollInterval, cancellationToken);
        }

        throw new TimeoutException(
            $"timed out waiting for {description} after {timeout}");
    }
}

// Usage (in an xUnit test):
//
//     // BEFORE (flaky): guesses that the channel consumer drains 2 items
//     // within 300ms.
//     await producer.PublishAllAsync(items);
//     await Task.Delay(300);
//     Assert.Equal(2, consumer.ProcessedCount);  // fails randomly under load
//
//     // AFTER (reliable): waits for the actual condition.
//     await producer.PublishAllAsync(items);
//     var count = await ConditionBasedWaiting.WaitForAsync(
//         () => consumer.ProcessedCount,
//         count => count >= 2,
//         timeout: TimeSpan.FromSeconds(5),
//         description: "2 processed items");
//     Assert.True(count >= 2);
