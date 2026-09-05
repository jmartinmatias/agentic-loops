"""Meridian, melted: Chapter 1's loop with a model deciding the next step.

Book I, Chapter 2 lab. The shell is frozen. The filling is not.

The model below is a scripted stand-in so this file runs anywhere,
deterministically, with no API key. Swapping in a real client is a
handful of lines (see the sidebar in section 2.7); nothing else moves.
"""

import json
from dataclasses import dataclass, replace

# ---------------------------------------------------------------
# STATE and ACTIONS -- carried over from Chapter 1, minus the FLOW
# table. The arithmetic stays frozen. Only the *decision* melts.
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

@dataclass(frozen=True)
class State:
    step: int = 0
    accounts: tuple = ()
    churn_rate: float | None = None
    segments: tuple = ()
    report: str | None = None

def load(s: State) -> State:
    return replace(s, accounts=RAW)

def compute(s: State) -> State:
    cancelled = sum(1 for a in s.accounts if a["cancelled"])
    return replace(s, churn_rate=cancelled / len(s.accounts))

def segment(s: State) -> State:
    plans = sorted({a["plan"] for a in s.accounts})
    segs = tuple(
        (p,
         sum(1 for a in s.accounts if a["plan"] == p and a["cancelled"]) /
         sum(1 for a in s.accounts if a["plan"] == p))
        for p in plans
    )
    return replace(s, segments=segs)

def write_report(s: State) -> State:
    lines = [f"MERIDIAN CHURN REPORT  |  overall: {s.churn_rate:.0%}"]
    lines += [f"  {plan:<12} {rate:>4.0%}" for plan, rate in s.segments]
    return replace(s, report="\n".join(lines))

ACTIONS = {"load": load, "compute": compute,
           "segment": segment, "write_report": write_report}

# ---------------------------------------------------------------
# RENDER -- the frozen half of the shell, on the way in.
# ---------------------------------------------------------------

def render(s: State) -> str:
    facts = [
        f"accounts loaded: {bool(s.accounts)}",
        f"churn computed: {s.churn_rate is not None}",
        f"segments computed: {bool(s.segments)}",
        f"report written: {s.report is not None}",
    ]
    return (
        "You are running Meridian's churn analysis, one step at a time.\n"
        "Current state:\n  " + "\n  ".join(facts) + "\n"
        f"Available actions: {', '.join(ACTIONS)}, or finish.\n"
        'Reply with JSON only: {"action": "<name>", "reason": "<short>"}'
    )

# ---------------------------------------------------------------
# MODEL -- the fluid filling. Scripted here; see the sidebar to go
# live. A real model receives render(state) and returns text.
# ---------------------------------------------------------------

class ScriptedModel:
    def __init__(self, replies):
        self.replies = list(replies)
    def __call__(self, prompt: str) -> str:
        return self.replies.pop(0)

# ---------------------------------------------------------------
# THE SHELL -- parse, validate, apply, log. Frozen, every line.
# ---------------------------------------------------------------

MAX_STEPS = 12     # progress budget: applied actions (the watchdog, as before)
MAX_REPAIRS = 4    # patience budget: tolerated bad replies before we abort

def run(model, state: State = State()):
    trail, repairs = [], 0
    while True:
        if state.step >= MAX_STEPS:
            trail.append(f"step {state.step}: TERMINATED -- watchdog")
            break
        if repairs >= MAX_REPAIRS:
            trail.append(f"step {state.step}: TERMINATED -- repair budget exhausted")
            break

        raw = model(render(state))

        try:                                     # guardrail 1: well-formed
            decision = json.loads(raw)
            action = decision["action"]
        except (json.JSONDecodeError, KeyError, TypeError):
            repairs += 1
            trail.append(f"step {state.step}: GUARDRAIL -- malformed reply "
                         f"rejected (repair {repairs}/{MAX_REPAIRS})")
            continue

        if action == "finish":                   # guardrail 3: postcondition
            if state.report is None:
                repairs += 1
                trail.append(f"step {state.step}: GUARDRAIL -- premature finish "
                             f"rejected, no report exists "
                             f"(repair {repairs}/{MAX_REPAIRS})")
                continue
            trail.append(f"step {state.step}: finish -- TERMINATED -- success")
            break

        if action not in ACTIONS:                # guardrail 2: real action only
            repairs += 1
            trail.append(f"step {state.step}: GUARDRAIL -- unknown action "
                         f"{action!r} rejected (repair {repairs}/{MAX_REPAIRS})")
            continue

        state = replace(ACTIONS[action](state), step=state.step + 1)
        trail.append(f"step {state.step - 1}: {action} "
                     f"({decision.get('reason', '')})")
    return state, trail

# ---------------------------------------------------------------
# Run 1: a well-behaved model. Note what is absent: no FLOW table.
# Nobody told the loop the order. The order was generated.
# ---------------------------------------------------------------

well_behaved = ScriptedModel([
    '{"action": "load", "reason": "no data in state yet"}',
    '{"action": "compute", "reason": "accounts loaded, need overall churn"}',
    '{"action": "segment", "reason": "break churn down by plan"}',
    '{"action": "write_report", "reason": "all numbers ready"}',
    '{"action": "finish", "reason": "report exists"}',
])

final, trail = run(well_behaved)
print("--- RUN 1: a well-behaved model ---")
for line in trail:
    print(line)
print()
print(final.report)

# ---------------------------------------------------------------
# Run 2: the same shell, a worse day. Three species of model error,
# one each: a malformed reply, a hallucinated action, and a
# premature claim of success. Watch what the shell does with them.
# ---------------------------------------------------------------

bad_day = ScriptedModel([
    'Certainly! Let me start by loading the data.',
    '{"action": "load", "reason": "fine, JSON it is"}',
    '{"action": "email_the_ceo", "reason": "he will want to know"}',
    '{"action": "compute", "reason": "back to the plan"}',
    '{"action": "segment", "reason": "by plan tier"}',
    '{"action": "finish", "reason": "we are basically done"}',
    '{"action": "write_report", "reason": "apparently we were not done"}',
    '{"action": "finish", "reason": "now the report exists"}',
])

print()
print("--- RUN 2: the same shell, a worse day ---")
final2, trail2 = run(bad_day)
for line in trail2:
    print(line)
print()
print(final2.report)
