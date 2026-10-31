"""Meridian learns the word for enough: a stopping stack in action.

Book I, Chapter 10 lab. A convergence layer that proposes, a shell
that disposes, a watchdog that salvages, an operator who outranks
the loop, and a fleet whose deaths are worth reading.
"""

import json
from difflib import SequenceMatcher


def wrapped(text, width=76, indent=""):
    """Wrap a long line the way the book prints it, so the output is the
    same on every screen: at word boundaries, continuation indented."""
    import textwrap
    return textwrap.wrap(text, width=width, subsequent_indent=indent,
                         break_long_words=False, break_on_hyphens=False) or [""]

def emit(line):
    """Print one trail line, wrapped at the page width."""
    lead = len(line) - len(line.lstrip(" "))
    for part in wrapped(line, 76, " " * (lead + 4)):
        print(part)

REQUIRED = ["June 3-12", "$997.00"]
CONV_THRESH = 0.05      # a draft changing less than 5%...
CONV_STREAK = 2         # ...twice in a row, has stopped moving

class ScriptedModel:
    def __init__(self, replies):
        self.replies = list(replies)
    def __call__(self, prompt: str) -> str:
        return self.replies.pop(0)

def delta(a, b):
    return 1 - SequenceMatcher(None, a, b).ratio()

# ---------------------------------------------------------------
# THE RUNNER -- a drafting loop with a layered stopping stack:
#   layer 1: verified success (postcondition on finish)
#   layer 2: convergence (proposes; never disposes)
#   layer 5: budgets, with salvage
#   out of band: the operator's word, checked above everything
# ---------------------------------------------------------------

def run_drafting(script, max_steps=8, max_repairs=3, abort_at=None):
    model = ScriptedModel(script)
    trail, drafts, repairs, streak, proposed = [], [], 0, 0, False
    step = 0
    while True:
        if abort_at is not None and step >= abort_at:
            trail.append(f"step {step}: OPERATOR -- abort received; halted by "
                         f"an authority the loop cannot negotiate with")
            return "operator-abort", trail
        if step >= max_steps:                              # layer 5, with salvage
            best = max(range(len(drafts)),
                       key=lambda i: (sum(n in drafts[i] for n in REQUIRED), i))
            missing = [n for n in REQUIRED if n not in drafts[best]]
            trail.append(f"step {step}: TERMINATED -- watchdog: step budget; "
                         f"salvage: draft v{best + 1} shipped UNVERIFIED; "
                         f"missing: {', '.join(missing) if missing else 'none'}")
            return "watchdog (salvaged)", trail
        if repairs >= max_repairs:
            trail.append(f"step {step}: TERMINATED -- repair budget exhausted")
            return "repair-budget", trail

        raw = model(f"drafting; v{len(drafts)} exists; converged={proposed}")
        try:
            d = json.loads(raw)
            action = d["action"]
        except (json.JSONDecodeError, KeyError, TypeError):
            repairs += 1
            trail.append(f"step {step}: GUARDRAIL -- malformed reply "
                         f"(repair {repairs}/{max_repairs})")
            continue

        if action == "finish":                             # layer 1: verified
            missing = [n for n in REQUIRED if not drafts or n not in drafts[-1]]
            if missing:
                repairs += 1
                trail.append(f"step {step}: GUARDRAIL -- premature finish: "
                             f"draft missing {', '.join(missing)} "
                             f"(repair {repairs}/{max_repairs})")
                continue
            trail.append(f"step {step}: finish -- TERMINATED -- "
                         f"verified-success (postcondition holds; stop "
                         f"proposed by convergence, disposed by the shell)")
            return "verified-success", trail

        if action == "draft":
            text = d["args"]["text"]
            dl = delta(drafts[-1], text) if drafts else 1.0
            drafts.append(text)
            note = f"(delta {dl:.1%})" if len(drafts) > 1 else "(first draft)"
            trail.append(f"step {step}: draft v{len(drafts)} {note} "
                         f"({d.get('reason', '')})")
            streak = streak + 1 if dl < CONV_THRESH else 0
            if streak >= CONV_STREAK and not proposed:     # layer 2: proposes
                proposed = True
                trail.append(f"CONVERGENCE -- drafts stabilized (delta under "
                             f"{CONV_THRESH:.0%} twice); stopping proposed "
                             f"to the state, not imposed")
            step += 1
            continue

        repairs += 1
        trail.append(f"step {step}: GUARDRAIL -- unknown action {action!r} "
                     f"(repair {repairs}/{max_repairs})")

# ---------------------------------------------------------------
# Scripts.
# ---------------------------------------------------------------

V1 = "Churn spiked in the basic tier. An export incident occurred in June. Investigation is ongoing."
V2 = "Churn spiked in the basic tier. The export incident of June 3-12 hit basic only. At-risk MRR is $997.00 across three accounts."
V3 = "Churn spiked in the basic tier. The export incident of June 3-12 hit basic only. At-risk MRR is $997.00 across 3 accounts (A-01, A-02, A-04)."
V4 = "Churn spiked in the basic tier. The export incident of June 3-12 hit basic tier only. At-risk MRR is $997.00 across 3 accounts (A-01, A-02, A-04)."
V5 = "Churn spiked in the basic tier. The export incident of June 3-12 hit only the basic tier. At-risk MRR is $997.00 across 3 accounts (A-01, A-02, A-04)."

def dr(text, reason):
    return json.dumps({"action": "draft", "args": {"text": text},
                       "reason": reason})

converging = [
    dr(V1, "first pass from memory"),
    '{"action": "finish", "reason": "reads fine to me"}',
    dr(V2, "the guardrail says facts are missing; add them"),
    dr(V3, "name the accounts"),
    dr(V4, "tighten the incident sentence"),
    dr(V5, "final polish"),
    '{"action": "finish", "reason": "the shell says the drafts stopped moving"}',
]

A = "The June 3-12 export incident drove the churn in the basic tier this quarter."
B = "Pricing pressure drove basic churn this quarter; at-risk MRR is $997.00."
oscillating = [dr(A, "incident framing"), dr(B, "pricing framing")] * 4

stubborn = ['{"action": "finish", "reason": "done"}',
            '{"action": "finish", "reason": "really done"}',
            'I would say it is finished.',
            '{"action": "finish", "reason": "surely now"}']

print("--- RUN 1: the layered stop ---")
reason1, trail1 = run_drafting(converging)
for line in trail1:
    emit(line)

print()
print("--- RUN 2: the broom ---")
reason2, trail2 = run_drafting(oscillating)
for line in trail2:
    emit(line)

# ---------------------------------------------------------------
# THE FLEET -- eight runs, and a distribution worth reading.
# ---------------------------------------------------------------

print()
print("--- FLEET TELEMETRY: 8 runs ---")
fleet = [(converging, None)] * 4 + [(oscillating, None)] * 2 + \
        [(stubborn, None), (converging, 2)]
counts = {}
for script, abort in fleet:
    reason, _ = run_drafting(list(script), abort_at=abort)
    counts[reason] = counts.get(reason, 0) + 1
for reason in ["verified-success", "watchdog (salvaged)",
               "repair-budget", "operator-abort"]:
    n = counts.get(reason, 0)
    print(f"  {reason:<22} {n}  {'*' * (n * 2)}")
print("healthy fleets die of success; read this table weekly")
