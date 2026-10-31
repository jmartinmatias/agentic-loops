"""Meridian, two menus: the same policy against two instruction sets.

Book I, Chapter 7 lab. The model never changes. The catalog does,
and the world's counters keep the score.
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
# STATE and WORLD
# ---------------------------------------------------------------

@dataclass(frozen=True)
class Obs:
    kind: str
    source: str
    note: str

@dataclass(frozen=True)
class State:
    step: int = 0
    billing: bool = False
    crm: bool = False
    merged: bool = False
    churn: str | None = None
    url: str | None = None
    facts: tuple = ()

def make_world():
    return {"crm_flaky": 1, "billing_rows": 5, "crm_rows": 3,
            "billing_fetches": 0, "crm_fetches": 0,
            "publish_queued": 0, "publish_live": 0}

class ToolError(Exception):
    """A structured fault: code, retryable flag, detail. Catalog B only."""
    def __init__(self, code, retryable, detail):
        super().__init__(detail)
        self.code, self.retryable, self.detail = code, retryable, detail

# ---------------------------------------------------------------
# CATALOG A -- the drawer of odd knives. Two overlapping fetchers
# and one monolith whose description promises more than it returns.
# ---------------------------------------------------------------

def a_get_data(s, w, args):
    src = args["source"]
    w[f"{src}_fetches"] += 1
    return replace(s, billing=True), Obs("read", "warehouse",
                                         f"billing: {w['billing_rows']} rows")

def a_fetch_billing(s, w, args):
    w["billing_fetches"] += 1
    return replace(s, billing=True), Obs("read", "billing_api",
                                         f"billing: {w['billing_rows']} rows")

def a_refresh_dashboard(s, w, args):
    w["billing_fetches"] += 1
    w["crm_fetches"] += 1
    if w["crm_flaky"] > 0:
        w["crm_flaky"] -= 1
        raise RuntimeError("refresh failed")          # opaque: which stage? retry?
    w["publish_queued"] += 1                          # description promised a URL
    return s, Obs("write", "dashboard_svc", "refresh complete: status queued")

CATALOG_A = {"get_data": a_get_data, "fetch_billing": a_fetch_billing,
             "refresh_dashboard": a_refresh_dashboard}

# ---------------------------------------------------------------
# CATALOG B -- the instruction set. One orthogonal fetch, three
# composable stages, structured faults, honest receipts.
# ---------------------------------------------------------------

def b_fetch_rows(s, w, args):
    src = args["source"]
    w[f"{src}_fetches"] += 1
    if src == "crm" and w["crm_flaky"] > 0:
        w["crm_flaky"] -= 1
        raise ToolError("TIMEOUT", True, "crm did not answer")
    n = w[f"{src}_rows"]
    return replace(s, **{src: True}), Obs("read", f"{src}_api", f"{src}: {n} rows")

def b_merge_rows(s, w, args):
    return replace(s, merged=True), Obs("derived", "merger",
                                        "merged 8 rows (billing 5 + crm 3)")

def b_compute_churn(s, w, args):
    return replace(s, churn="$997.00"), Obs("derived", "risk_model",
                                            "MRR at risk $997.00 across 3 accounts")

def b_publish_dashboard(s, w, args):
    w["publish_live"] += 1
    url = "https://meridian.example/dash/churn"
    return replace(s, url=url), Obs("write", "dashboard_svc",
                                    f"live at {url} (publish P-1)")

CATALOG_B = {"fetch_rows": b_fetch_rows, "merge_rows": b_merge_rows,
             "compute_churn": b_compute_churn,
             "publish_dashboard": b_publish_dashboard}

PRECONDS_B = {
    "merge_rows": (lambda s: s.billing and s.crm, "both sources must be fetched"),
    "compute_churn": (lambda s: s.merged, "rows not merged yet"),
    "publish_dashboard": (lambda s: s.churn is not None, "churn not computed"),
}

# ---------------------------------------------------------------
# THE SHELL -- the Chapter 4 skeleton, catalog-agnostic. Finish
# requires a live dashboard URL, whichever menu is in force.
# ---------------------------------------------------------------

MAX_STEPS = 12
MAX_REPAIRS = 4

class ScriptedModel:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0
    def __call__(self, prompt: str) -> str:
        self.calls += 1
        return self.replies.pop(0)

def run(model, catalog, preconds, world, state: State = State()):
    trail, repairs = [], 0
    while True:
        if state.step >= MAX_STEPS:
            trail.append(f"step {state.step}: TERMINATED -- watchdog")
            break
        if repairs >= MAX_REPAIRS:
            trail.append(f"step {state.step}: TERMINATED -- repair budget exhausted")
            break
        raw = model(f"state: {state.step} facts: {len(state.facts)}")
        try:
            d = json.loads(raw)
            action, args = d["action"], d.get("args", {}) or {}
        except (json.JSONDecodeError, KeyError, TypeError):
            repairs += 1
            trail.append(f"step {state.step}: GUARDRAIL -- malformed reply "
                         f"(repair {repairs}/{MAX_REPAIRS})")
            continue
        if action == "finish":
            if state.url is None:
                repairs += 1
                trail.append(f"step {state.step}: GUARDRAIL -- premature finish: "
                             f"no dashboard URL on the record "
                             f"(repair {repairs}/{MAX_REPAIRS})")
                continue
            trail.append(f"step {state.step}: finish -- TERMINATED -- success")
            break
        if action not in catalog:
            repairs += 1
            trail.append(f"step {state.step}: GUARDRAIL -- unknown action "
                         f"{action!r} (repair {repairs}/{MAX_REPAIRS})")
            continue
        pre = preconds.get(action)
        if pre and not pre[0](state):
            repairs += 1
            trail.append(f"step {state.step}: GUARDRAIL -- precondition failed "
                         f"for {action}: {pre[1]} (repair {repairs}/{MAX_REPAIRS})")
            continue
        argrepr = f" {args}" if args else ""
        try:
            nxt, receipt = catalog[action](state, world, args)
        except ToolError as e:
            state = replace(state, step=state.step + 1,
                            facts=state.facts + (Obs("error", action, e.detail),))
            trail.append(f"step {state.step - 1}: {action}{argrepr} "
                         f"({d.get('reason', '')})")
            trail.append(f"OBSERVED ERROR -- {action}: {e.code} "
                         f"(retryable={e.retryable}) {e.detail}; recorded")
            continue
        except Exception as e:
            state = replace(state, step=state.step + 1,
                            facts=state.facts + (Obs("error", action, str(e)),))
            trail.append(f"step {state.step - 1}: {action}{argrepr} "
                         f"({d.get('reason', '')})")
            trail.append(f"OBSERVED ERROR -- {action}: {e!r}; nothing says "
                         f"what failed or whether to retry")
            continue
        if any(o.note == receipt.note for o in state.facts):
            repairs += 1
            trail.append(f"step {state.step}: GUARDRAIL -- repetition: receipt "
                         f"already on the trail (repair {repairs}/{MAX_REPAIRS})")
            continue
        state = replace(nxt, step=state.step + 1, facts=nxt.facts + (receipt,))
        trail.append(f"step {state.step - 1}: {action}{argrepr} "
                     f"({d.get('reason', '')})")
        trail.append(f"RECEIPT -- {receipt.source}: {receipt.note}")
    return state, trail, repairs

# ---------------------------------------------------------------
# One competent policy, two menus.
# ---------------------------------------------------------------

script_a = [
    '{"action": "get_data", "args": {"source": "billing"}, "reason": "start with the warehouse"}',
    '{"action": "fetch_billing", "reason": "the docs also list a billing fetcher; make sure"}',
    '{"action": "refresh_dashboard", "reason": "one tool claims to do the whole job"}',
    '{"action": "refresh_dashboard", "reason": "no diagnosis available; run the whole thing again"}',
    '{"action": "finish", "reason": "the description promised a live dashboard"}',
    '{"action": "refresh_dashboard", "reason": "maybe a second run yields the URL"}',
    '{"action": "finish", "reason": "out of moves this menu can express"}',
]

script_b = [
    '{"action": "fetch_rows", "args": {"source": "billing"}, "reason": "fetch the first source"}',
    '{"action": "fetch_rows", "args": {"source": "crm"}, "reason": "fetch the second source"}',
    '{"action": "fetch_rows", "args": {"source": "crm"}, "reason": "the contract says retryable; retry only the failed fetch"}',
    '{"action": "merge_rows", "reason": "both sources on the record"}',
    '{"action": "compute_churn", "reason": "turn merged rows into risk"}',
    '{"action": "publish_dashboard", "reason": "publish and collect the URL"}',
    '{"action": "finish", "reason": "dashboard live, receipt on the trail"}',
]

print("--- CATALOG A: the drawer of odd knives ---")
world_a = make_world()
model_a = ScriptedModel(script_a)
final_a, trail_a, repairs_a = run(model_a, CATALOG_A, {}, world_a)
for line in trail_a:
    emit(line)
emit(f"WORLD -- billing fetched {world_a['billing_fetches']}x, "
      f"crm fetched {world_a['crm_fetches']}x, publishes queued "
      f"{world_a['publish_queued']}, dashboards live {world_a['publish_live']}")

print()
print("--- CATALOG B: the instruction set ---")
world_b = make_world()
model_b = ScriptedModel(script_b)
final_b, trail_b, repairs_b = run(model_b, CATALOG_B, PRECONDS_B, world_b)
for line in trail_b:
    emit(line)
print(f"WORLD -- billing fetched {world_b['billing_fetches']}x, "
      f"crm fetched {world_b['crm_fetches']}x, dashboards live "
      f"{world_b['publish_live']}")

print()
print("SAME POLICY, TWO MENUS")
print(f"  catalog A: {model_a.calls} decisions, {repairs_a} repairs, "
      f"{world_a['publish_live']} dashboards")
print(f"  catalog B: {model_b.calls} decisions, {repairs_b} repairs, "
      f"{world_b['publish_live']} dashboard")
print("  the model never changed. the menu did.")
