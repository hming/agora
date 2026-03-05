# Why AGORA?

## The Hidden Assumption in "One Agent, One Task"

This model works — but only if something handles these four things:

1. **Which task goes to which agent** (preventing two agents from claiming the same task)
2. **Task B depends on Task A — who notifies B when A is done?**
3. **An agent crashes mid-execution — how is the task reassigned?**
4. **All tasks are done — who declares the overall goal achieved?**

That "something" is either a central scheduler you write yourself, or AGORA.

---

## If You Write Your Own Central Scheduler

```
Your scheduler
  ├── Maintain a task state table (pending/running/done/failed)
  ├── Assign tasks to agents (needs a concurrency lock to avoid double-assignment)
  ├── Monitor each agent's heartbeat (detect failures)
  ├── Reassign tasks after failure (need to know which tasks that agent held)
  ├── Track DAG dependencies, unlock downstream tasks
  └── Determine when the overall goal is complete
```

You just reinvented AGORA — but more fragile:
- Scheduler crashes → entire system halts
- Scheduler restarts → task state is lost
- Only the scheduler knows global state → all other agents are blind to overall progress

---

## What AGORA Actually Is

AGORA is not a tool for "making agents execute tasks." It is the act of **extracting coordination logic from a central node and placing it in a shared log**.

```
Without AGORA:   Agent A → [Central Scheduler] → Agent B
                                   ↑
                             Single point of failure
                             Opaque state
                             Lost on restart

With AGORA:      Agent A → [Square Log] ← Agent B
                                   ↑
                             Readable by anyone
                             Persistent
                             Agent failure doesn't affect the log
```

Both approaches solve the same coordination problem. The difference is: **where does the coordination state live?**

---

## When You Genuinely Don't Need AGORA

If your scenario satisfies **all** of the following:

- Tasks have **no dependencies** (all parallel and independent)
- **Duplicate execution is fine** (idempotent tasks — running twice is harmless)
- **Failure doesn't matter** (if an agent crashes, that's okay)
- **Single run** — no need for persistent state
- **Single caller** — no competition between multiple agents

Then you really don't need AGORA. A simple `for` loop that spawns tasks is enough.

---

## Conclusion

AGORA's value: **when tasks have dependencies, competition, and failures, you have no choice but to solve the coordination problem — AGORA means you don't have to build a more fragile wheel yourself.**
