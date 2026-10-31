"""Meridian acts: the complete Observe-Decide-Act runtime for a fixed agent.

Book I, Chapter 4 lab. The loop grows hands, and every hand leaves a receipt.
"""

import json
from dataclasses import dataclass, replace


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

# ---------------------------------------------------------------
# STATE -- what the loop knows. Receipts from the world accumulate
# in facts; derived beliefs (risk) live apart, per Chapter 3.
# ---------------------------------------------------------------

@dataclass(frozen=True)
class Obs:
    kind: str      # "read", "write", "derived", "error", "gate"
    source: str
    note: str

@dataclass(frozen=True)
class State:
    step: int = 0
    billing: tuple = ()
    risk: tuple | None = None      # (total_usd, at_risk_accounts)
    facts: tuple = ()              # every reply the world ever gave us

# ---------------------------------------------------------------
# THE WORLD -- outside the loop, mutable, occasionally moody.
# ---------------------------------------------------------------

def make_world(flaky_reads=0):
    return {
        "flaky_reads": flaky_reads,
        "billing": (
            {"account_id": "A-01", "mrr_cents": 4900,   "status": "cancelled"},
            {"account_id": "A-02", "mrr_cents": 4900,   "status": "cancelled"},
            {"account_id": "A-04", "mrr_cents": 89900,  "status": "cancelled"},
            {"account_id": "A-05", "mrr_cents": 89900,  "status": "active"},
            {"account_id": "A-08", "mrr_cents": 499000, "status": "active"},
        ),
        "credits": {},      # idempotency key -> credit id
        "outbox": [],
        "next_credit": 1,
    }

# ---------------------------------------------------------------
# ACTIONS -- where the loop touches the world. Reads observe,
# writes mutate, and every one returns a receipt: what actually
# happened, not what was intended.
# ---------------------------------------------------------------

def read_billing(s, world, args):
    if world["flaky_reads"] > 0:
        world["flaky_reads"] -= 1
        raise TimeoutError("billing mirror did not answer")
    rows = world["billing"]
    cancelled = [r["account_id"] for r in rows if r["status"] == "cancelled"]
    note = f"{len(rows)} rows; cancelled: {', '.join(cancelled)}"
    return replace(s, billing=rows), Obs("read", "billing_db", note)

def compute_risk(s, world, args):
    at_risk = [(r["account_id"], r["mrr_cents"] / 100)
               for r in s.billing if r["status"] == "cancelled"]
    total = sum(v for _, v in at_risk)
    accts = ", ".join(a for a, _ in at_risk)
    return (replace(s, risk=(total, tuple(a for a, _ in at_risk))),
            Obs("derived", "risk_model",
                f"MRR at risk ${total:,.2f} across {len(at_risk)} accounts ({accts})"))

def apply_credit(s, world, args):
    acct = args["account"]
    if acct not in s.risk[1]:
        raise ValueError(f"{acct} is not on the at-risk list")
    key = f"credit:{acct}"                       # the idempotency key
    if key in world["credits"]:
        cid = world["credits"][key]
        note = (f"credit already applied to {acct} "
                f"(idempotency key {key} -> {cid}); nothing charged twice")
    else:
        cid = f"CR-{world['next_credit']}"
        world["next_credit"] += 1
        world["credits"][key] = cid
        note = f"$50 retention credit applied to {acct} (receipt {cid})"
    return s, Obs("write", "billing_db", note)

def send_exec_summary(s, world, args):
    world["outbox"].append("exec summary")       # only reachable once approved
    return s, Obs("write", "mailer", "summary sent to leadership")

ACTIONS = {"read_billing": read_billing, "compute_risk": compute_risk,
           "apply_credit": apply_credit, "send_exec_summary": send_exec_summary}

IRREVERSIBLE = {"send_exec_summary"}   # cannot be taken back once done
APPROVED = set()                       # nobody has approved anything.
                                       # This empty set is load-bearing.

PRECONDITIONS = {                      # enforced by the shell, not requested
    "compute_risk": (lambda s: bool(s.billing), "no billing data in state"),
    "apply_credit": (lambda s: s.risk is not None, "risk not computed yet"),
}

# ---------------------------------------------------------------
# RENDER and MODEL -- as in Chapter 2. The decision surface now
# carries receipts, flags, and an action menu with arguments.
# ---------------------------------------------------------------

def render(s: State) -> str:
    recent = "; ".join(o.note for o in s.facts[-3:]) or "none yet"
    return (
        "You run Meridian's churn response, one action per step.\n"
        f"billing loaded: {bool(s.billing)} | risk computed: {s.risk is not None}\n"
        f"recent receipts: {recent}\n"
        "actions: read_billing, compute_risk, apply_credit(account), "
        "send_exec_summary [needs approval], finish\n"
        'JSON only: {"action": ..., "args": {...}, "reason": ...}'
    )

class ScriptedModel:
    def __init__(self, replies):
        self.replies = list(replies)
    def __call__(self, prompt: str) -> str:
        return self.replies.pop(0)

# ---------------------------------------------------------------
# THE SHELL -- Chapter 2's sandwich, grown up. Invalid decisions
# cost repairs; attempted actions cost steps, even when the world
# answers with an error. Errors are observations.
# ---------------------------------------------------------------

