"""The pathology bench: four failure specimens under glass.

Book I, Chapter 11 lab. Each specimen is small, deterministic, and
chosen because the ordinary armor misses it. Specimen 1 pays a debt
owed since Chapter 4.
"""


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


# ===============================================================
# SPECIMEN 1 -- oscillation: motion the progress rule cannot see.
# ===============================================================

print("SPECIMEN 1 -- oscillation (revisited-state detection)")

credits, next_id = set(), [1]

def apply_credit(acct):
    cid = f"CR-{next_id[0]}"
    next_id[0] += 1
    credits.add(acct)
    return f"applied {cid} to {acct}"

def revoke_credit(acct):
    credits.discard(acct)
    return f"revoked credit from {acct}"

script = [("apply", "A-04"), ("revoke", "A-04"), ("apply", "A-04")]
receipts, seen, revisits = [], {tuple(): -1}, 0

for step, (action, acct) in enumerate(script):
    note = apply_credit(acct) if action == "apply" else revoke_credit(acct)
    receipts.append(note)
    print(f"step {step}: {action} {acct} -> RECEIPT: {note}")
    fp = tuple(sorted(credits))
    if fp in seen:
        revisits += 1
        period = step - seen[fp]
        if revisits == 1:
            where = ("the initial state" if seen[fp] == -1
                     else f"the state of step {seen[fp]}")
            print(f"  WARN -- world returned to {where}; "
                  f"cycle candidate, period {period}")
        else:
            print(f"  GUARDRAIL -- oscillation confirmed (period {period}); "
                  f"loop halted for diagnosis")
            break
    seen[fp] = step

unique = len(set(receipts)) == len(receipts)
emit(f"  note: all {len(receipts)} receipts unique = {unique}; "
      f"the Chapter 4 progress rule is blind to this specimen")

# ===============================================================
# SPECIMEN 2 -- dead end: the menu has no exit, and saying so
# beats discovering it one repair at a time.
# ===============================================================

print()
print("SPECIMEN 2 -- dead end (diagnosis at death)")

state = {"billing": False, "churn": None, "url": None}
broken_counts = {"fetch_rows": 0}
GOAL = lambda s: s["url"] is not None

def try_fetch():
    broken_counts["fetch_rows"] += 1
    raise TimeoutError("billing mirror is down")

CLOSED_REASONS = {}

def viable_actions():
    CLOSED_REASONS.clear()
    v = []
    if broken_counts["fetch_rows"] >= 2:
        CLOSED_REASONS["fetch_rows"] = "broken x2"
    else:
        v.append("fetch_rows")
    if not state["billing"]:
        CLOSED_REASONS["compute_churn"] = "precondition: no billing"
        CLOSED_REASONS["publish_dashboard"] = "precondition: no churn"
    CLOSED_REASONS["send_exec_summary"] = "gated, no approval"
    return v

for step in range(12):
    v = viable_actions()
    if not v and not GOAL(state):
        closed = ", ".join(f"{a}({r})" for a, r in CLOSED_REASONS.items())
        emit(f"step {step}: TERMINATED -- dead end: no reachable action can "
              f"advance the goal; menu exhausted: {closed}")
        print(f"  note: a watchdog alone would have spent "
              f"{12 - step} more steps discovering this")
        break
    try:
        print(f"step {step}: fetch_rows -> ", end="")
        try_fetch()
    except TimeoutError as e:
        print(f"OBSERVED ERROR: {e}")

# ===============================================================
# SPECIMEN 3 -- Goodhart: the proxy satisfied, the purpose betrayed.
# ===============================================================

print()
print("SPECIMEN 3 -- reward hacking (a proxy and its independent check)")

REQUIRED = ["June 3-12", "$997.00"]
padded = ("This report is a thorough, detailed, comprehensive, complete, "
          "careful, extensive, rigorous, methodical, systematic, and very "
          "long discussion of churn matters, covering many important topics "
          "at appropriate length for executive review purposes overall, "
          "as requested, with all due diligence, care, attention, and "
          "professional consideration applied throughout, in full.")

proxy_pass = len(padded.split()) >= 40
held_out = [n for n in REQUIRED if n not in padded]
print(f"proxy check (length >= 40 words): "
      f"{'PASS' if proxy_pass else 'FAIL'} ({len(padded.split())} words)")
print(f"held-out check (required facts): FAIL -- missing "
      f"{', '.join(held_out)}")
emit("  verdict: proxy satisfied, purpose betrayed; every proxy needs an "
      "independent check it cannot see")

# ===============================================================
# SPECIMEN 4 -- loops meeting loops: two correct rules, one spiral,
# and a breaker neither loop contains.
# ===============================================================

print()
print("SPECIMEN 4 -- coupled loops (the spiral and the breaker)")

price = {"A": 100.0, "B": 100.0}
OPEN = 100.0
BREAKER = 0.30      # halt if price moves 30% from open

tick = 0
for mover, other in [("A", "B"), ("B", "A")] * 6:
    tick += 1
    price[mover] = round(price[other] * 0.85, 2)
    print(f"tick {tick}: loop {mover} reprices to {price[mover]:.2f} "
          f"(rule: match competitor minus 15%)")
    drop = 1 - price[mover] / OPEN
    if drop > BREAKER:
        emit(f"  CIRCUIT BREAKER -- price moved {drop:.0%} from open in "
              f"{tick} ticks; both loops halted by an authority neither "
              f"loop contains")
        break

print()
print("four specimens, one lesson: the pathogen is rarely in the step")
