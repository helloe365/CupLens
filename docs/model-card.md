# CupLens Elo–Poisson v1 Model Card

## Purpose

`elo-poisson-v1` produces deterministic pre-match football score and outcome
probabilities for CupLens. It is a baseline forecasting model, not a betting or
financial decision system.

## Data and cutoffs

The development dataset is the public international-results CSV at
`https://raw.githubusercontent.com/martj42/international_results/master/results.csv`.
The fixed local file contains 49,509 rows and has SHA-256
`e9e417298abc881bac63f1d89722982e30881788ee59a77b761c2d7c2284d2cf`.
It was retrieved at `2026-07-14T03:25:41+00:00`.

Every fit and prediction filters matches with the strict rule
`date < cutoff_at`. The baseline splits are:

- 2018 features: before `2018-06-13T23:59:59.999999+00:00`; test set:
  64 FIFA World Cup matches beginning 2018-06-14.
- 2022 features: before `2022-11-19T23:59:59.999999+00:00`; test set:
  64 FIFA World Cup matches beginning 2022-11-20.

There is no random train/test split and no test-tournament match is added to
the features during either baseline evaluation.

## Method

Elo starts each observed team at 1500. Its expected score is
`1 / (1 + 10 ** ((rating_b - rating_a) / 400))`. The base K is 20, with
competition importance weights 0.5 for friendlies, 1.0 for qualifiers and
other matches, 1.25 for continental finals, and 1.5 for the FIFA World Cup.
Match influence decays with a three-year half-life.

For each team, the Poisson model uses its most recent 20 pre-cutoff matches.
Goals for and against use the same three-year time decay and shrink toward the
global single-team goals-per-match mean with five equivalent matches:

```text
attack  = ((weighted_goals_for     + 5 * mu) / (weighted_games + 5)) / mu
defense = ((weighted_goals_against + 5 * mu) / (weighted_games + 5)) / mu
```

Expected goals are:

```text
lambda_a = mu * attack_a * defense_b * exp(0.25 * (elo_a - elo_b) / 400)
lambda_b = mu * attack_b * defense_a * exp(0.25 * (elo_b - elo_a) / 400)
```

Each lambda is limited to `[0.2, 3.5]`. Independent Poisson probabilities are
enumerated for scores 0–7 and the resulting 8×8 matrix is normalized to one.
The matrix yields home win, draw, away win, and the three most probable scores.

For knockout presentation, the home-team advancement approximation is
`P(home win in the score matrix) + P(draw) * logisticElo(home, away)`. This is
an approximation, not an exact extra-time or penalty-shootout model.

## Baseline results

The three-class Brier score is the mean, over matches, of the sum of squared
errors against a one-hot home-win/draw/away-win target. Log Loss clips the
probability assigned to the observed class to `[1e-6, 1-1e-6]`. Accuracy is the
argmax class accuracy.

| Test year | Matches | Accuracy | Brier score | Log Loss |
| --- | ---: | ---: | ---: | ---: |
| 2018 | 64 | 0.578125000000 | 0.590071407536 | 0.988389145848 |
| 2022 | 64 | 0.437500000000 | 0.613694152615 | 1.031319073481 |

These are uncalibrated baseline measurements without a competing-model
comparison. They do not establish superiority or production accuracy.

## Dixon–Coles experiment

Enhancement 1 tested the standard Dixon–Coles low-score factors for 0–0, 1–0,
0–1, and 1–1. All other score factors remain one, and the corrected 0–7 matrix
is normalized before deriving home-win, draw, and away-win probabilities.

For each test tournament, `rho` was selected from `[-0.15, 0.15]` in 0.01
increments using only the latest completed World Cup before the test year. The
2018 evaluation used the 2014 World Cup to select `rho=0.01`; the 2022
evaluation used the 2018 World Cup to select `rho=0.15`. Each calibration
tournament's expected goals were computed from data strictly before that
calibration tournament began. No 2018 or 2022 test result was used to select
the corresponding `rho`.

Positive relative change below means lower loss than the P0 baseline.

| Test year | P0 Brier | Dixon–Coles Brier | Relative change | P0 Log Loss | Dixon–Coles Log Loss | Relative change |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2018 | 0.590071407536 | 0.589546906693 | +0.088888% | 0.988389145848 | 0.987626942970 | +0.077116% |
| 2022 | 0.613694152615 | 0.611918186761 | +0.289389% | 1.031319073481 | 1.028339099208 | +0.288948% |

Both metrics improved slightly in both test years, but no metric improved by
the required 1%. The experiment did not meet the original enhancement gate.
It is now available through `MODEL_VARIANT=dixon-coles` under the user's
explicit instruction to enable every implemented variant despite the
sub-threshold improvement. The 2022 value is
also at the upper edge of the predefined grid, so it must not be interpreted
as a stable optimum or used as justification to widen the grid after seeing
test results.

## LightGBM meta-model experiment

Enhancement 2 trained a deterministic, single-threaded LightGBM 4.6.0
three-class model and blended its probabilities with the P0 Elo–Poisson
probabilities. The experiment used only these pre-match features:

- Elo difference;
- P0 home-win, draw, and away-win probabilities;
- attack-strength and defense-strength differences;
- recent-five-match form difference;
- neutral-venue flag;
- rest-days difference.

For every World Cup row, features were frozen one microsecond before that
tournament's first match, so every row satisfies
`feature_cutoff < match_date`. For the 2018 test, 2006 and 2010 were training
tournaments and 2014 was the validation tournament. For the 2022 test, 2006,
2010, and 2014 were training tournaments and 2018 was the validation
tournament. The blend weight grid was selected only on the validation
tournament; test outcomes were not available to feature generation, model
training, or blend selection.

