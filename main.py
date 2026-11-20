"""GTA VI trophy rarity forecaster (make.fun gta6-trophy-rarity-forecast-01).

Reads every case /input/<id>.in and writes /output/<id>.out with five quantiles
(5/25/50/75/95%) of every trophy's Exophase earn rate at the case's target.

Method (the full write-up, with the calibration data, is in README.md):
  * Each trophy's earn rate is modelled with three curve families that
    compete on the same weighted logit-space loss, so the data picks the
    shape that fits it: a saturating log-logistic curve rising toward the
    trophy's eventual (lifetime) ceiling; a power-law approach to the
    ceiling anchored at the last read (whose gamma = 0 member is the flat
    line, so a frozen launch-night page does not invent growth); and a
    straight line of logit(rate) on ln(1 + t), the house curve baseline's
    model - a pure power law in the odds, which is what a trophy in its
    steep early-growth phase actually follows. The ceiling and the day-7
    prior come from a category table calibrated on the lifetime earn-rate
    curves of GTA V, Red Dead Redemption 2 and Elden Ring plus the live
    GTA VI reads ~32h after launch (see README).
  * The fit runs in logit space, weighted by sqrt(players tracked) and by
    recency, with a half-step floor (0.005%) for zero rates, so a rate that
    falls only because the tracked base grows faster than earners
    (dilution) is not mistaken for a trophy nobody is earning.
  * The fitted day-7 median is shrunk in logit space toward a
    horizon-aware prior: over a 90-minute horizon a rate barely moves from
    its last read; over 4.5 days it approaches the category's day-7 value.
    The shrinkage weight grows with the amount of informative history and
    falls when the fit is poor or when the history cannot tell the
    near-best extrapolations apart (the extrapolation uncertainty u).
  * Structural constraints are enforced on the medians: the story-chapter
    chain is non-increasing, and the platinum cannot exceed 100% completion.
  * Quantiles are a logit-normal spread around the median; the spread grows
    with the fit residual, the category's prior width, the extrapolation
    uncertainty u and the horizon (scaled by 0.8, backtest-tuned).

The program is deterministic (no randomness, no wall clock: every time it
uses comes from the case file), uses only the standard library, and reads no
network. It runs in well under a second per case on the practice cases.
"""

import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# The grader's -P leaves /bot off sys.path: put it back first, so a module
# shipped beside this file would import. (This entry is one file, but the
# line keeps the layout the starter documents.)
sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.6448536269514722, -0.6744897501960817, 0.0, 0.6744897501960817, 1.6448536269514722]

