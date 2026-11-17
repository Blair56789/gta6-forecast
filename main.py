"""GTA VI launch-day Twitch CCU forecaster (gta6-twitch-ccu-forecast-01).

Reads one case (/input/<id>.in, schema makefun/twitch-ccu-case/v1) and writes
one forecast (/output/<id>.out): for each UTC hour 2..24 of release day
2026-11-19, five quantiles (5/25/50/75/95%) of the concurrent viewers in
the "Grand Theft Auto VI" Twitch category. Python 3.13, standard library
only; no network, no clock, no randomness: the same input always gives the
same output.

How it forecasts
-----------------
The case ships a set of past big game launches ("comparables"), each with
its release-day hourly Twitch curve. Three facts about those curves drive
the model:

1. The day has a timezone shape. A launch unlocks at local midnight,
   country by country, so the category usually dips to ~0.7x the hour-1
   print around hour 4, then climbs to ~2.4x around hours 19-20 (European
   evening + US afternoon) before easing off.
2. The level decides the growth, and non-linearly. Small hour-1 prints
   grow several-fold over the day as time zones unlock; huge hour-1 prints
   (already near the day's peak, often after a PC unlock just before the
   UTC day) stay flat or fall. Across the comparables, corr(ln v1, ln ratio
   at hour 20) is about -0.94, so the fit is quadratic in ln(v1).
3. A pre-existing audience dampens growth. Given the same hour-1 print, a
   category that already had viewers before launch grows less over the day
   (its hour 1 was front-loaded by people already watching). The model
   therefore also uses the category's mean viewers over the two days
   ending one day before launch, ln(1 + pre).

So for each hour h = 2..24, the model fits by least squares over the
comparables with a complete, positive release-day curve:

    ln(viewers_h) = b0 + b1 * ln(v1) + b2 * ln(v1)^2 + b3 * ln(1 + pre)

where v1 is the case's hour-1 print. A tiny ridge (1e-8) keeps the normal
equations solvable when a feature column degenerates.

Extrapolation guard: GTA VI may print a bigger hour 1 than any comparable
(max ~875k). Outside the comparables' ln(v1) range the quadratic is
replaced by its tangent at the nearest boundary, so a record print can
never make the forecast turn down. (Checked: the fitted tangent slope at
the top boundary is positive, +0.78..+0.97, for every hour, so a 1.5M
hour-1 print extrapolates to a ~1.3-1.5M peak, not a collapse.)

Spread: the residual standard deviation among the 12 comparables nearest
in ln(v1) -- a launch's uncertainty looks like launches its own size --
floored at 0.20 log units and scaled by 0.9. Quantiles are
exp(pred + z_tau * sd) with z = (-1.645, -0.674, 0, 0.674, 1.645).
The 0.9 scale is a compromise between the practice cases (which favour
narrower) and a leave-one-out run over the bigger launches (which favour
wider); it sits within 0.007 of the best on both.

Fallbacks (the output is always a valid forecast): fewer than 12 usable
comparables -> a linear fit on ln(v1) only; fewer than 5 -> the house
persistence baseline (every hour at the hour-1 print, spread widening
like a random walk). A case with no hour-1 print falls back to its last
pre-checkpoint hourly mean, then to 1 viewer.

Validation (local scorer, competition's own pinball loss on the log scale,
practice answers = the four launches' SullyGnome hourly averages, whose
hour-1 prints reproduce the cases exactly):
    p00 Marvel's Wolverine   0.1311
    p01 Red Dead Redemption 2 0.1431
    p02 God of War Ragnarok   0.1241
    p03 Marvel's Spider-Man 2 0.1790
    mean 0.1443 vs house baseline 0.3871 (62.7% lower).
"""

import json
import math
import os
import statistics
import sys
from datetime import datetime, timedelta
from pathlib import Path

LEVELS = (0.05, 0.25, 0.5, 0.75, 0.95)
Z_SCORES = (-1.645, -0.674, 0.0, 0.674, 1.645)
FORECAST_HOURS = range(2, 25)

K_NEAREST = 12          # comparables nearest in ln(v1) used for the spread
SPREAD_SCALE = 0.9      # shrinkage on the local residual std
SPREAD_FLOOR = 0.20     # minimum spread, log units
RIDGE = 1e-8            # keeps a degenerate feature column solvable
MIN_FOR_QUADRATIC = 12  # comparables needed for the full fit
MIN_FOR_LINEAR = 5      # comparables needed for any regression at all


