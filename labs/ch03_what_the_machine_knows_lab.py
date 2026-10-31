"""Meridian's research agent learns to observe.

Book I, Chapter 3 lab. Three sources, one truth, and the difference
between a number and an observation.
"""

from dataclasses import dataclass
from datetime import date


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

NOW = date(2026, 8, 8)   # frozen clock, so the lab is deterministic

# ---------------------------------------------------------------
# THE WORLD -- three sources, three dialects, zero coordination.
# ---------------------------------------------------------------

# 1. The billing database. Authoritative. Amounts in USD *cents*.
BILLING = (
    {"account_id": "A-01", "mrr_cents": 4900,   "status": "cancelled", "updated": "2026-08-01"},
    {"account_id": "A-02", "mrr_cents": 4900,   "status": "cancelled", "updated": "2026-08-01"},
    {"account_id": "A-04", "mrr_cents": 89900,  "status": "cancelled", "updated": "2026-08-01"},
    {"account_id": "A-05", "mrr_cents": 89900,  "status": "active",    "updated": "2026-08-01"},
    {"account_id": "A-08", "mrr_cents": 499000, "status": "active",    "updated": "2026-08-01"},
)

# 2. A CRM export. Semicolon CSV, *EUR*, European decimal commas.
CRM_EXPORT = (
    "A-04;pro;824,77;EUR;2026-08-06",
    "A-02;basic;95,00;EUR;2026-08-05",
    "A-09;enterprise;4.128,44;EUR;2026-06-20",
)

# 3. A support-ticket API. Today it is having a day.
def fetch_support():
    raise TimeoutError("support API did not answer")

# ---------------------------------------------------------------
# RUN 1 -- the naive merge. Nine lines, no questions asked.
# ---------------------------------------------------------------

def naive_mrr_at_risk():
    churning = [r for r in BILLING if r["status"] == "cancelled"]
    total = 0.0
    for r in churning:
        total += r["mrr_cents"]                        # cents? dollars? nobody asks
    for line in CRM_EXPORT:
        acct, plan, raw, cur, sync = line.split(";")
        if any(r["account_id"] == acct for r in churning):
            total += float(raw.replace(",", ""))       # strip commas, numbers are numbers
    return total

print("--- RUN 1: the naive merge ---")
print(f"MRR AT RISK: ${naive_mrr_at_risk():,.2f}")
print("(no crash, no warning, no survivors)")

# ---------------------------------------------------------------
# RUN 2 -- through the envelope. Every fact that enters state
# carries: value, units, source, time, trust. No exceptions.
# ---------------------------------------------------------------

@dataclass(frozen=True)
class Observation:
    kind: str            # "mrr", "status", "error"
    source: str
    observed_at: date
    trust: int           # 1 = authoritative ... 3 = external
    account: str | None = None
    value: float | None = None   # ALWAYS USD per month, converted at the boundary
    note: str = ""

EUR_USD = 1.09        # declared, versioned, converted at the boundary.
                      # The line nobody wrote in 1999. (And a fact about the
                      # world frozen into an artifact. Remember this constant.)
FRESHNESS_DAYS = 30   # observations older than this do not enter state
TOLERANCE = 0.02      # sources disagreeing beyond 2% must be confronted

def normalize_billing(row) -> tuple[Observation, ...]:
    seen = date.fromisoformat(row["updated"])
    return (
        Observation("mrr", "billing_db", seen, 1,
                    row["account_id"], row["mrr_cents"] / 100),
        Observation("status", "billing_db", seen, 1,
                    row["account_id"], note=row["status"]),
    )

def normalize_crm(line) -> Observation:
    acct, plan, raw, cur, sync = line.split(";")
    amount = float(raw.replace(".", "").replace(",", "."))   # European format, on purpose
    usd = amount * EUR_USD if cur == "EUR" else amount
    return Observation("mrr", "crm_export", date.fromisoformat(sync), 2, acct, usd)

def ingest():
    state, quarantine, log = [], [], []
    for row in BILLING:
        state.extend(normalize_billing(row))
    log.append(f"ingested {len(BILLING)} billing rows from billing_db (trust 1)")
    for line in CRM_EXPORT:
        obs = normalize_crm(line)
        age = (NOW - obs.observed_at).days
        if age > FRESHNESS_DAYS:                              # freshness guarantee
            quarantine.append(obs)
            log.append(f"QUARANTINE -- crm {obs.account}: observation is "
                       f"{age} days old (freshness policy: {FRESHNESS_DAYS})")
        else:
            state.append(obs)
    log.append(f"ingested {len(CRM_EXPORT) - len(quarantine)} of {len(CRM_EXPORT)} "
               f"crm rows from crm_export (trust 2)")
    try:                                                      # an error is an observation
        fetch_support()
    except Exception as e:
        state.append(Observation("error", "support_api", NOW, 2, note=str(e)))
        log.append(f"OBSERVED ERROR -- support_api: {e!r} recorded, loop continues")
    return state, quarantine, log

def reconcile(state, log):
    """Where two sources report the same fact, disagreement must surface."""
    best = {}
    for o in (o for o in state if o.kind == "mrr"):
        rival = best.get(o.account)
        if rival is None:
            best[o.account] = o
            continue
        hi, lo = sorted((rival, o), key=lambda x: x.trust)    # hi = more trusted
        rel = abs(hi.value - lo.value) / hi.value
        if rel > TOLERANCE:                                   # reconciliation guarantee
            log.append(f"reconcile {o.account}: {hi.source} ${hi.value:,.2f} vs "
                       f"{lo.source} ${lo.value:,.2f} -> DISCREPANCY {rel:.0%} "
                       f"(kept {hi.source}, trust {hi.trust})")
        else:
            log.append(f"reconcile {o.account}: {hi.source} ${hi.value:,.2f} vs "
                       f"{lo.source} ${lo.value:,.2f} -> agreement within "
                       f"{TOLERANCE:.0%}")
        best[o.account] = hi
    return best

print()
print("--- RUN 2: through the envelope ---")
state, quarantine, log = ingest()
mrr = reconcile(state, log)
for line in log:
    emit(line)

churning = sorted(o.account for o in state if o.kind == "status" and o.note == "cancelled")
print()
print("PROVENANCE")
total = 0.0
for acct in churning:
    o = mrr[acct]
    total += o.value
    print(f"  {acct}  ${o.value:>8,.2f}   {o.source}  {o.observed_at}  trust {o.trust}")
print(f"MRR AT RISK: ${total:,.2f}  ({', '.join(churning)})")
print("every number above carries: value, units, source, time, trust")
