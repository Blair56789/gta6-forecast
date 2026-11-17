# Model

## The problem, in one paragraph

GTA VI releases 2026-11-19 on PS5 and Xbox Series X|S, single-player, no PC
until 2027, and no console maker publishes a player count — so the count
this contest forecasts is Twitch's own concurrent viewers in the "Grand
Theft Auto VI" category. The program sees everything up to the end of hour
1 (00:00–01:00 UTC) and must forecast hours 2–24 as five quantiles each,
scored by mean pinball loss on the log scale. The unlock rolls at local
midnight, country by country: New Zealand first (11:00Z on 18 Nov), central
Europe 23:00Z, the UK 00:00Z, US Eastern 05:00Z, US Pacific 08:00Z. So hour
1 is mostly Europe + Oceania + Asia; the Americas arrive during hours 5–9;
the peak lands in the European evening / US afternoon. Any forecaster that
just says "hour 1, all day" (the house baseline) misses that whole shape.

## What the data says

The kit ships 38 past big launches with hourly Twitch category averages
(SullyGnome), each covering 14 days before to 3 days after its release day.
37 of them have a complete, positive release-day curve. Across those 37:

- The median curve dips to 0.73x the hour-1 print around hour 4, then
  climbs to ~2.4x around hours 19–20, then eases off. The shape is the
  timezone story above, and it is stable across launches.
- The level is everything, and it is non-linear: the correlation between
  ln(hour-1 print) and the log-ratio at hour 20 is −0.94. Launches with a
  small hour-1 print (a few thousand) grow 5–10x over the day; launches
  with a huge hour-1 print (~850k, e.g. ELDEN RING, Cyberpunk 2077 — both
  with a PC unlock just before the UTC day) stay flat or decline.
- The cross-launch scatter is wide late in the day (std of the log-ratio
  ~2.1 at hours 15–24 in the raw ratios), so the quantiles must be wide —
  but most of that scatter is the level effect above, not noise: once the
  level is conditioned on, the residual std is ~0.4–0.5 among launches of
  a similar size.
- Hour-1 channels add nothing once viewers are known (tested: no gain on
  the practice cases).

## The model

For each hour h = 2..24, least squares over the case's comparables with a
complete, positive release-day curve:

```
ln(viewers_h) = b0 + b1 * ln(v1) + b2 * ln(v1)^2 + b3 * ln(1 + pre)
```

- `v1`: the case's hour-1 print (floor 1).
- `pre`: the case's own pre-launch baseline — mean viewers of its category
  over [day_start − 2 days, day_start − 1 day), from `history_hourly`
  (falling back to the minute-resolution `history`, then to 0). The fitted
  b3 is negative: given the same hour-1 print, a category that already had
  viewers before launch grows less — its hour 1 was front-loaded by people
  already watching the category.
- The window [−2d, −1d) is deliberate: it ends a full day before launch so
  early regional unlocks (New Zealand unlocks ~12h before the UTC day)
  cannot contaminate the baseline, and it exists in both the practice and
  the final cases. A small ridge (1e-8) keeps the normal equations
  solvable if a feature column degenerates.
- Extrapolation guard: outside the comparables' ln(v1) range, the quadratic
  is replaced by its tangent at the nearest boundary. GTA VI's hour-1 print
  may exceed every comparable's (max ~875k); the guard keeps the forecast
  monotone increasing in v1 instead of letting the parabola turn down.
  Checked: the fitted tangent slope at the top boundary is positive
  (+0.78..+0.97) for every hour, so a hypothetical 1.5M hour-1 print
  extrapolates to a ~1.3–1.5M peak, and holding out ELDEN RING (the
  biggest comparable) scores 0.1004 with the guard.
- Spread: the residual standard deviation among the 12 comparables nearest
  in ln(v1), floored at 0.20 log units, scaled by 0.9. A launch's
  uncertainty looks like launches its own size. Quantiles are
  `exp(pred + z_tau * sd)` with z = (−1.645, −0.674, 0, 0.674, 1.645),
  clamped to [1, 1e9].
- Fallbacks, in order: fewer than 12 usable comparables → a linear fit on
  ln(v1) only; fewer than 5 → the house persistence baseline. The output
  is always a valid forecast.

