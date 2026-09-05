"""Meridian churn report -- a loop you can trust.

Book I, Chapter 1 lab. Deterministic. Boring. That's the point.
"""

from dataclasses import dataclass, replace
from enum import Enum

# ---------------------------------------------------------------
# STATE -- everything the loop knows, in one place, immutable.
# ---------------------------------------------------------------

class Phase(str, Enum):
    LOAD = "load"
    COMPUTE = "compute"
    SEGMENT = "segment"
    REPORT = "report"
    DONE = "done"

@dataclass(frozen=True)          # yes, frozen. The word will follow us around.
class State:
    phase: Phase = Phase.LOAD
    step: int = 0
    accounts: tuple = ()
    churn_rate: float | None = None
    segments: tuple = ()
    report: str | None = None

# ---------------------------------------------------------------
# THE BODY -- what happens during a step. Hand-written, every line.
# ---------------------------------------------------------------

RAW = (
    {"id": "A-01", "plan": "basic",      "cancelled": True},
    {"id": "A-02", "plan": "basic",      "cancelled": True},
    {"id": "A-03", "plan": "basic",      "cancelled": False},
    {"id": "A-04", "plan": "pro",        "cancelled": True},
    {"id": "A-05", "plan": "pro",        "cancelled": False},
    {"id": "A-06", "plan": "pro",        "cancelled": False},
    {"id": "A-07", "plan": "pro",        "cancelled": False},
    {"id": "A-08", "plan": "enterprise", "cancelled": False},
    {"id": "A-09", "plan": "enterprise", "cancelled": False},
    {"id": "A-10", "plan": "enterprise", "cancelled": False},
)

def load(s: State) -> State:
    return replace(s, phase=Phase.COMPUTE, accounts=RAW)

def compute(s: State) -> State:
    cancelled = sum(1 for a in s.accounts if a["cancelled"])
    return replace(s, phase=Phase.SEGMENT, churn_rate=cancelled / len(s.accounts))

def segment(s: State) -> State:
    plans = sorted({a["plan"] for a in s.accounts})
    segs = tuple(
        (p,
         sum(1 for a in s.accounts if a["plan"] == p and a["cancelled"]) /
         sum(1 for a in s.accounts if a["plan"] == p))
        for p in plans
    )
    return replace(s, phase=Phase.REPORT, segments=segs)

def report(s: State) -> State:
    lines = [f"MERIDIAN CHURN REPORT  |  overall: {s.churn_rate:.0%}"]
    lines += [f"  {plan:<12} {rate:>4.0%}" for plan, rate in s.segments]
    return replace(s, phase=Phase.DONE, report="\n".join(lines))

# ---------------------------------------------------------------
# THE FLOW -- how steps are arranged over time. Also hand-written.
# ---------------------------------------------------------------

FLOW = {
    Phase.LOAD: load,
    Phase.COMPUTE: compute,
    Phase.SEGMENT: segment,
    Phase.REPORT: report,
}

# ---------------------------------------------------------------
# THE GUARANTEES -- what must remain true, no matter what.
# ---------------------------------------------------------------

MAX_STEPS = 10   # the watchdog. Our rendezvous-radar insurance.

def run(state: State = State(), flow=FLOW):
    trail = []
    while True:
        if state.phase is Phase.DONE:                       # success condition
            trail.append(f"step {state.step}: TERMINATED -- success")
            break
        if state.step >= MAX_STEPS:                         # watchdog
            trail.append(f"step {state.step}: TERMINATED -- watchdog "
                         f"(step budget exhausted in phase '{state.phase.value}')")
            break
        body = flow[state.phase]                            # <- the flow, frozen
        nxt = body(state)                                   # <- the body, frozen
        assert isinstance(nxt.phase, Phase), "unknown phase"  # <- a guarantee
        trail.append(f"step {state.step}: {state.phase.value} -> {nxt.phase.value}")
        state = replace(nxt, step=state.step + 1)
    return state, trail

# ---------------------------------------------------------------
# Run 1: the loop, behaving.
# ---------------------------------------------------------------

final, trail = run()
print("--- RUN 1: nominal ---")
for line in trail:
    print(line)
print()
print(final.report)

# ---------------------------------------------------------------
# Run 2: re-creating the rendezvous radar. One step misbehaves --
# it does its work but forgets to advance the phase. Left alone,
# the loop would run forever. It is not left alone.
# ---------------------------------------------------------------

def stuck_compute(s: State) -> State:
    cancelled = sum(1 for a in s.accounts if a["cancelled"])
    return replace(s, churn_rate=cancelled / len(s.accounts))   # phase unchanged. Oops.

SABOTAGED = {**FLOW, Phase.COMPUTE: stuck_compute}

print()
print("--- RUN 2: one component misbehaves ---")
final2, trail2 = run(flow=SABOTAGED)
for line in trail2:
    print(line)
print(f"report produced: {final2.report!r}")
