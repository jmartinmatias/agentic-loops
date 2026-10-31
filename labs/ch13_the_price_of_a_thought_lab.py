"""The meter: what a thought actually costs Meridian.

Book I, Chapter 13 lab. Four meters on the same task. Nothing here
is a benchmark of any real vendor; the prices are illustrative units
chosen to make the structure legible. The structure is the lesson.
"""

# ---------------------------------------------------------------
# A PRICE LIST, in cents per thousand tokens. Illustrative units.
# Two models: a cheap small one, a dear large one.
# ---------------------------------------------------------------

PRICE = {
    "small": {"in": 0.02, "out": 0.06},
    "large": {"in": 0.30, "out": 0.90},
}
TOOL_CALL = 0.05        # cents per tool round-trip
CLEANUP = 20.0          # cents to undo one wrong irreversible action

def call_cost(model, in_tok, out_tok):
    p = PRICE[model]
    return in_tok / 1000 * p["in"] + out_tok / 1000 * p["out"]

# ===============================================================
# METER 1 -- LOOP DEPTH. The context grows every step, because the
# trail rides in the render. So step N is not priced like step 1.
# ===============================================================

print("METER 1 -- the price of depth (why step 30 costs more than step 1)")

BASE_CONTEXT = 800      # charter + tools + task, fixed
PER_STEP_GROWTH = 220   # each step adds a receipt to the render
OUT_PER_STEP = 120

def run_cost(model, steps, pinned=False):
    total = 0.0
    for n in range(steps):
        if pinned:
            ctx = BASE_CONTEXT + min(n, 4) * PER_STEP_GROWTH   # tiered render
        else:
            ctx = BASE_CONTEXT + n * PER_STEP_GROWTH           # naive: all history
        total += call_cost(model, ctx, OUT_PER_STEP) + TOOL_CALL
    return total

for steps in (10, 30, 100):
    naive = run_cost("small", steps)
    tiered = run_cost("small", steps, pinned=True)
    print(f"  {steps:>3} steps: naive ${naive/100:.4f}  "
          f"tiered ${tiered/100:.4f}  "
          f"naive/tiered = {naive/tiered:.2f}x")
print("  the naive curve is quadratic in depth; the tiered curve is linear")

# ===============================================================
# METER 2 -- BEST OF N. Draw N samples, keep the best. Quality
# rises with diminishing returns; cost rises linearly. There is an
# optimum, and it is usually small.
# ===============================================================

print()
print("METER 2 -- the value of one more try (best-of-N)")

# P(one sample is good) = 0.55. P(at least one of N good) = 1-(1-p)^N.
# Value of a good outcome = 30 cents. Each sample is one large call.
P_GOOD = 0.55
VALUE = 30.0

def sample_cost():
    return call_cost("large", 6000, 900)

best_n = None
best_net = -1e9
prev_net = 0.0
for N in range(1, 7):
    p_any = 1 - (1 - P_GOOD) ** N
    gross = p_any * VALUE
    cost = N * sample_cost()
    net = gross - cost
    marginal = "" if N == 1 else f"  d(net)={net - prev_net:+.2f}"
    print(f"  N={N}: P(success)={p_any:.3f}  gross {gross:.2f}  "
          f"cost {cost:.2f}  net {net:.2f}{marginal}")
    if net > best_net:
        best_net, best_n = net, N
    prev_net = net
print(f"  optimum: N={best_n} (more samples buy less than they cost)")

# ===============================================================
# METER 3 -- THE RIGHT DENOMINATOR. Cost per run flatters the cheap
# model. Cost per VERIFIED outcome tells the truth, because wrong
# answers are not free: they cost cleanup.
# ===============================================================

print()
print("METER 3 -- cost per verified outcome (the honest denominator)")

# small model: cheap per run, but right only 60% of the time.
# large model: dear per run, right 92%.
# routed: small drafts, large verifies/retries the hard 40%.
SCENARIOS = {
    "small only":  {"run": call_cost("small", 2000, 300) + 3 * TOOL_CALL,
                    "acc": 0.60},
    "large only":  {"run": call_cost("large", 2000, 300) + 3 * TOOL_CALL,
                    "acc": 0.92},
}
# routed: pay small always; on the 40% small gets wrong, pay large too.
small_run = call_cost("small", 2000, 300) + 3 * TOOL_CALL
large_run = call_cost("large", 2000, 300) + 3 * TOOL_CALL
routed_run = small_run + 0.40 * large_run
routed_acc = 0.60 + 0.40 * 0.92          # small's hits + large's rescue

SCENARIOS["routed"] = {"run": routed_run, "acc": routed_acc}

print(f"  {'policy':<12}{'$/run':>10}{'accuracy':>10}"
      f"{'$/verified':>13}{'w/ cleanup':>12}")
for name, s in SCENARIOS.items():
    per_run = s["run"]
    per_verified = per_run / s["acc"]
    # true cost: each run, plus cleanup on every wrong answer
    true_cost = per_run + (1 - s["acc"]) * CLEANUP
    per_true = true_cost / s["acc"]
    print(f"  {name:<12}{per_run/100:>9.4f} {s['acc']*100:>8.0f}% "
          f"{per_verified/100:>12.4f}{per_true/100:>11.4f}")
print("  ranked by $/run, 'small only' wins; ranked by cost per verified")
print("  outcome with cleanup priced in, it loses. the denominator decides.")

# ===============================================================
# METER 4 -- LATENCY, the currency no invoice itemizes. Wall-clock
# is money three ways: a held resource, an abandoned user, an idle
# downstream. The cheap model is fast PER CALL and slow PER OUTCOME,
# because it needs more calls to get there.
# ===============================================================

print()
print("METER 4 -- the uninvoiced currency (latency to a correct answer)")

# seconds per call: the small model answers faster, the large slower.
LATENCY_S = {"small": 1.2, "large": 4.5}
TOOL_LATENCY_S = 0.8              # per tool round-trip
HELD_RESOURCE = 0.10             # cents per second a run holds a slot
# a run that is wrong is retried once end-to-end before a human is paged.
RETRY_ON_WRONG = True

def wall_clock(model, calls, tools):
    return calls * LATENCY_S[model] + tools * TOOL_LATENCY_S

# each policy: model calls per run, tool round-trips per run.
PLANS = {
    "small only": ("small", 1, 3, 0.60),
    "large only": ("large", 1, 3, 0.92),
    "routed":     ("routed", None, 3, routed_acc),
}

print(f"  {'policy':<12}{'sec/run':>9}{'sec/verified':>14}"
      f"{'held $/verified':>17}")
for name, (model, calls, tools, acc) in PLANS.items():
    if model == "routed":
        # small always (1 call), large on the wrong 40% (1 more call)
        sec = wall_clock("small", 1, tools) + 0.40 * wall_clock("large", 1, 0)
    else:
        sec = wall_clock(model, calls, tools)
    # to reach a CORRECT answer: wrong runs are re-run once end to end
    exp_runs_to_correct = 1 / acc
    sec_verified = sec * exp_runs_to_correct
    held = sec_verified * HELD_RESOURCE / 100
    print(f"  {name:<12}{sec:>8.1f}s{sec_verified:>12.1f}s"
          f"{held:>15.4f}$")
print("  'small only' is fastest per run, but routed is first to a correct answer:")
print("  it wins the call and loses the outcome. latency has a denominator too.")