def parse_time(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def release_day_curve(hourly_points, day_start):
    """Hourly viewers for hours 1..24 of a launch day, or None if incomplete."""
    curve = {}
    for point in hourly_points or []:
        viewers = point.get("viewers")
        if viewers is None:
            continue
        hour = int((parse_time(point["from"]) - day_start).total_seconds() // 3600) + 1
        if 1 <= hour <= 24:
            curve[hour] = viewers
    if len(curve) != 24 or any(v <= 0 for v in curve.values()):
        return None
    return curve


def pre_launch_mean(hourly_points, minute_points, day_start):
    """Mean category viewers over [day_start - 2d, day_start - 1d).

    The window ends a full day before launch on purpose: the last 24h can
    already contain early regional unlocks (New Zealand unlocks ~12h
    before the UTC day), which would contaminate a "pre-launch" baseline.
    Falls back to the minute-resolution history, then to 0.
    """
    start = day_start - timedelta(days=2)
    end = day_start - timedelta(days=1)
    for points in (hourly_points, minute_points):
        values = [
            p["viewers"]
            for p in (points or [])
            if p.get("viewers") is not None
            and start <= parse_time(p["from"]) < end
        ]
        if values:
            return sum(values) / len(values)
    return 0.0


def solve_linear(matrix, vector):
    """Gaussian elimination with partial pivoting; None if singular."""
    n = len(vector)
    rows = [list(matrix[i]) + [vector[i]] for i in range(n)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(rows[r][col]))
        if abs(rows[pivot][col]) < 1e-12:
            return None
        rows[col], rows[pivot] = rows[pivot], rows[col]
        for r in range(n):
            if r == col:
                continue
            factor = rows[r][col] / rows[col][col]
            for k in range(col, n + 1):
                rows[r][k] -= factor * rows[col][k]
    return [rows[i][n] / rows[i][i] for i in range(n)]


def least_squares(design, targets):
    """Least squares with a tiny ridge; returns coefficients or None."""
    k = len(design[0])
    normal = [[0.0] * k for _ in range(k)]
    rhs = [0.0] * k
    for row, y in zip(design, targets):
        for a in range(k):
            rhs[a] += row[a] * y
            for b in range(k):
                normal[a][b] += row[a] * row[b]
    for a in range(k):
        normal[a][a] += RIDGE
    return solve_linear(normal, rhs)


def design_row(v1, pre, quadratic):
    x = math.log(max(v1, 1))
    if quadratic:
        return [1.0, x, x * x, math.log1p(max(pre, 0.0))]
    return [1.0, x]


def fit_hour(comparables, hour, v1, pre):
    """Fit one hour; returns (log-median prediction, log-spread)."""
    use_quadratic = len(comparables) >= MIN_FOR_QUADRATIC
    design = [design_row(c["v1"], c["pre"], use_quadratic) for c in comparables]
    targets = [math.log(c["curve"][hour]) for c in comparables]
    beta = least_squares(design, targets)
    if beta is None:  # degenerate design: drop to the linear fit
        use_quadratic = False
        design = [design_row(c["v1"], c["pre"], False) for c in comparables]
        beta = least_squares(design, targets)
    if beta is None:
        return None, None

    x = math.log(max(v1, 1))
    row = design_row(v1, pre, use_quadratic)
    prediction = sum(b * f for b, f in zip(beta, row))

    # Tangent guard: outside the comparables' ln(v1) range, follow the
    # fitted curve's slope at the nearest boundary instead of the parabola.
    xs = [math.log(c["v1"]) for c in comparables]
    low, high = min(xs), max(xs)
    if x < low or x > high:
        edge = low if x < low else high
        edge_row = design_row(math.exp(edge), pre, use_quadratic)
        edge_pred = sum(b * f for b, f in zip(beta, edge_row))
        if use_quadratic:
            slope = beta[1] + 2.0 * beta[2] * edge
        else:
            slope = beta[1]
        prediction = edge_pred + slope * (x - edge)

    # Spread from the K nearest launches in ln(v1): their in-sample
    # residuals around this hour's fit.
    residuals = [
        y - sum(b * f for b, f in zip(beta, row))
        for row, y in zip(design, targets)
    ]
    nearest = sorted(
        range(len(comparables)),
        key=lambda i: abs(math.log(comparables[i]["v1"]) - x),
    )[:K_NEAREST]
    local = [residuals[i] for i in nearest]
    spread = statistics.pstdev(local) if len(local) > 1 else 0.5
    spread = max(spread * SPREAD_SCALE, SPREAD_FLOOR)
    return prediction, spread


def persistence_baseline(v1):
    """House baseline: every hour at the hour-1 print, random-walk spread."""
    rows = []
    for hour in FORECAST_HOURS:
        quantiles = [
            round(v1 * math.exp(z * 0.15 * math.sqrt(hour - 1)), 2)
            for z in Z_SCORES
        ]
        rows.append({"hour": hour, "q": quantiles})
    return {"hours": rows}


def forecast(case):
    known = case.get("known") or []
    v1 = known[0].get("viewers") if known else None
    day_start = parse_time(case["day_start"])
    if not v1 or v1 <= 0:
        history = case.get("history_hourly") or []
        values = [p["viewers"] for p in history if p.get("viewers")]
        v1 = values[-1] if values else 1
    v1 = max(v1, 1)

    pre = pre_launch_mean(
        case.get("history_hourly"), case.get("history"), day_start
    )

    comparables = []
    for comp in case.get("comparables") or []:
        curve = release_day_curve(comp.get("hourly"), parse_time(comp["day_start"]))
        if curve is None:
            continue
        comparables.append(
            {
                "v1": curve[1],
                "curve": curve,
                "pre": pre_launch_mean(
                    comp.get("hourly"), None, parse_time(comp["day_start"])
                ),
            }
        )

    if len(comparables) < MIN_FOR_LINEAR:
        return persistence_baseline(v1)

    rows = []
    for hour in FORECAST_HOURS:
        prediction, spread = fit_hour(comparables, hour, v1, pre)
        if prediction is None:
            return persistence_baseline(v1)
        quantiles = []
        previous = 0.0
        for z in Z_SCORES:
            q = math.exp(prediction + z * spread)
            q = max(1.0, min(1e9, q))
            q = round(q, 2)
            q = max(q, previous)  # keep quantiles non-decreasing
            quantiles.append(q)
            previous = q
        rows.append({"hour": hour, "q": quantiles})
    return {"hours": rows}


def main():
    input_dir = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
    output_dir = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))
    inputs = sorted(input_dir.glob("*.in"))
    if not inputs:
        print(f"no .in files in {input_dir}", file=sys.stderr)
        return 1
    output_dir.mkdir(parents=True, exist_ok=True)
    for in_path in inputs:
        case = json.loads(in_path.read_text())
        out_path = output_dir / (in_path.stem + ".out")
        out_path.write_text(json.dumps(forecast(case)) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
