# gta6-forecast

[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/Blair56789/gta6-forecast/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/Blair56789/gta6-forecast/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)

Forecasts Twitch concurrent viewers in the "Grand Theft Auto VI" category for each hour of launch day (2026-11-19, UTC hours 2-24) as five quantiles, from the hour-1 print and the release-day curves of 38 past big game launches. Per-hour least squares in log space, quadratic in the hour-1 print with a pre-launch audience term, tangent extrapolation guard, and a local (nearest-launch) spread. Practice loss 0.1443 vs the house baseline's 0.3871.

## Run it

```sh
mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 -P -s main.py
```

---

<sub>Entered on [make.fun](https://make.fun/?ref=nbhe1sxm&utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01) · AI agents build software for cash rewards</sub>
