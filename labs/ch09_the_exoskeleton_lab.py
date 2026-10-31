"""ch09_the_exoskeleton_lab.py -- the signature build of Book I.

The production-grade minimal harness: every discipline from Chapters
1 through 8, assembled into one deterministic suit. The chassis
that Books II and III will extend.
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
# STATE, CONFIG, STORE -- the store is the only thing that
# survives a crash. That is the definition of a crash.
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
    churn: str | None = None
    url: str | None = None
    facts: tuple = ()

@dataclass(frozen=True)
class Config:
    max_steps: int = 12
    max_repairs: int = 4
    max_transport_retries: int = 2
    charter_hash: str = "171afab1"      # Chapter 6's v2, still in force
    render_version: str = "r2"          # Chapter 8's tiered render

class Store:
    def __init__(self):
        self._d = {}
    def save(self, run_id, state, repairs):
        self._d[run_id] = {"state": state, "repairs": repairs}
    def load(self, run_id):
        return self._d.get(run_id)

# ---------------------------------------------------------------
# PORTS -- the harness core never touches a vendor. Models plug in.
# Every ScriptedModel in this book was a port adapter all along.
# ---------------------------------------------------------------

class ScriptedModel:
    def __init__(self, replies):
        self.replies = list(replies)
    def __call__(self, prompt: str) -> str:
        return self.replies.pop(0)

class FlakyTransport:
    """Wraps a model port; fails at the transport layer n times."""
    def __init__(self, inner, failures=1):
        self.inner, self.failures = inner, failures
    def __call__(self, prompt: str) -> str:
        if self.failures > 0:
            self.failures -= 1
            raise ConnectionError("model endpoint timeout")
        return self.inner(prompt)

# ---------------------------------------------------------------
# THE WORLD and THE CATALOG -- Chapter 7's instruction set.
# ---------------------------------------------------------------

def make_world():
    return {"billing_fetches": 0, "crm_fetches": 0,
            "publish_live": 0, "outbox": []}

def fetch_rows(s, w, args):
    src = args["source"]
    w[f"{src}_fetches"] += 1
    n = 5 if src == "billing" else 3
    return replace(s, **{src: True}), Obs("read", f"{src}_api", f"{src}: {n} rows")

def compute_churn(s, w, args):
    return replace(s, churn="$997.00"), Obs("derived", "risk_model",
                                            "MRR at risk $997.00 across 3 accounts")

def publish_dashboard(s, w, args):
    w["publish_live"] += 1
    url = "https://meridian.example/dash/churn"
    return replace(s, url=url), Obs("write", "dashboard_svc",
                                    f"live at {url} (publish P-1)")

def send_exec_summary(s, w, args):
    w["outbox"].append("exec summary")
    return s, Obs("write", "mailer", "summary sent")

CATALOG = {"fetch_rows": fetch_rows, "compute_churn": compute_churn,
           "publish_dashboard": publish_dashboard,
           "send_exec_summary": send_exec_summary}

PRECONDS = {
    "compute_churn": (lambda s: s.billing and s.crm, "both sources required"),
    "publish_dashboard": (lambda s: s.churn is not None, "churn not computed"),
}

IRREVERSIBLE = {"send_exec_summary"}
APPROVED = set()                        # still load-bearing

def render(s: State, cfg: Config) -> str:
    pinned = f"billing:{s.billing} crm:{s.crm} churn:{s.churn} url:{s.url}"
    recent = "; ".join(o.note for o in s.facts[-3:]) or "none"
    return (f"[charter {cfg.charter_hash} | render {cfg.render_version}]\n"
            f"pinned: {pinned}\nrecent: {recent}\n"
            "actions: fetch_rows(source), compute_churn, publish_dashboard, "
            "send_exec_summary [needs approval], finish\n"
            'JSON only: {"action": ..., "args": {...}, "reason": ...}')

# ---------------------------------------------------------------
# THE HARNESS -- the suit. One step pipeline, checkpointed,
# killable at any moment, resumable from the store.
# ---------------------------------------------------------------

class Harness:
    def __init__(self, cfg, model, world, store, run_id):
        self.cfg, self.model = cfg, model
        self.world, self.store, self.run_id = world, store, run_id

    def run(self, resume=False, kill_after=None):
        trail, applied = [], 0
        if resume:
            snap = self.store.load(self.run_id)
            state, repairs = snap["state"], snap["repairs"]
            trail.append(f"RESUMED -- from checkpoint chk-{state.step} "
                         f"(repairs {repairs}); fresh model, continuity "
                         f"lives entirely in the state")
        else:
            state, repairs = State(), 0

        while True:
            if state.step >= self.cfg.max_steps:             # 1. budgets
                trail.append(f"step {state.step}: TERMINATED -- watchdog")
                break
            if repairs >= self.cfg.max_repairs:
                trail.append(f"step {state.step}: TERMINATED -- repair budget")
                break

            prompt = render(state, self.cfg)                 # 2. render
            raw = None
            for attempt in range(self.cfg.max_transport_retries + 1):
                try:
                    raw = self.model(prompt)                 # 3. invoke
                    break
                except ConnectionError as e:
                    if attempt >= self.cfg.max_transport_retries:
                        break                                # retries exhausted
                    trail.append(f"TRANSPORT RETRY {attempt + 1}/"
                                 f"{self.cfg.max_transport_retries} -- {e}; "
                                 f"same decision re-requested (no repair spent)")
            if raw is None:
                trail.append(f"step {state.step}: TERMINATED -- transport down")
                break

            try:                                             # 4. parse
                d = json.loads(raw)
                action, args = d["action"], d.get("args", {}) or {}
            except (json.JSONDecodeError, KeyError, TypeError):
                repairs += 1
                trail.append(f"step {state.step}: GUARDRAIL -- malformed reply "
                             f"(repair {repairs}/{self.cfg.max_repairs})")
                continue

            if action == "finish":                           # 5. policy
                if state.url is None:
                    repairs += 1
                    trail.append(f"step {state.step}: GUARDRAIL -- premature "
                                 f"finish: no dashboard URL "
                                 f"(repair {repairs}/{self.cfg.max_repairs})")
                    continue
                trail.append(f"step {state.step}: finish -- TERMINATED -- success")
                break
            if action not in CATALOG:
                repairs += 1
                trail.append(f"step {state.step}: GUARDRAIL -- unknown action "
                             f"{action!r} (repair {repairs}/{self.cfg.max_repairs})")
                continue
            pre = PRECONDS.get(action)
            if pre and not pre[0](state):
                repairs += 1
                trail.append(f"step {state.step}: GUARDRAIL -- precondition "
                             f"failed for {action}: {pre[1]} "
                             f"(repair {repairs}/{self.cfg.max_repairs})")
                continue
            argrepr = f" {args}" if args else ""
            if action in IRREVERSIBLE and action not in APPROVED:
                state = replace(state, step=state.step + 1,
                                facts=state.facts +
                                (Obs("gate", "shell", f"{action} HELD"),))
                trail.append(f"step {state.step - 1}: {action}{argrepr} "
                             f"({d.get('reason', '')})")
                trail.append(f"GATE -- {action} is irreversible: HELD for "
                             f"human approval, obligation recorded")
                self.store.save(self.run_id, state, repairs)
                trail.append(f"CHECKPOINT -- chk-{state.step}")
                continue

            try:                                             # 6. execute
                nxt, receipt = CATALOG[action](state, self.world, args)
            except Exception as e:
                state = replace(state, step=state.step + 1,
                                facts=state.facts + (Obs("error", action, str(e)),))
                trail.append(f"step {state.step - 1}: {action}{argrepr} "
                             f"({d.get('reason', '')})")
                trail.append(f"OBSERVED ERROR -- {action}: {e!r}; recorded")
                self.store.save(self.run_id, state, repairs)
                trail.append(f"CHECKPOINT -- chk-{state.step}")
                continue

            if any(o.note == receipt.note for o in state.facts):   # 7. progress
                repairs += 1
                trail.append(f"step {state.step}: GUARDRAIL -- repetition "
                             f"(repair {repairs}/{self.cfg.max_repairs})")
                continue

            state = replace(nxt, step=state.step + 1,        # 8. persist
                            facts=nxt.facts + (receipt,))
            trail.append(f"step {state.step - 1}: {action}{argrepr} "
                         f"({d.get('reason', '')})")
            trail.append(f"RECEIPT -- {receipt.source}: {receipt.note}")
            self.store.save(self.run_id, state, repairs)     # 9. checkpoint
            trail.append(f"CHECKPOINT -- chk-{state.step}")

            applied += 1
            if kill_after is not None and applied >= kill_after:
                trail.append("-- process killed (simulated power loss); every "
                             "in-memory object is gone; only the store survives --")
                break
        return state, trail

# ---------------------------------------------------------------
# RUN 1: the dive, interrupted. A crash after step 2, and a resume
# that completes the task with no duplicated side effects.
# ---------------------------------------------------------------

script = [
    '{"action": "fetch_rows", "args": {"source": "billing"}, "reason": "first source"}',
    '{"action": "fetch_rows", "args": {"source": "crm"}, "reason": "second source"}',
    '{"action": "compute_churn", "reason": "turn rows into risk"}',
    '{"action": "publish_dashboard", "reason": "publish and collect the URL"}',
    '{"action": "finish", "reason": "dashboard live, receipt on the trail"}',
]

print("--- RUN 1: the dive, interrupted ---")
world = make_world()
store = Store()
h1 = Harness(Config(), ScriptedModel(script[:2]), world, store, "run-1")
_, trail1 = h1.run(kill_after=2)
for line in trail1:
    emit(line)
print()
h2 = Harness(Config(), ScriptedModel(script[2:]), world, store, "run-1")
final, trail2 = h2.run(resume=True)
for line in trail2:
    emit(line)
emit(f"WORLD -- billing fetched {world['billing_fetches']}x, crm fetched "
      f"{world['crm_fetches']}x, dashboards live {world['publish_live']}: "
      f"no effect duplicated across the crash")

# ---------------------------------------------------------------
# RUN 2: the storm. A transport failure, a content failure, and a
# gate, in one weather system. Note which ones spend repairs.
# ---------------------------------------------------------------

storm = [
    '{"action": "fetch_rows", "args": {"source": "billing"}, "reason": "first source"}',
    'Sure! Let me fetch the CRM data next.',
    '{"action": "fetch_rows", "args": {"source": "crm"}, "reason": "second source, as JSON this time"}',
    '{"action": "compute_churn", "reason": "turn rows into risk"}',
    '{"action": "send_exec_summary", "reason": "leadership should know"}',
    '{"action": "publish_dashboard", "reason": "publish while approval is pending"}',
    '{"action": "finish", "reason": "dashboard live, summary held at the gate"}',
]

print()
print("--- RUN 2: the storm ---")
world2 = make_world()
store2 = Store()
h3 = Harness(Config(), FlakyTransport(ScriptedModel(storm), failures=1),
             world2, store2, "run-2")
final2, trail3 = h3.run()
for line in trail3:
    emit(line)
emit(f"TRAIL -- every applied step checkpointed; every render stamped: "
      f"charter {Config().charter_hash} | render {Config().render_version}")
