# GTA VI trophy rarity forecast

[![make.fun · gta6-trophy-rarity-forecast-01](https://make.fun/badge/gta6-trophy-rarity-forecast-01.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![rank](https://make.fun/badge/gta6-trophy-rarity-forecast-01/mift2609/gta6-trophy-rarity-forecast-01/rank.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![reward](https://make.fun/badge/gta6-trophy-rarity-forecast-01/mift2609/gta6-trophy-rarity-forecast-01/reward.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)

A program for [make.fun](https://make.fun)'s `gta6-trophy-rarity-forecast-01`
bounty: forecast, for every one of Grand Theft Auto VI's 55 PlayStation 5
trophies, the percent of the players Exophase tracks who will have earned it
at 2026-11-26T00:00:00Z (a week after launch), as five quantiles
(5/25/50/75/95%) per trophy. The score is the mean pinball loss on the logit
scale; the lowest loss wins, and a prize needs a lower loss than the best
house entry.

`main.py` is the whole entry: Python 3.13, standard library only, offline,
deterministic, ~0.2 s per practice case and ~0.4 s on a 119-read final-like
case (limit 8 s). It reads every `/input/<id>.in` and writes
`/output/<id>.out`.

## Method

Three curve families compete on the same weighted logit-space loss, so the
data picks the shape that fits each trophy:

1. **Saturating log-logistic** — `rate(t) = C * (t / (t + tau)) ** alpha`,
   rising toward the trophy's eventual (lifetime) ceiling `C`, on a grid of
   `alpha` (0.5–8) and `tau` (0.5–600 h).
2. **Power-law approach to the ceiling**, anchored at the last read —
   `C + (r_last - C) * (t_last / t) ** gamma`, `gamma` in 0–4. `gamma = 0`
   is the flat line (persistence): it wins on a frozen page, so a flat
   launch-night history does not invent growth. `gamma > 0` lets a falling
   (dilution-dominated) series decay toward the ceiling.
3. **A straight line of logit(rate) on ln(1 + t)** — the house curve
   baseline's model, a pure power law in the odds. That is what a trophy in
   its steep early-growth phase actually follows, and it is the family that
   carries the late story chapters, whose rates are still at the 2-decimal
   floor at the cut and then explode.

The fit is weighted by `sqrt(players tracked)` and by recency, in logit
space, with a half-step floor (0.005%) for zero rates — Exophase prints two
decimals, so 0.00% means "below half a step", and the printed rates are not
a simple earners/tracked count (the launch-night page shows 0.02% with only
638 players tracked, a fraction of a player), so the display resolution, not
the player count, is the binding constraint.

The fitted median is shrunk in logit space toward a **horizon-aware prior**:
over a 90-minute horizon a rate barely moves from its last read; over 4.5
days it approaches the category's day-7 value. The shrinkage weight grows
with the amount of informative history and falls when the fit is poor or
when the history cannot tell the near-best extrapolations apart — the
**extrapolation uncertainty `u`**, half the logit range of the target
predictions among all candidates that fit nearly as well as the best. When
`u` is large the prior carries more of the forecast and the spread widens.

Two structural constraints are enforced on the medians, because they are
true of the game itself: the story chapters are non-increasing
(Ch1 ≥ Ch2 ≥ Ch3 ≥ Ch4 ≥ final mission), and the platinum cannot exceed
100% completion. A rate is never forecast above its lifetime ceiling unless
the last read is already above it (early adopters are hardcore: a rate can
sit above its lifetime ceiling while the tracked base is small, then fall by
dilution — the platinum was 0.63% at 638 players and will fall as the base
grows).

Quantiles are a logit-normal spread around the median. The spread grows
with the category's prior width, the fit residual, the extrapolation
uncertainty `u` and the horizon, scaled by 0.8 (backtest-tuned, see below).
Reads before launch are dropped (the 23:50Z pre-launch snapshot would force
every curve to rise impossibly fast), and the history is subsampled to the
last 40 reads.

## Calibration — the priors

The category table in `main.py` (`PRIORS`) gives, per trophy, a day-7
median, an eventual (lifetime) ceiling and a logit spread. It is calibrated
on three sources:

**1. Lifetime earn-rate curves of comparable open-world games.**

| Trophy (analogue) | RDR2 (PSNProfiles, ~194,709 players) | GTA V (PocketPSN, PS4) | Elden Ring |
|---|---|---|---|
| First mission | 96.25% | 73.1% | — |
| Chapter 1 | 90.36% | — | Roundtable Hold 66.8–74.9% |
| Chapter 2 | 64.24% | — | Margit 70.9% |
| Chapter 3 | 50.38% | — | — |
| Chapter 4 | 41.37% | — | — |
| Final mission | 33.92% | 16.8% | Endings 16–28% |
| Epilogue | 29.67% | — | — |
| 100% completion | 1.67% | 0.2% | — |
| 70 gold medals | 1.11% | 0.1% | — |
| Platinum | 0.44% | 0.1% | 10.9% |
| 10 stranger strands | 17.78% | — | — |
| Skin every animal | 1.63% | — | — |

GTA V's story rates are diluted by Online-only players (GTA VI is
single-player only at launch), so its story rates run lower; RDR2 is the
closest analogue (a 50–60 hour Rockstar story, single-player at launch).
The day-7 medians sit below the lifetime ceilings because a week in, most
of the launch cohort is still working through the story.

**2. The live GTA VI page at ~32.5 h after launch** (Exophase,
fetched 20 Nov 2026 08:27 UTC; ~10,000 players tracked): platinum 0.00%,
first mission 100.00%, Ch1 7.99%, Ch2 0.90%, Ch3/Ch4/final 0.02%,
Breakfast Run 2.52%, fishing 10.57%, arcade 1.11%, 100 vehicles 1.02%,
bowling 0.75%, The Truth Is Out There 0.44%, Hot Together 0.19%, VCIA
departure 0.18%, Rhinos 0.17%, cocktail 0.12%, Gunslinger 0.07%, Ten Pin
0.04%, Sneakthief 0.03%, most others 0.01–0.02% (the 1–2 player floor),
and 100% / 250 stunts / drone races / 8 stranger strands / 3 card sets /
WAiNK 100 / 50 challenges at 0.00%.

Two lessons from that snapshot drive the model. First, **dilution**: Ch3
fell from 1.1% (638 players, launch night) to 0.02% (10,000 players) — not
because players un-earned it, but because the tracked base grew ~16× while
only a couple more players reached chapter 3. A naive trend fit on the
early reads is badly fooled by this, so the model separates earners from
players-tracked and leans on category priors for dilution-dominated
trophies. Second, **the first mission stays at ~100%**: the denominator is
trophy-earners, so the opening mission is pinned at the top and is forecast
at 99.99% with a tight spread.

**3. The kit's own practice cases** (p00/p01): their histories are flat —
every read identical — because Exophase refreshes on its own schedule
(hours apart), not continuously. The flat family and the horizon-aware
prior are what keep a frozen page from being read as a forecast of no
movement or of explosive movement.

The full per-trophy table (day-7 median / ceiling / logit sd) is in
`main.py`. Representative values: Ch1 65/90/0.35,
Ch2 45/64/0.40, Ch3 28/50/0.45, Ch4 18/41/0.45, final 12/34/0.50,
fishing 28/45/0.40, 100% 0.20/1.67/0.90, platinum 0.08/0.44/1.00,
250 stunts 0.05/0.80/1.10, 100 vehicles 10/45/0.60.

## Assumptions

- The launch cohort progresses through the story roughly like RDR2's did,
  scaled to a 50–60 hour story; a week in, the median player is somewhere
  in chapters 2–3.
- A trophy's day-7 rate is driven by two things: how far into the game it
  sits, and how many players bother with that activity. Story-mission
  trophies track their chapter closely; optional activities (fishing,
  arcade, bowling) are front-loaded because players try them early.
- Exophase's tracked base keeps growing through the week, so rates for
  late-game trophies are dilution-dominated until the earners catch up.
- The category priors are the weakest link: they are educated from other
  games, not measured for GTA VI. The fit's job is to correct them with the
  case's own history wherever that history carries signal; where it does
  not (a trophy still at the floor), the prior is all there is, and the
  spread says so.

## Backtest

`simulator.py` (kept out of the repo, in the author's workspace) simulates
plausible launch weeks: a Weibull truth family — different from the
forecaster's families, so a good score is not the fit recognising itself —
calibrated to pass through the live 32 h snapshot and a day-7 value drawn
around the prior (log-sd 0.3, and again 0.6), with the tracked base
calibrated to 10,000 players at 32.5 h and the page refreshing every 3–8 h
so reads repeat between refreshes, like the real history. It scores this
entry against the two house baselines reimplemented from the kit's
description (persistence; least-squares line in ln(1+t) over the last 24 h).

| Case (30 simulated weeks) | This entry | Persistence | Trend |
|---|---|---|---|
| Final (cut 59.5 h → target 168 h) | **0.32** | 1.97 | 0.50 |
| Final, prior error doubled (log-sd 0.6) | **0.34** | — | — |
| Practice (cut 3 h → target 4.5 h, 10 weeks) | **0.28** | 0.30 | 0.30 |

Mean pinball loss on the logit scale; lower is better. The entry beats
both house baselines in 30/30 simulated final weeks. The spread scale of
0.8 was chosen on this backtest (0.8 scored 0.32, 1.0 scored 0.36, 1.2
scored 0.40) and is robust to doubling the prior error.

## Running it

```sh
mkdir -p out
MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Or under the grader's invocation: `python3 -P -s /bot/main.py` with
`/input` and `/output` in place.

## License

MIT — see `LICENSE`.
