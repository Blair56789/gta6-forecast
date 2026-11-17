#!/usr/bin/env python3
"""Score this repo's forecaster on the four practice cases.

Runs main.py once over the kit's practice inputs (input/p00.in .. p03.in)
and grades each forecast with the competition's own loss: mean pinball
loss on the log scale, 2 * max(tau*d, (tau-1)*d) with d = ln(y) - ln(q),
over all 23 hours x 5 quantile levels. Also prints the median-quantile
miss (as a percentage) and how often the true value lands inside the
5%-95% interval, both informational only.

Ground truth lives in practice_answers.json next to this script: the four
launches' hourly Twitch category averages from SullyGnome.com, the public
source the kit's input/NOTICE.txt names. The answers were checked by
reproducing every practice case's hour-1 print exactly before use.

    python3 evaluation/score.py --kit <path to unpacked kit>

The kit's starter (the house persistence baseline) can be scored the same
way with --program <kit>/starter/main.py; its practice loss is 0.3871.
"""

import argparse
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

TAUS = [0.05, 0.25, 0.5, 0.75, 0.95]
ZS = [-1.645, -0.674, 0.0, 0.674, 1.645]
BASELINE = 0.3871
TITLES = {
    "p00": "Marvel's Wolverine",
    "p01": "Red Dead Redemption 2",
    "p02": "God of War Ragnarok",
    "p03": "Marvel's Spider-Man 2",
}


def grade_one(out_file, truth):
    """Return (pinball loss, typical miss %, 90% coverage) for one case."""
    forecast = json.loads(Path(out_file).read_text())
    assert set(forecast) == {"hours"} and len(forecast["hours"]) == 23
    pinballs, log_misses, inside = [], [], 0
    for row in forecast["hours"]:
        hour, quantiles = row["hour"], row["q"]
        assert len(quantiles) == 5 and all(
            quantiles[i] <= quantiles[i + 1] for i in range(4)
        )
        y = truth[str(hour)]
        log_y = math.log(max(y, 1))
        for tau, q in zip(TAUS, quantiles):
            d = log_y - math.log(max(q, 1e-9))
            pinballs.append(2 * max(tau * d, (tau - 1) * d))
        log_misses.append(abs(log_y - math.log(quantiles[2])))
        inside += quantiles[0] <= y <= quantiles[4]
    n = len(forecast["hours"])
    return (
        sum(pinballs) / len(pinballs),
        100 * (math.exp(sum(log_misses) / n) - 1),
        inside / n,
    )


def main():
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--kit", required=True)
    parser.add_argument("--program", default=str(root / "main.py"))
    args = parser.parse_args()

    truth = json.loads(
        (root / "evaluation" / "practice_answers.json").read_text()
    )
    with tempfile.TemporaryDirectory() as tmp:
        outdir = Path(tmp) / "out"
        outdir.mkdir()
        env = dict(__import__("os").environ)
        env["MAKEFUN_INPUT_DIR"] = str(Path(args.kit) / "input")
        env["MAKEFUN_OUTPUT_DIR"] = str(outdir)
        subprocess.run(
            [sys.executable, "-P", "-s", args.program],
            env=env, check=True, capture_output=True, text=True,
        )
        print(f"{'case':28s} {'loss':>7s} {'miss':>7s} {'cov90':>6s}")
        losses = []
        for pid in ["p00", "p01", "p02", "p03"]:
            loss, miss, cov = grade_one(outdir / f"{pid}.out", truth[pid])
            losses.append(loss)
            print(f"{TITLES[pid]:28s} {loss:7.4f} {miss:6.1f}% {cov:6.3f}")
        mean = sum(losses) / len(losses)
        print(f"{'MEAN':28s} {mean:7.4f}")
        print(f"house baseline: {BASELINE}  ->  {(1 - mean / BASELINE) * 100:.1f}% lower")
        return 0 if mean < BASELINE else 1


if __name__ == "__main__":
    raise SystemExit(main())
