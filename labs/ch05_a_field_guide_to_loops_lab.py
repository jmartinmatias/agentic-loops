"""Meridian researches: an evidence-aware research loop.

Book I, Chapter 5 lab. The read-only species, where the guarantees
guard truth instead of consequences.
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
# THE CORPUS -- Meridian's scattered institutional knowledge.
# Every document carries source, date, trust, and a stance on a
# topic, so contradiction can be handled deterministically.
# ---------------------------------------------------------------

CORPUS = {
    "D1": dict(source="exit_surveys", date="2026-07-14", trust=2,
               topic="pricing", stance="supports",
               keys={"price", "pricing", "basic", "churn"},
               text="Cancelling customers cite the June price increase on basic"),
    "D2": dict(source="exit_surveys", date="2026-07-20", trust=2,
               topic="competitor", stance="supports",
               keys={"competitor", "northlane", "churn"},
               text="Several leavers mention Northlane's cheaper starter plan"),
    "D3": dict(source="support_tickets", date="2026-06-10", trust=2,
               topic="export_incident", stance="supports",
               keys={"export", "csv", "basic", "tickets"},
               text="Basic tier users report CSV export broken since June 3"),
    "D4": dict(source="status_page", date="2026-06-12", trust=1,
               topic="export_incident", stance="supports",
               keys={"export", "incident", "status"},
               text="Incident: export service degraded June 3-12, basic tier only"),
    "D5": dict(source="pricing_changelog", date="2026-06-01", trust=1,
               topic="pricing", stance="supports",
               keys={"price", "pricing", "changelog"},
               text="June 1: basic plan $39 -> $49"),
    "D6": dict(source="industry_blog", date="2026-06-18", trust=3,
               topic="competitor", stance="supports",
               keys={"northlane", "competitor", "starter"},
               text="Northlane launches $29 starter tier"),
    "D7": dict(source="sales_notes", date="2026-07-05", trust=3,
               topic="pricing", stance="contradicts",
               keys={"churn", "seasonal", "pricing"},
               text="Summer churn is seasonal; pricing not a factor per our calls"),
}

WEIGHT = {1: 3, 2: 2, 3: 1}      # trust 1 counts triple, trust 3 counts once
MIN_CITES = 2                     # a claim needs two citations
MIN_SOURCES = 2                   # ...from two distinct sources
SATURATION = 2                    # consecutive zero-novelty searches before nudging

@dataclass(frozen=True)
class Obs:
    kind: str
    source: str
    note: str

@dataclass(frozen=True)
class State:
    step: int = 0
    retrieved: tuple = ()         # document ids actually seen
    claims: tuple = ()            # (topic, text, cites, contradiction_note)
    report: str | None = None
    zero_streak: int = 0
    facts: tuple = ()

# ---------------------------------------------------------------
# ACTIONS -- reads all the way down. Search retrieves, claim files
# evidence, synthesize drafts. Nothing here can hurt the world.
# ---------------------------------------------------------------

def search(s: State, args):
    tokens = set(args["query"].lower().split())
    hits = sorted(i for i, d in CORPUS.items() if tokens & d["keys"])
    new = [h for h in hits if h not in s.retrieved]
    streak = 0 if new else s.zero_streak + 1
    note = (f"'{args['query']}': {len(hits)} hits ({len(new)} new): "
            f"{', '.join(hits)}")
    return (replace(s, retrieved=s.retrieved + tuple(new), zero_streak=streak),
            Obs("read", "corpus_search", note))

def synthesize(s: State, args):
    lines = ["MERIDIAN CHURN BRIEF -- basic tier"]
    for topic, text, cites, contra in s.claims:
        lines.extend(wrapped(f"  {topic}: {text} [cites {', '.join(cites)}]", 76, "      "))
        if contra:
            lines.extend(wrapped(f"    note: {contra}", 76, "        "))
    return (replace(s, report="\n".join(lines)),
            Obs("derived", "synthesis", f"report drafted: {len(s.claims)} findings"))

# ---------------------------------------------------------------
# RENDER and MODEL -- house pattern.
# ---------------------------------------------------------------

def render(s: State) -> str:
    docs = ", ".join(f"{i}({CORPUS[i]['source']}, trust {CORPUS[i]['trust']})"
                     for i in s.retrieved) or "none yet"
    claimed = ", ".join(c[0] for c in s.claims) or "none yet"
    notes = "; ".join(o.note for o in s.facts if o.kind == "sufficiency") or "none"
    return (
        "You are researching: why did churn spike in Meridian's basic tier?\n"
        f"retrieved: {docs}\nclaims registered: {claimed}\nshell notes: {notes}\n"
        "actions: search(query), claim(topic, text, cites), synthesize, finish\n"
        'JSON only: {"action": ..., "args": {...}, "reason": ...}'
    )

class ScriptedModel:
    def __init__(self, replies):
        self.replies = list(replies)
    def __call__(self, prompt: str) -> str:
        return self.replies.pop(0)

# ---------------------------------------------------------------
# THE SHELL -- Chapter 4's skeleton with the research organs:
# citation grounding, a sufficiency policy, contradiction weighing,
# and a novelty counter that measures evidence, not text.
# ---------------------------------------------------------------

MAX_STEPS = 14
MAX_REPAIRS = 4

def run(model, state: State = State()):
    trail, repairs = [], 0

    def guardrail(msg):
        nonlocal repairs
        repairs += 1
        trail.append(f"step {state.step}: GUARDRAIL -- {msg} "
                     f"(repair {repairs}/{MAX_REPAIRS})")

    while True:
        if state.step >= MAX_STEPS:
            trail.append(f"step {state.step}: TERMINATED -- watchdog")
            break
        if repairs >= MAX_REPAIRS:
            trail.append(f"step {state.step}: TERMINATED -- repair budget exhausted")
            break

        raw = model(render(state))
        try:
            d = json.loads(raw)
            action, args = d["action"], d.get("args", {}) or {}
        except (json.JSONDecodeError, KeyError, TypeError):
            guardrail("malformed reply rejected")
            continue

        if action == "finish":
            if state.report is None:
                guardrail("premature finish rejected, no report drafted")
                continue
            trail.append(f"step {state.step}: finish -- TERMINATED -- success")
            break

        contra_note = ""
        if action == "claim":                       # the evidence guarantees
            topic, cites = args.get("topic"), args.get("cites", [])
            if not topic or not isinstance(cites, list) or not args.get("text"):
                guardrail("malformed claim rejected: needs topic, text, cites")
                continue
            ghosts = [c for c in cites if c not in state.retrieved]
            if ghosts:
                guardrail(f"hallucinated citation: {', '.join(ghosts)} "
                          f"never retrieved")
                continue
            if (len(set(cites)) < MIN_CITES or
                    len({CORPUS[c]["source"] for c in cites}) < MIN_SOURCES):
                guardrail(f"insufficient evidence for '{topic}': need "
                          f"{MIN_CITES}+ citations from {MIN_SOURCES}+ sources")
                continue
            if topic in (c[0] for c in state.claims):
                guardrail(f"topic '{topic}' already claimed")
                continue
            contras = [i for i in state.retrieved
                       if CORPUS[i]["topic"] == topic
                       and CORPUS[i]["stance"] == "contradicts"
                       and i not in cites]
            if contras:
                sw = sum(WEIGHT[CORPUS[c]["trust"]] for c in cites)
                cw = sum(WEIGHT[CORPUS[c]["trust"]] for c in contras)
                if sw <= cw:
                    guardrail(f"unresolved contradiction on '{topic}'")
                    continue
                srcs = ", ".join(f"{CORPUS[c]['source']} (trust "
                                 f"{CORPUS[c]['trust']}, {c})" for c in contras)
                contra_note = (f"{srcs} contradicts '{topic}'; support "
                               f"outweighs {sw} to {cw}")
            nxt = replace(state, claims=state.claims +
                          ((topic, args["text"], tuple(cites), contra_note),))
            receipt = Obs("derived", "evidence_ledger",
                          f"claim '{topic}' registered with {len(cites)} "
                          f"citations ({', '.join(cites)})")
        elif action == "search":
            nxt, receipt = search(state, args)
        elif action == "synthesize":
            if not state.claims:
                guardrail("nothing to synthesize: no claims registered")
                continue
            nxt, receipt = synthesize(state, args)
        else:
            guardrail(f"unknown action {action!r} rejected")
            continue

        if any(o.note == receipt.note for o in state.facts):    # progress rule
            guardrail("repetition: receipt already on the trail")
            continue

        argrepr = f" {args}" if action == "search" else ""
        trail.append(f"step {state.step}: {action}{argrepr} "
                     f"({d.get('reason', '')})")
        if contra_note:
            trail.append(f"CONTRADICTION -- {contra_note}; recorded with the claim")
        trail.append(f"RECEIPT -- {receipt.source}: {receipt.note}")
        state = replace(nxt, step=state.step + 1,
                        facts=nxt.facts + (receipt,))

        if (state.zero_streak >= SATURATION and
                not any(o.kind == "sufficiency" for o in state.facts)):
            suff = Obs("sufficiency", "shell",
                       f"last {SATURATION} searches added no new evidence; "
                       f"diminishing returns, consider synthesize")
            state = replace(state, facts=state.facts + (suff,))
            trail.append(f"SUFFICIENCY -- {suff.note}")
    return state, trail

# ---------------------------------------------------------------
# Run 1: the disciplined researcher.
# ---------------------------------------------------------------

disciplined = ScriptedModel([
    '{"action": "search", "args": {"query": "basic churn"}, "reason": "cast the first net wide"}',
    '{"action": "search", "args": {"query": "export incident"}, "reason": "tickets mention a broken export; corroborate"}',
    '{"action": "search", "args": {"query": "pricing changelog"}, "reason": "surveys blame price; find the primary record"}',
    '{"action": "search", "args": {"query": "northlane starter"}, "reason": "leavers name a competitor; verify the launch"}',
    '{"action": "claim", "args": {"topic": "export_incident", "text": "A 10-day export outage hit basic tier in June", "cites": ["D3", "D4"]}, "reason": "tickets plus status page agree"}',
    '{"action": "claim", "args": {"topic": "pricing", "text": "Basic price rose 26% on June 1", "cites": ["D1", "D5"]}, "reason": "survey testimony matches the changelog"}',
    '{"action": "claim", "args": {"topic": "competitor", "text": "Northlane launched a $29 starter plan mid-June", "cites": ["D2", "D6"]}, "reason": "two independent mentions"}',
    '{"action": "synthesize", "reason": "three grounded findings; evidence stopped moving"}',
    '{"action": "finish", "reason": "report drafted with citations"}',
])

print("--- RUN 1: the disciplined researcher ---")
final1, trail1 = run(disciplined)
for line in trail1:
    emit(line)
print()
print(final1.report)

# ---------------------------------------------------------------
# Run 2: the eager synthesizer. Stops too early, then too late.
# ---------------------------------------------------------------

eager = ScriptedModel([
    '{"action": "search", "args": {"query": "basic churn"}, "reason": "quick look"}',
    '{"action": "claim", "args": {"topic": "pricing", "text": "Price rise drove the churn", "cites": ["D1", "D9"]}, "reason": "surveys say price, and I recall a changelog"}',
    '{"action": "claim", "args": {"topic": "pricing", "text": "Price rise drove the churn", "cites": ["D1"]}, "reason": "fine, just the survey then"}',
    '{"action": "search", "args": {"query": "pricing changelog"}, "reason": "apparently I need a second source"}',
    '{"action": "claim", "args": {"topic": "pricing", "text": "Basic price rose 26% on June 1", "cites": ["D1", "D5"]}, "reason": "survey plus changelog"}',
    '{"action": "search", "args": {"query": "churn basic tier"}, "reason": "maybe there is more"}',
    '{"action": "search", "args": {"query": "seasonal churn"}, "reason": "one more angle"}',
    '{"action": "synthesize", "reason": "the shell says the evidence stopped moving"}',
    '{"action": "finish", "reason": "thin but grounded"}',
])

print()
print("--- RUN 2: the eager synthesizer ---")
final2, trail2 = run(eager)
for line in trail2:
    emit(line)
print()
print(final2.report)