| Test year | Blend weight | P0 Brier | LightGBM Brier | Relative change | P0 Log Loss | LightGBM Log Loss | Relative change |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2018 | 0.00 | 0.590071407536 | 0.590071407536 | 0.000000% | 0.988389145848 | 0.988389145848 | 0.000000% |
| 2022 | 0.00 | 0.613694152615 | 0.613694152615 | 0.000000% | 1.031319073481 | 1.031319073481 | 0.000000% |

Both validation periods selected a zero LightGBM weight, so the test output is
exactly the P0 baseline. The experiment failed the original 1% improvement
gate. It is now available through `MODEL_VARIANT=lightgbm-meta` under the
user's explicit override. The validated blend weight remains `0.0`, production
performs no runtime training, and the `lightgbm` package is installed so the
implemented module remains available. On the
development machine, the complete 2018/2022 experiment took
12.96 seconds, used approximately 165 MiB peak resident memory, and used no
swap.

## Dixon–Coles + LightGBM combination experiment

The combination experiment replaced all three Poisson probability features
and the final blend baseline with Dixon–Coles-corrected probabilities. Each
tournament used only the latest earlier World Cup to select `rho`: 2006 used
2002 (`rho=0.08`), 2010 used 2006 (`rho=-0.06`), 2014 used 2010 (`rho=0.12`),
2018 used 2014 (`rho=0.01`), and 2022 used 2018 (`rho=0.15`). LightGBM retained
the same features, hyperparameters, deterministic seed, chronological training
windows, validation tournament, and blend-weight grid as the standalone meta
experiment.

| Variant | 2018 Brier | 2018 Log Loss | 2022 Brier | 2022 Log Loss | Pooled Brier | Pooled Log Loss |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| P0 Elo–Poisson | 0.590071407536 | 0.988389145848 | 0.613694152615 | 1.031319073481 | 0.601882780076 | 1.009854109665 |
| Dixon–Coles | 0.589546906693 | 0.987626942970 | 0.611918186761 | 1.028339099208 | 0.600732546727 | 1.007983021089 |
| LightGBM meta | 0.590071407536 | 0.988389145848 | 0.613694152615 | 1.031319073481 | 0.601882780076 | 1.009854109665 |
| Dixon–Coles + LightGBM | 0.589546906693 | 0.987626942970 | 0.611918186761 | 1.028339099208 | 0.600732546727 | 1.007983021089 |

Both validation tournaments selected a LightGBM blend weight of `0.0` for the
combined variant. The combined output is therefore exactly the standalone
Dixon–Coles output and receives no incremental gain from LightGBM. Relative to
P0, pooled Brier improves by `0.191106%` and pooled Log Loss improves by
`0.185283%`; neither reaches the required 1%. Although neither loss regresses
in either test year, the combination failed the original activation threshold.
Under the user's explicit override, `dixon-coles-lightgbm-meta` is now the
default for newly generated snapshots. Because the validated LightGBM weight
is `0.0`, its current output is exactly the Dixon-Coles output. Existing
immutable snapshots are unchanged.

## Atomic result updater decision

Enhancement 3 started after the two prior enhancements had explicit decisions.
The public-health check was skipped only under the user's explicit exception;
the local P0 service remained healthy and the time gate had more than two hours
remaining. The two completed manual-update records were:

- `20260714-pre-semifinals-v1`, committed as `9aac497` on 2026-07-14;
- `20260715-post-france-spain-v1`, committed as `812ba40` on 2026-07-15.

Before implementation, the current results SHA-256 was
`030403282c36ad6950fb174167c1f905278259118a14f45a009caa0c105bfc03`,
the snapshot-index SHA-256 was
`fe50a27be22210a4f7891463af362c84e3a8feb11f47eda5f275a74d11e84d6f`,
and the last valid snapshot SHA-256 was
`102d5fbf81bbfa2106dc2566d7b1b04843c50433c7af7f6dcc445042579999a8`.

The implemented updater accepts only a curated JSON bundle containing the full
knockout result document and full source manifest. It downloads into a
temporary directory, preserves prior source history, requires matching
official and secondary hashes, permits only newly verified
`scheduled -> finished` transitions, validates and builds the snapshot in a
temporary project, and then commits the data, source manifest, immutable
snapshot, and index. A commit-time exception rolls every attempted replacement
back and removes the new snapshot.

The safety gate passed 18 focused tests, including invalid IDs, team and time
drift, reverse transitions, score rewrites, missing/conflicting/unverified
sources, interrupted download, validation failure, duplicate snapshot ID,
post-write commit failure, dry-run, and default-off behavior. The implementation
is retained, but operational activation is not approved yet: no real verified
bundle URL is configured and no live `scheduled -> finished` candidate was
available for an enabled end-to-end dry-run before the next match. Therefore
`AUTO_UPDATE_ENABLED=false` remains the default and manual verification remains
mandatory before any formal snapshot or submission.

## Limitations

- Scores are modeled as conditionally independent; there is no Dixon–Coles
  correction in this baseline.
- The historical results file does not reliably separate 90-minute scores from
  scores after extra time. Some knockout backtest labels may therefore reflect
  extra-time outcomes, while the displayed score matrix is described as a
  90-minute approximation.
- Penalty shootouts, lineups, injuries, suspensions, travel, weather, news, and
  player-level information are not modeled.
- There is no explicit home-field or neutral-venue adjustment.
- The three-year decay, 20-match window, five-match shrinkage, Elo factor, and
  lambda limits are fixed design choices, not tuned claims of optimality.
- Top scores omit outcomes above seven goals after matrix normalization.
- Predictions are uncertain estimates and must not be presented as facts or
  used as betting advice.