Nothing is hard-coded from the practice answers: every coefficient is
fitted from the case file at run time. The final case's comparables
(including the four practice launches) are used the same way.

## How the pieces were chosen

Each candidate was scored with the competition's own loss on the four
practice cases (answers: SullyGnome hourly averages, verified by
reproducing all four hour-1 prints exactly), plus a leave-one-out run over
all 37 complete launches (each held-out launch scored against its own
curve, fitted on the other 36):

| model | practice mean | LOO mean (37) | LOO mean, v1 ≥ 20k (27) |
| --- | --- | --- | --- |
| house persistence baseline | 0.3871 | — | — |
| linear in ln(v1), global spread | 0.2265 | — | — |
| quadratic in ln(v1), global spread | 0.2128 | — | — |
| quadratic + pre, global spread | 0.1827 | 0.4003 | — |
| quadratic + pre, local spread k12, scale 0.9 | **0.1443** | 0.3900 | 0.2721 |
| quadratic + pre, local spread k12, scale 0.8 | 0.1403 | 0.3964 | 0.2759 |
| quadratic + pre, local spread k12, scale 1.0 | 0.1496 | 0.3857 | 0.2697 |
| quadratic + pre, local spread k16, scale 0.9 | 0.1581 | 0.3872 | — |
| quadratic + pre-rel, local spread k12, scale 0.9 | 0.1486 | 0.3833 | — |
| quadratic + pre, kernel-weighted fit | 0.2128 | — | — |
| quadratic + pre, hour-smoothed medians | 0.1836 | — | — |

Decisions the numbers forced: the quadratic over the linear fit (the big
launches' late hours); the pre-launch baseline (consistent gains on all
four practice cases); the local spread over a global one (0.183 → 0.144
on practice); keeping every tier of comparable (excluding launches with
v1 < 5,000 made LOO much worse, 0.4890); no channels feature; no kernel
weighting; no hour smoothing. The 2-day pre window beat the 3-day and
7-day windows on every set (practice 0.1443 vs 0.1482 vs 0.1496; LOO
v1 ≥ 50k 0.2309 vs 0.2435 vs 0.2443). The 0.9 spread scale is a
compromise: the practice cases favour narrower (0.7: 0.1376) and the
bigger-launch LOO favours wider (1.1: 0.2685); 0.9 sits within 0.007 of
the best on both.

## Practice results (the entry as submitted)

| case | hour-1 print | loss | typical miss | 90% coverage |
| --- | --- | --- | --- | --- |
| Marvel's Wolverine | 23,357 | 0.1311 | 19.6% | 1.000 |
| Red Dead Redemption 2 | 116,550 | 0.1431 | 26.8% | 1.000 |
| God of War Ragnarök | 269,517 | 0.1241 | 21.2% | 1.000 |
| Marvel's Spider-Man 2 | 119,087 | 0.1790 | 31.0% | 0.783 |
| **mean** | | **0.1443** | | |
| house baseline | | 0.3871 | 82.8% | 0.783 |

Reproduce with `python3 evaluation/score.py --kit <kit dir>`. The entry
runs all four practice cases in ~0.3s total (cap is 8s per case) and is
deterministic: two runs produce byte-identical outputs.

## What could still go wrong on the final

- **One launch, not four.** The practice mean is an average over four
  launches; the final is a single draw. GTA VI is the biggest launch in
  the set by a wide margin, so the forecast leans on the tangent guard
  and on the biggest comparables (ELDEN RING, Cyberpunk 2077, Hogwarts
  Legacy). If GTA VI's hour-1 print is far above the training range, the
  forecast is an extrapolation, and the spread — set by the nearest big
  launches — is the honest part of the answer.
- **Big launches can surprise.** In the leave-one-out run, Diablo IV
  scored 0.5612 and Hogwarts Legacy 0.2579: their curves grew far more
  than the model expects for their hour-1 print. A 2x miss on the median
  is possible; the quantiles are built to absorb it.
- **The final case's history is minute-resolution** while the practice
  cases' is hourly; the pre-launch baseline reads `history_hourly`
  first and only falls back to the minute points, so this should not
  matter, but it is untested on real final data.