LAUNCH = datetime(2026, 11, 19, 0, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Priors.
#
# Each entry: (day-7 median %, eventual ceiling %, logit spread of the prior).
# Calibrated on lifetime Exophase/PSNProfiles curves (GTA V: first mission
# 73%, final mission 17%, 100% 0.2%, platinum 0.1%; RDR2: chapter 1 90%,
# chapter 2 64%, chapter 3 50%, chapter 4 41%, final 34%, 100% 1.67%,
# platinum 0.44%; Elden Ring: first hub 67-75%, an ending 16-28%, platinum
# 10.9%) and on the live GTA VI reads at ~32h after launch (chapter 1
# 7.99%, chapter 2 0.90%, first mission 100%, fishing 10.57%, Breakfast Run
# 2.52%, arcade 1.11%, 100 vehicles 1.02%). Day-7 medians sit below the
# lifetime ceilings because a week in, most of the launch cohort is still
# working through a 50-60 hour story. See README.md for the full table and
# its sources.
# ---------------------------------------------------------------------------

def _p(day7, ceiling, sd):
    return (day7, ceiling, sd)


PRIORS = {
    # keyed by the trophy name, lower-cased, punctuation stripped
    "vice got a price": _p(0.08, 0.44, 1.00),
    "just like paradise": _p(99.90, 100.0, 0.15),
    "paradise lost": _p(65.0, 90.0, 0.35),
    "ts ass drug money": _p(45.0, 64.0, 0.40),
    "vice city baby": _p(28.0, 50.0, 0.45),
    "top of the world ma": _p(18.0, 41.0, 0.45),
    "you gotta know when to get off": _p(12.0, 34.0, 0.50),
    "trust": _p(10.0, 30.0, 0.60),
    "break the bank": _p(4.0, 25.0, 0.70),
    "family matters": _p(3.0, 20.0, 0.70),
    "dwnfall": _p(2.5, 18.0, 0.70),
    "hijacked": _p(2.0, 16.0, 0.70),
    "snow storm": _p(1.5, 14.0, 0.70),
    "a long road": _p(0.20, 1.67, 0.90),
    "cunning stunts": _p(0.05, 0.80, 1.10),
    "master of none": _p(3.0, 20.0, 0.80),
    "the shootist": _p(1.0, 6.0, 0.90),
    "top fun": _p(0.30, 3.0, 1.00),
    "earn cash not kudos": _p(1.5, 12.0, 0.80),
    "baited my tackle": _p(28.0, 45.0, 0.40),
    "stick fiddler": _p(5.0, 25.0, 0.70),
    "road to rehabilitation": _p(2.5, 12.0, 0.80),
    "this was no boat accident": _p(2.5, 12.0, 0.80),
    "the lone rider": _p(2.0, 10.0, 0.80),
    "strangers freaks": _p(1.0, 8.0, 0.90),
    "supply demand": _p(2.0, 10.0, 0.80),
    "spin on this": _p(2.0, 10.0, 0.80),
    "positive mental attitude": _p(0.60, 6.0, 0.90),
    "fair game": _p(0.80, 6.0, 0.90),
    "dont touch my deck": _p(0.20, 3.0, 1.00),
    "you wainker": _p(0.10, 2.0, 1.10),
    "one last thing": _p(1.5, 10.0, 0.90),
    "hot together": _p(2.0, 12.0, 0.80),
    "retail therapy": _p(0.80, 6.0, 0.90),
    "whip it good": _p(10.0, 45.0, 0.60),
    "gunslinger": _p(1.5, 12.0, 0.80),
    "catch me if you can": _p(1.5, 10.0, 0.80),
    "challenging tank": _p(1.0, 8.0, 0.90),
    "sneakthief": _p(1.0, 8.0, 0.90),
    "maximum withdrawal": _p(0.80, 6.0, 0.90),
    "a classic blitz play": _p(1.5, 10.0, 0.80),
    "the goodtime state": _p(4.0, 35.0, 0.70),
    "pest control": _p(1.0, 8.0, 0.90),
    "in the beginning": _p(1.5, 12.0, 0.80),
    "capital offense": _p(0.60, 5.0, 0.90),
    "lets go bowling": _p(4.0, 20.0, 0.70),
    "personal best": _p(0.50, 5.0, 0.90),
    "actions speak louder": _p(0.50, 5.0, 0.90),
    "bad luck i guess": _p(0.50, 5.0, 0.90),
    "the truth is out there": _p(2.0, 12.0, 0.80),
    "ten pin": _p(0.80, 6.0, 0.90),
    "dime on the dollar": _p(0.50, 5.0, 0.90),
    "treat yo self": _p(1.0, 8.0, 0.90),
    "little boxes": _p(0.50, 5.0, 0.90),
    "on the spot": _p(1.5, 10.0, 0.80),
}

# Fallback priors by description keyword, then by tier, for any trophy the
# table above does not name (a later case could add or rename trophies).
KEYWORD_PRIORS = [
    ("chapter 1", _p(65.0, 90.0, 0.35)),
    ("chapter 2", _p(45.0, 64.0, 0.40)),
    ("chapter 3", _p(28.0, 50.0, 0.45)),
    ("chapter 4", _p(18.0, 41.0, 0.45)),
    ("final mission", _p(8.0, 30.0, 0.60)),
    ("100% completion", _p(0.20, 1.67, 0.90)),
    ("100% game completion", _p(0.20, 1.67, 0.90)),
    ("platinum", _p(0.08, 0.44, 1.00)),
    ("stunt", _p(0.05, 0.80, 1.10)),
    ("gold medal", _p(1.0, 6.0, 0.90)),
    ("collectible", _p(0.20, 3.0, 1.00)),
    ("explore", _p(4.0, 35.0, 0.70)),
    ("race", _p(1.0, 10.0, 0.90)),
    ("fishing", _p(20.0, 40.0, 0.50)),
    ("arcade", _p(5.0, 25.0, 0.70)),
    ("vehicle", _p(5.0, 30.0, 0.70)),
    ("challenge", _p(1.5, 10.0, 0.90)),
    ("stranger", _p(1.5, 10.0, 0.90)),
    ("rob", _p(1.0, 8.0, 0.90)),
    ("meditate", _p(0.60, 6.0, 0.90)),
    ("hunt", _p(0.80, 6.0, 0.90)),
    ("bowling", _p(4.0, 20.0, 0.70)),
    ("cocktail", _p(1.5, 12.0, 0.80)),
    ("spend", _p(1.0, 8.0, 0.90)),
    ("purchase", _p(0.50, 5.0, 0.90)),
    ("register", _p(1.5, 10.0, 0.80)),
    ("wanted level", _p(1.5, 10.0, 0.80)),
    ("complete", _p(2.0, 12.0, 0.80)),
]
TIER_PRIORS = {
    "platinum": _p(0.08, 0.44, 1.00),
    "gold": _p(0.30, 3.0, 1.00),
    "silver": _p(0.50, 5.0, 1.00),
    "bronze": _p(1.0, 10.0, 0.90),
}

# Grid for the saturating curve's speed parameters. Alpha runs to 8: a trophy
# whose rate is still at the 2-decimal floor at the cut and then explodes
# (a late story chapter in the launch week) needs a very steep curve, and a
# grid capped at 4 would fit it with a slow curve and forecast far too low.
ALPHAS = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0]
TAUS = [0.5 * (1200.0 ** (k / 19.0)) for k in range(20)]  # 0.5h .. 600h


