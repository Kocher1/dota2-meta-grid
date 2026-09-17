# Method and evidence

All tests below were run on 2026-09-17 on Dota2ProTracker data for Sep 10-17
(patch 7.41e -> 7.41f on Sep 15) and OpenDota's 7-day bracket statistics.
"Backtest" = train on 3 of the 5 clean 7.41e days, test on the other 2, all 10 splits x 5 roles;
the score is the realized out-of-sample win-rate edge of the top-7 heroes per role.

## Scoring

    score(hero, role) = shrunk role win-rate edge in 6500+ MMR pubs
                      + personal tie-breaker (0.25 x your shrunk lifetime edge, max +-1.5pp)

    eligible if  the hero fills >= 0.3% of the role's slots
            and  its all-role win rate in YOUR OpenDota bracket is >= 49%   (the veto)
            and  you have not said you won't play it there

* **Shrinkage**: an empirical-Bayes beta prior per role, fitted by the method of moments
  (variance of observed win rates minus mean sampling variance). True between-hero spread is
  only about 1.6-3.3pp depending on role, so a 60% win rate over 130 games becomes about 52%.
* **Patch handling**: post-patch games come from the site's patch table (filtered by game
  version). While the patch is younger than the 8-day window, pre-patch games (8-day totals
  minus patch totals) form the prior; it is widened by the expected patch drift
  (tau = 2.4pp for heroes the patch touched, ~0 for the rest) and updated with post-patch games.
* **Veto**: the only place the player's own rank enters. It removes heroes that are strong at
  6500+ but losing in the player's bracket (e.g. Monkey King or Naga Siren at Ancient).

## What was tested

| Assumption | Test | Verdict |
|---|---|---|
| Shrunk win rate ranks better than raw win rate | Backtest: shrunk +2.88pp, raw (n>=50) +2.20, raw (n>=200) +2.69, Wilson lower bound +2.37. Prediction RMSE 2.62 vs 2.82pp | confirmed |
| Low-pick heroes should be cut at 1% of role slots | A 1% floor *lowers* the realized edge to +2.25pp; 0.3% is the best floor tested (+3.11pp) | rejected -> 0.3% floor |
| Niche picks' edge is fake | Cores: realized >= predicted (mid niche picks: predicted +5.1pp, realized +6.6pp). Supports: about -0.6pp on small samples | real for cores, no evidence for supports; whether it transfers to a non-specialist cannot be tested -> the player is asked |
| The prior mean should depend on pick rate | Regression prior: +2.89 vs +2.88pp | no gain, dropped |
| Model is calibrated | Predicted vs realized edge of selected heroes agree within ~0.5pp in core roles | confirmed |
| Heroes drift across a letter patch | Pre vs post win rates, 172 hero-roles: heroes the patch touched drift with SD 2.4pp beyond sampling noise; untouched heroes show no drift beyond noise | tau = 2.4pp / ~0 |
| 6500+ statistics transfer to lower ranks | Noise-corrected correlation with OpenDota bracket win rates: Divine 0.93, Ancient 0.75, Legend 0.58, Archon 0.46, Crusader 0.33, Guardian 0.23, Herald 0.13 | only partly - see limits |
| Bracket trends can be extrapolated | A hero's MMR gradient inside 6500+ vs its Divine-minus-Ancient gradient: r = 0.14 | rejected -> plain veto, no extrapolation |

A data-quality trap, for anyone extending this: the 8-day table carries per-day rows, but
across a patch boundary they disagree with the site's own patch table (only 67 of 119
hero-roles within 15% for the same two days) while independent OpenDota trends agree with the
patch table. The per-day rows are therefore not used for the pre/post split. They were used
for the backtests above, which only split pre-patch days against each other.

## Expected gain
Out of sample at 6500+ MMR: top-1 pick +5.2pp, top-3 +4.1pp, top-7 +2.9pp over an average
hero in the role.

## Known limits
* **Built for Ancient and above.** The role statistics are 6500+ MMR games. About 74% of such
  an edge carries over at Ancient, 57% at Legend, under half at Archon and below. The veto
  removes the worst mismatches but does not re-rank the list for low brackets. No open source
  publishes win rates by role *and* bracket; with one, this would be the first thing to fix.
* tau and the transfer figures were measured on one week around one patch.
* OpenDota has no Immortal bucket (no veto there) and no role split (the veto is all-role).
  Its window is the last 7 days, so right after a patch the veto still reflects the old one.
* Role detection is Dota2ProTracker's (it reports ~0.4% invalid-position player games).
* It is unverified whether `stats.dat` lifetime standings include unranked or turbo games;
  the personal term is capped at +-1.5pp partly for that reason. In flat roles (supports) it
  can still reorder near-tied heroes - it is a tie-breaker, not evidence.
* Statistics describe the hero population, not drafts: counters, synergies and lane matchups
  are ignored.
