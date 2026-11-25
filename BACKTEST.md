# Backtests: scoring engine vs. your spreadsheets

Engine: `scoring.py`. Ground truth: `truth47.json` and `truth46.json`, parsed from the owner's workbooks.

Rule rulings from 2026-11-25 are applied (see CLAUDE.md):
- The tie/revote −1 applies.
- Revote switchers get +1 instead of +2.
- Merged split-group challenges pay the winning team reward.
- Sitting out a challenge your side wins still pays.

The sheets predate these rulings, so differences from them are expected.

## Season 47

Run: `python backtest.py fixtures/survivoR_season47.json truth47.json`, built by `survivor_data.py` with `overrides/season47.json`.

The hand-transcribed `fixtures/season47.json` (from `build_s47.py`) gives identical contestant totals.

**Result:** 705 of 720 cells (contestant × week × category) match. The owner ranking is unchanged (Jamie, Mom, Will, Greg, Jimmy).

| Owner | Engine | Sheet |
|---|---|---|
| Jamie | 366 | 363 |
| Mom | 206 | 212 |
| Will | 120 | 124 |
| Greg | 105 | 105 |
| Jimmy | 43 | 39 |

| Week | Contestant | Category | Engine | Sheet | Cause |
|---|---|---|---|---|---|
| 5 | Sierra | votes | -5 | -4 | Tie then revote: the eliminated player loses 1 more (ruling). |
| 5 | Sol, Andy, Genevieve, Teeny | votes | +1 | +2 | Switched to Sierra on the revote (ruling: +1). |
| 4 | Sam, Andy, Sierra, Sol | challenges | 3 | 0 | Split-group challenge: the winning team gets reward points (ruling). |
| 4 | Genevieve, Teeny | challenges | 3 | 6 | Same challenge. The sheet paid them immunity; survivoR and Wikipedia say reward. |
| 5 | Rachel | votes | 0 | +2 | Rachel played the Shot in the Dark and gave up her vote. The sheet gave alliance credit. |
| 6 | Caroline | votes | 0 | +2 | Caroline had lost her vote. The sheet gave alliance credit. |
| 11 | Teeny | votes | 0 | +2 | Teeny voted for Sam (the backup vote), not Genevieve. The sheet gave alliance credit. |
| 12 | Sam | votes | +2 | 0 | Kyle's jury vote went to Sam. The sheet missed it. |

Overrides used:
- "Advantage used" for Rome's vote steal and Sol's Safety without Power.
- Episode 9 reward winners (Gabe, Kyle, Sol, Teeny), which survivoR is missing.

## Season 46

Run: `python backtest.py fixtures/survivoR_season46.json truth46.json --merge 5,6`, built with `overrides/season46.json`.

- Week 1 is Randen's medevac (boot 3).
- The sheet keeps episode 7's two Tribals in one column, hence `--merge`.

**Result:** 756 of 768 cells match. The owner comparison is muddied by the S46 waiver wire, so only contestant cells are compared.

| Sheet col | Contestant | Category | Engine | Sheet | Cause |
|---|---|---|---|---|---|
| 7 | Hunter | votes | -5 | -4 | Tie then revote (ruling). |
| 7 | Venus, Kenzie | votes | +1 | 0 | Switched to Hunter on the revote (ruling: +1). |
| 5 | Liz, Soda, Tevin, Venus, Charlie | challenges | 3 | 0 | Split-group challenge: the winning team gets reward points (ruling). |
| 4 | Venus | votes | 1 | 2 | The sheet missed Charlie's vote against Venus. |
| 5 | Venus | votes | 0 | 2 | The sheet missed the two votes against Venus at Soda's Tribal. |
| 11 | Ben | votes | 1 | 2 | The sheet missed Maria's vote against Ben. |
| 4 | Tiffany | challenges | 4 | 0 | Sat out a challenge her team won. Sitting out still pays (ruling); the sheet missed it. |

## Conventions the sheets were using (confirmed by the backtests)

- A "week" is one elimination. The S47 sheet split its double-Tribal episode into two columns; the S46 sheet kept its double-Tribal episode in one column but still counted both rungs of the survival ladder (5+6).
- Surviving week k = k points. Finalists keep climbing the ladder: 3rd gets k, 2nd gets k+(k+1), 1st gets k+(k+1)+(k+2).
- A combined Reward/Immunity challenge pays only the immunity points. Separate reward challenges pay reward points.
- Votes cancelled by an idol are not counted against the idol holder.
- A vote steal counts as two ballots for the stealer, and the stolen voter gets nothing.
- Idol found +10 counts at the full "Found" (not a "beware" idol's partial find). Being voted out holding an idol is −20. A medevac gets +5 pity points.

## Caveat on the special points

"Other advantage used" isn't machine-decidable. survivoR lists every advantage event, and `survivor_data.py` puts the non-idol ones on a review list. Which of them counted (Rome's and Sol's in S47; not Maria's Extra Vote in S46) was decided with the sheet in view, so the match on specials isn't an independent test. The idol finds, idol plays and idol-in-pocket penalties are detected automatically, and they all match.