def _norm_name(name):
    out = []
    for ch in str(name).lower():
        if ch.isalnum() or ch == " ":
            out.append(ch)
    return " ".join("".join(out).split())


def _prior_for(trophy):
    name = _norm_name(trophy.get("name", ""))
    if name in PRIORS:
        return PRIORS[name]
    desc = str(trophy.get("description", "")).lower()
    text = name + " " + desc
    for keyword, prior in KEYWORD_PRIORS:
        if keyword in text:
            return prior
    return TIER_PRIORS.get(str(trophy.get("tier", "bronze")).lower(),
                           _p(1.0, 10.0, 0.90))


def _parse_time(value):
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _hours_since_launch(moment):
    return max(0.1, (moment - LAUNCH).total_seconds() / 3600.0)


def _clamp_pct(x):
    return min(99.99, max(0.01, x))


def _logit(pct):
    p = _clamp_pct(pct) / 100.0
    return math.log(p / (1.0 - p))


def _inv_logit(lg):
    if lg >= 0:
        return 100.0 / (1.0 + math.exp(-lg))
    e = math.exp(lg)
    return 100.0 * e / (1.0 + e)


def _round4(x):
    """Round to 4 decimals, half up, as the starter's Math.round does."""
    scaled = x * 10000.0
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 10000.0
    return int(value) if float(value).is_integer() else value