MAX_STEPS = 12
MAX_REPAIRS = 4

def run(model, world, state: State = State()):
    trail, repairs = [], 0
    while True:
        if state.step >= MAX_STEPS:
            trail.append(f"step {state.step}: TERMINATED -- watchdog")
            break
        if repairs >= MAX_REPAIRS:
            trail.append(f"step {state.step}: TERMINATED -- repair budget exhausted")
            break

        raw = model(render(state))
        try:                                                # well-formed
            d = json.loads(raw)
            action, args = d["action"], d.get("args", {}) or {}
        except (json.JSONDecodeError, KeyError, TypeError):
            repairs += 1
            trail.append(f"step {state.step}: GUARDRAIL -- malformed reply "
                         f"rejected (repair {repairs}/{MAX_REPAIRS})")
            continue

        if action == "finish":                              # postcondition
            if state.risk is None:
                repairs += 1
                trail.append(f"step {state.step}: GUARDRAIL -- premature finish "
                             f"rejected, risk never computed "
                             f"(repair {repairs}/{MAX_REPAIRS})")
                continue
            trail.append(f"step {state.step}: finish -- TERMINATED -- success")
            break

        if action not in ACTIONS:                           # real action only
            repairs += 1
            trail.append(f"step {state.step}: GUARDRAIL -- unknown action "
                         f"{action!r} rejected (repair {repairs}/{MAX_REPAIRS})")
            continue

        pre = PRECONDITIONS.get(action)                     # enforced, not asked
        if pre and not pre[0](state):
            repairs += 1
            trail.append(f"step {state.step}: GUARDRAIL -- precondition failed "
                         f"for {action}: {pre[1]} (repair {repairs}/{MAX_REPAIRS})")
            continue

        argrepr = f" {args}" if args else ""

        if action in IRREVERSIBLE and action not in APPROVED:   # the gate
            state = replace(state, step=state.step + 1,
                            facts=state.facts +
                            (Obs("gate", "shell", f"{action} HELD for human approval"),))
            trail.append(f"step {state.step - 1}: {action}{argrepr} "
                         f"({d.get('reason', '')})")
            trail.append(f"GATE -- {action} is irreversible: HELD for human "
                         f"approval, obligation recorded")
            continue

        try:                                                # act on the world
            nxt, receipt = ACTIONS[action](state, world, args)
        except Exception as e:                              # error = observation
            state = replace(state, step=state.step + 1,
                            facts=state.facts + (Obs("error", action, str(e)),))
            trail.append(f"step {state.step - 1}: {action}{argrepr} "
                         f"({d.get('reason', '')})")
            trail.append(f"OBSERVED ERROR -- {action}: {e!r}; recorded, "
                         f"loop continues")
            continue

        if any(o.note == receipt.note for o in state.facts):    # progress rule
            repairs += 1
            trail.append(f"step {state.step}: GUARDRAIL -- repetition: receipt "
                         f"already on the trail, decision rejected "
                         f"(repair {repairs}/{MAX_REPAIRS})")
            continue

        state = replace(nxt, step=state.step + 1,
                        facts=nxt.facts + (receipt,))
        trail.append(f"step {state.step - 1}: {action}{argrepr} "
                     f"({d.get('reason', '')})")
        trail.append(f"RECEIPT -- {receipt.source}: {receipt.note}")
    return state, trail

# ---------------------------------------------------------------
# Run 1: a competent day. Watch the duplicate credit and the gate.
# ---------------------------------------------------------------

competent = ScriptedModel([
    '{"action": "read_billing", "reason": "start with the ledger"}',
    '{"action": "compute_risk", "reason": "turn rows into risk"}',
    '{"action": "apply_credit", "args": {"account": "A-04"}, "reason": "largest at-risk account"}',
    '{"action": "apply_credit", "args": {"account": "A-04"}, "reason": "make sure it landed"}',
    '{"action": "send_exec_summary", "reason": "leadership should know"}',
    '{"action": "finish", "reason": "risk computed, actions taken or queued"}',
])

world1 = make_world()
print("--- RUN 1: a competent day ---")
final1, trail1 = run(competent, world1)
for line in trail1:
    emit(line)
print(f"WORLD -- credits: {world1['credits']} | outbox: {world1['outbox']}")

# ---------------------------------------------------------------
# Run 2: the world pushes back. A precondition, a timeout observed
# and answered, and a repetition caught by the progress rule.
# ---------------------------------------------------------------

stubborn = ScriptedModel([
    '{"action": "compute_risk", "reason": "jump straight to the number"}',
    '{"action": "read_billing", "reason": "fine, ledger first"}',
    '{"action": "read_billing", "reason": "the mirror timed out; try once more"}',
    '{"action": "compute_risk", "reason": "turn rows into risk"}',
    '{"action": "compute_risk", "reason": "double-check the math"}',
    '{"action": "finish", "reason": "risk computed and on the record"}',
])

world2 = make_world(flaky_reads=1)
print()
print("--- RUN 2: the world pushes back ---")
final2, trail2 = run(stubborn, world2)
for line in trail2:
    emit(line)
