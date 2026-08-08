#!/usr/bin/env bash
# Systematic Debugging — Quick Reference Framework

# ═══ THE 5-STEP METHOD ══════════════════════════════════════════
# 1. REPRODUCE → Can you make it happen consistently?
# 2. ISOLATE   → What's the smallest scope where it fails?
# 3. OBSERVE   → What does the system ACTUALLY do? (not what you think)
# 4. HYPOTHESIZE → What could explain ALL observations?
# 5. TEST      → Validate the hypothesis with a specific experiment

# ═══ REPRODUCE ══════════════════════════════════════════════════
# Key questions:
# - Does it happen every time or intermittently?
# - What's the minimum trigger? (specific input, time of day, load level)
# - Does it happen in other environments?
# If not reproducible: focus on collecting evidence when it DOES happen (logging, tracing)

# ═══ ISOLATE ═══════════════════════════════════════════════════
# Binary search technique:
# - Works in system A, fails in system B → what's different?
# - Works with input X, fails with input Y → what's different?
# - Worked yesterday, fails today → what changed? (git log, deploys, config)

# Diff between environments:
diff <(ssh working-host env | sort) <(ssh broken-host env | sort)
diff <(ssh working-host cat /etc/config) <(ssh broken-host cat /etc/config)

# ═══ OBSERVE (don't guess — look) ══════════════════════════════
# System calls:
strace -p "pid" -e trace=network -tt     # what network calls?
strace -p "pid" -e trace=file -tt        # what file operations?
strace -f -e trace=write -p "pid"        # what is it writing?

# Network:
tcpdump -i eth0 port 8080 -c 20         # what's on the wire?
ss -tnp | grep "pid"                    # what connections does it have?

# Filesystem:
lsof -p "pid"                            # what files are open?
inotifywait -mr /path -e modify          # watch for file changes

# ═══ HYPOTHESIZE (require evidence) ═════════════════════════════
# Good hypothesis: "The connection times out because the remote host
#   has a firewall rule blocking port 5432 from this subnet"
#   → Testable: telnet remote-host 5432 from this host vs another subnet
#
# Bad hypothesis: "It's probably a network issue"
#   → Not testable, too vague

# ═══ TEST (one variable at a time) ═════════════════════════════
# Change ONE thing, observe the result.
# If fixed → hypothesis confirmed.
# If not fixed → revert change, revise hypothesis.
# NEVER change multiple things simultaneously.

# ═══ ANTI-PATTERNS ══════════════════════════════════════════════
# ❌ "Let me try restarting" → loses evidence, doesn't find root cause
# ❌ Changing 3 things at once → can't know which fixed it
# ❌ "It works on my machine" → didn't isolate the environment diff
# ❌ Googling the error without reading it first → may be misleading
# ❌ Spending 2 hours without asking for help → escalate after 30min
# ❌ Assuming correlation = causation → temporal proximity ≠ cause

# ═══ WHEN TO ESCALATE ══════════════════════════════════════════
# - After 30 minutes without progress
# - When you need access/permissions you don't have
# - When the blast radius is growing while you investigate
# - When you're on your 3rd hypothesis without evidence