def _fit_curve(series, ceiling, t_target):
    """Fit one trophy's reads and extrapolate to the target.

    Three families compete on the same weighted logit-space loss, so the
    data picks the shape that fits it:
      * a saturating log-logistic curve rising toward the ceiling;
      * a power-law approach to the ceiling anchored at the last read
        (gamma = 0 is the flat line: it wins on a frozen page, so a flat
        history does not invent growth);
      * a straight line of logit(rate) on ln(1 + t), the house curve
        baseline's model: a pure power law in the odds, which is what a
        trophy in its steep early-growth phase actually follows.
    Returns (median_at_target, rms_residual, n_informative, u) where u is
    the extrapolation uncertainty: half the logit range of the target
    predictions among all candidates that fit nearly as well as the best.
    When the history cannot tell those candidates apart, u is large, and
    the caller trusts the fit less and widens the spread.
    """
    informative = [(t, r, n, w) for (t, r, n, w) in series if r is not None and r > 0]
    if len(informative) < 2:
        return None
    # Logit-space targets with a half-step floor (0.005%): a read shows two
    # decimals, so 0.00% means the rate is below half a step, and a rate of
    # 0.01% is already above it. (A half-player floor from players_tracked
    # would be wrong here: Exophase's printed rates are not a simple
    # earners/tracked count - the launch-night page shows 0.02% with only
    # 638 players tracked, a fraction of a player - so the display
    # resolution, not the player count, is the binding constraint.)
    pts = []
    for t, r, n, w in informative:
        pts.append((t, _logit(max(r, 0.005)), w))
    total_w = sum(w for _, _, w in pts) or 1.0
    t_last, r_last = pts[-1][0], informative[-1][1]

    def _loss_of(predict):
        loss = 0.0
        for t, lg, w in pts:
            d = _logit(predict(t)) - lg
            if d > 8.0:
                d = 8.0
            elif d < -8.0:
                d = -8.0
            loss += w * d * d
        return loss / total_w

    candidates = []  # (loss, prediction at the target)
    for alpha in ALPHAS:
        for tau in TAUS:
            pred = lambda t, a=alpha, u=tau: ceiling * (t / (t + u)) ** a
            candidates.append((_loss_of(pred), pred(t_target)))
    for gamma in (0.0, 0.25, 0.5, 1.0, 2.0, 4.0):
        pred = lambda t, g=gamma: ceiling + (r_last - ceiling) * (t_last / t) ** g
        candidates.append((_loss_of(pred), pred(t_target)))
    # Line family: weighted least squares of logit(rate) on ln(1 + t).
    xs = [math.log1p(t) for t, _, _ in pts]
    ys = [lg for _, lg, _ in pts]
    ws = [w for _, _, w in pts]
    sw = sum(ws)
    mx = sum(w * x for w, x in zip(ws, xs)) / sw
    my = sum(w * y for w, y in zip(ws, ys)) / sw
    sxx = sum(w * (x - mx) ** 2 for w, x in zip(ws, xs))
    slope = (sum(w * (x - mx) * (y - my) for w, x, y in zip(ws, xs, ys)) / sxx
             if sxx else 0.0)
    intercept = my - slope * mx
    line_loss = sum(w * (y - (intercept + slope * x)) ** 2
                    for w, x, y in zip(ws, xs, ys)) / sw
    line_pred = min(_inv_logit(intercept + slope * math.log1p(t_target)), ceiling)
    candidates.append((line_loss, line_pred))

    best_loss, best_pred = min(candidates, key=lambda c: c[0])
    near = [p for (loss, p) in candidates if loss <= best_loss + 0.5]
    lo = min(_logit(max(p, 0.01)) for p in near)
    hi = max(_logit(min(p, 99.99)) for p in near)
    u = (hi - lo) / 2.0
    rms = math.sqrt(max(best_loss, 0.0))
    return best_pred, rms, len(informative), u


def _forecast_trophy(trophy, series, t_target, horizon_days):
    """Return (median_pct, spread_logit) for one trophy at the target."""
    day7, ceiling, prior_sd = _prior_for(trophy)
    last_rate = None
    for _, r, _, _ in reversed(series):
        if r is not None:
            last_rate = r
            break

    # The opening mission: every tracked player has done it at every read,
    # and it cannot fall while the base only grows with players who play it.
    # Its rate is pinned at the top (100.00% at every read, including 10,000
    # players in), so the median is the clamped maximum with a tight spread.
    if last_rate is not None and last_rate >= 99.5:
        return 99.99, 0.15

    # Horizon-aware prior. Over a 90-minute horizon a rate barely moves from
    # its last read; over 4.5 days it approaches the category's day-7 value.
    # (The practice pays nothing, but a prior that ignores the horizon would
    # also be wrong on the final: it would pull every trophy toward its
    # day-7 value even when the last read is only hours old.)
    h = horizon_days / (horizon_days + 1.5)
    # A 0.00% last read means the rate is below half a display step (0.005%),
    # not zero - see the note in _fit_curve.
    last_logit = _logit(max(last_rate, 0.005)) if last_rate is not None else _logit(day7)
    prior_logit = (1.0 - h) * last_logit + h * _logit(day7)
    prior_median = _inv_logit(prior_logit)
    prior_sd_eff = prior_sd * (0.3 + 0.7 * h)
    h_scale = math.sqrt(0.25 + horizon_days / 3.0)

    fit = _fit_curve(series, ceiling, t_target)
    if fit is None:
        # No signal yet: the horizon-aware prior alone, with a wide spread.
        spread = min(2.2, max(0.5, prior_sd_eff * 1.3 * h_scale))
        return prior_median, spread

    median_fit, rms, n_info, u = fit
    # Shrink the fitted median toward the prior in logit space. The weight
    # grows with the amount of informative history and falls when the fit is
    # poor (a flat or jumpy history says little about the curve's speed) or
    # when the history cannot tell the near-best extrapolations apart (u
    # large: the data does not pin down the target value, so the prior - the
    # category's typical week-one level - carries more of the forecast).
    w_data = n_info / (n_info + 8.0)
    if rms > 0.8:
        w_data *= max(0.25, 0.8 / rms)
    w_data *= 1.0 / (1.0 + u / 2.0)
    w_data = min(0.85, w_data)
    median_logit = w_data * _logit(median_fit) + (1.0 - w_data) * prior_logit
    median = _inv_logit(median_logit)
    # Never forecast above the lifetime ceiling - unless the last read is
    # already above it (early adopters are hardcore: a rate can sit above its
    # lifetime ceiling while the tracked base is small, then fall by dilution).
    median = min(median, max(ceiling, last_rate if last_rate is not None else ceiling))
    # The 0.8 factor on the spread is backtest-tuned: on 30 simulated launch
    # weeks (a Weibull truth, day-7 drawn around the prior with log-sd 0.3,
    # and again with 0.6) a spread scaled by 0.8 scored 0.32-0.34 against
    # 0.36-0.38 unscaled and 0.40 at 1.2, while the practice case was
    # unchanged. See simulator.py.
    spread = math.sqrt((0.8 * prior_sd_eff * h_scale) ** 2
                       + (0.8 * 0.6 * rms * h_scale) ** 2 + (0.8 * 0.7 * u) ** 2)
    spread = min(2.2, max(0.25, spread))
    return median, spread


def _forecast_case(case, name):
    if not case.get("history"):
        raise ValueError(f"{name} has no history")
    horizon_minutes = float(case.get("horizon_minutes", 0) or 0)
    horizon_days = horizon_minutes / 1440.0
    target = _parse_time(case["target"])
    t_target = _hours_since_launch(target)
    at = _parse_time(case["at"])
    t_at = _hours_since_launch(at)

    # One subsampled read list, shared by every trophy: the last 40 reads
    # carry the signal; earlier reads are stale (the launch-night page was
    # frozen for hours) and only dilute the fit.
    history = sorted(case["history"], key=lambda r: r.get("slot", ""))
    # Reads before launch are a pre-launch snapshot, not launch-night data:
    # their rates are already at their frozen values at t ~ 0, which would
    # force every fitted curve to rise impossibly fast. Drop them.
    history = [r for r in history
               if _parse_time(r.get("slot") or r.get("at")) >= LAUNCH]
    if len(history) > 40:
        history = history[-40:]
    reads = []
    for read in history:
        slot = _parse_time(read.get("slot") or read.get("at"))
        t = _hours_since_launch(slot)
        players = read.get("players_tracked") or 0
        age = max(0.0, t_at - t)
        weight = math.sqrt(players) * math.exp(-age / 72.0) if players else 1.0
        reads.append((t, read.get("rates") or [], weight, players))

    trophies = case["trophies"]
    medians = {}
    spreads = {}
    for i, trophy in enumerate(trophies):
        series = []
        for t, rates, weight, players in reads:
            rate = rates[i] if i < len(rates) else None
            series.append((t, rate, players, weight))
        median, spread = _forecast_trophy(trophy, series, t_target, horizon_days)
        medians[trophy["id"]] = median
        spreads[trophy["id"]] = spread

    # Structural constraints on the medians (true of the game itself):
    # the story chapters are nested, and the platinum needs 100% completion.
    by_name = {_norm_name(t.get("name", "")): t["id"] for t in trophies}
    chain = ["paradise lost", "ts ass drug money", "vice city baby",
             "top of the world ma", "you gotta know when to get off"]
    chain_ids = [by_name[n] for n in chain if n in by_name]
    for prev_id, next_id in zip(chain_ids, chain_ids[1:]):
        if medians[next_id] > medians[prev_id]:
            medians[next_id] = medians[prev_id]
    plat = by_name.get("vice got a price")
    full = by_name.get("a long road")
    if plat is not None and full is not None and medians[plat] > medians[full]:
        medians[plat] = medians[full]

    rows = []
    for trophy in trophies:
        tid = trophy["id"]
        lg = _logit(medians[tid])
        s = spreads[tid]
        qs = []
        for z in Z:
            q = _inv_logit(lg + z * s)
            qs.append(_round4(_clamp_pct(q)))
        # Keep the row non-decreasing after rounding.
        for k in range(1, 5):
            if qs[k] < qs[k - 1]:
                qs[k] = qs[k - 1]
        rows.append({"id": tid, "q": qs})
    rows.sort(key=lambda row: row["id"])
    return {"trophies": rows}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = _forecast_case(case, path.name)
        out_path = OUTPUT_DIR / f"{path.stem}.out"
        out_path.write_text(json.dumps(forecast, separators=(",", ":")) + "\n",
                            encoding="utf-8")


if __name__ == "__main__":
    main()
