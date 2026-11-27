# Survivor Fantasy League

Family fantasy league for the TV show Survivor. Goal: replace a hand-built spreadsheet with a free, automated site (no domain, no ongoing cost) with a live draft room, leaderboard and week-by-week scoring.

## Status
- DONE: scoring engine (`scoring.py`), Season 47 fixture (`fixtures/season47.json`, built by `build_s47.py`), backtest (`backtest.py`) against the owner's spreadsheet. Run `python backtest.py fixtures/season47.json truth47.json`. 715/720 cells match; owner ranking identical. See `BACKTEST.md`.
- DONE: survivoR converter (`survivor_data.py`). It builds the season JSON straight from survivoR, with owner decisions layered on from `overrides/seasonNN.json`.
  - S47: `python survivor_data.py 47 --first-week-boot 4 --overrides overrides/season47.json`, then `python backtest.py fixtures/survivoR_season47.json truth47.json`. 705/720, with contestant totals identical to the hand fixture.
  - S46: `python survivor_data.py 46 --first-week-boot 3 --overrides overrides/season46.json`, then `python backtest.py fixtures/survivoR_season46.json truth46.json --merge 5,6`. 755/768.
  - Since the 2026-11-25 rule rulings, every difference in both seasons is a deliberate rule change or a sheet error (see `BACKTEST.md`). The S47 owner ranking is unchanged.
- DONE: static site in `docs/` (GitHub Pages can serve `/docs` straight from the main branch, no build step).
  - `python build_site.py` scores every `leagues/seasonNN.json` and writes `docs/data/seasonNN.json` + `docs/data/index.json`.
  - Owner colors are fixed per person across all seasons (`OWNER_SLOTS` in `build_site.py`).
  - Views: All time (career table, points-over-time chart, season-by-season table, "Since S45" filter), Leaderboard (standings, roster chips, cumulative race chart), Results (owner grid, what happened, contestant scoring), Contestants (sortable by total, finish, name, owner; total ties break by finish).
  - UI terminology: the code's "week" is an **elimination** in the UI.
  - An Elimination/Episode toggle (remembered in localStorage) regroups every view. Episode mode sums a double-elimination episode into one column, and its Results page lists the eliminations in order.
  - Hash routes: `#/47/results/elim/5`, `#/47/results/ep/13`. Old `#/47/weeks/5` links still work.
  - Plain HTML/JS/CSS, no libraries. Owner colors follow the league-file order (slot 1-5), never rank.
  - Bump `?v=` on `app.js`/`style.css` in `index.html` after editing them, so browsers don't serve stale copies.
  - Never rewrite source files through Windows PowerShell `Get-Content`/`WriteAllText`. PowerShell 5.1 reads UTF-8 as cp1252 and garbles `…`, `·`, `—`, emoji (this happened to `draft.js` on 2026-11-25). Use the Edit tool.
  - Local preview: `python -m http.server 8047 --directory docs`.
- DONE: past seasons S28–S50 imported from the owner's workbooks (`python import_sheets.py`; needs `openpyxl`) plus an All time (career) tab.
  - Rosters come from the score sheet's owner column when the sheet has scores, otherwise from the draft table. S48's draft table is shifted in the workbook.
  - `first_week_boot` was auto-detected, then calibrated against each score sheet.
  - S49 has double picks (one contestant on two rosters; both owners score them).
- **Finished seasons are frozen. Never rescore them** (owner, 2026-11-25). Scoring-rule changes apply to future seasons only. `build_site.py` skips any season whose `docs/data/seasonNN.json` says `complete`, even with no flags. Don't work around this.
- **Test drafts:** a "Test draft" checkbox in the draft room sets `test` on the draft, which carries into the league file and season data.
  - Test seasons show on the site labelled "(test)", never count in career stats, and aren't the default landing season.
  - Deleting the draft in Firestore makes `sync_draft.py` remove the league file, site data and fixture, even after the season ends.
  - The owner plans an S51 test draft for the rest of this season.
- Past seasons' results stay **official exactly as the owner calculated them**; never "correct" them. Recalculated past seasons exist only as test cases to check the engine is right going forward (owner, 2026-11-25).
- Career stats count the career sheet's **official** totals and winners through S47 (`OFFICIAL_THROUGH` in `build_site.py`) and recalculated totals from S48 on (owner decision 2026-11-25).
  - Recalculated flips vs the official winners (as of 2026-11-25):
    - S40: Greg 676 vs Mom 664 (official Mom 686, Greg 678). Close; S40 is Edge of Extinction.
    - S44: Mom 276 vs Greg 270. The sheet missed Matthew's idol find (ep 3) and his medevac pity, worth +15.
  - S36 now matches. Old season pages show an "Official final result" banner above the recalculated detail.
  - Recalculated seasons that track the sheets well: 32, 34–37, 42, 46, 47. Drift comes from early rule differences (S28 counted survival only), Edge of Extinction (S40), and partial sheets (S48–49).
- **Excluded owner:** one former participant is excluded everywhere. Their name lives only in git-ignored `private/excluded_owners.txt`, read by `import_sheets.py`, which refuses to run without it. Never write the name into a tracked file (the repo is public). Their picks are unowned, and their name must never appear in any output, career stat or page. The career sheet already omits them. (The S41 contestant with the same first name is a different person and is fine.)
- DONE: draft room (Draft tab; `docs/draft.js`).
  - Randomized snake order, no clock. The pool = whoever is in the game when the draft starts (`docs/data/live.json`, written by `build_site.py` for the newest survivoR season). Roster size = pool ÷ owners; leftovers are unowned.
  - Only the owner on the clock sees Draft buttons. Commissioner tools allow undo and delete. There's a "copy your-turn message" button.
  - Shared state: one Firestore doc `drafts/sNN` (field `state` = JSON), with transactions; rules are in `firestore.rules`. Without `docs/firebase-config.js` it runs in test mode (localStorage).
  - `sync_draft.py` (run by `build_site.py`) turns a complete draft into `leagues/seasonNN.json` with `first_week_boot` = the elimination after the draft started.
  - Picked players voted out mid-draft stay on the roster; unpicked ones leave the pool. Waivers are not built yet.
  - survivoR can lag an episode or more, so the draft room lets you mark contestants eliminated: "Already out" before starting (shrinks the pool and roster size, and moves `startBoot` past them) or Commissioner tools during the draft (state `out`). Practice mode (`?practice`) never touches Firestore.
- Footer shows survivoR's last update (`docs/data/meta.json`, from the GitHub API's last commit to `dev/json`). Python on this PC needs `certifi` (installed) to verify api.github.com.
- Repo: github.com/patsrule33/survivor-league (public). `.gitignore` keeps `reference/`, `truth*.json`, `private/` and `data/` out. GitHub Pages serves `docs/`.
- DONE: Firebase project `patsrule33-survivor-league` (config in `docs/firebase-config.js`, rules published).
- DONE: daily GitHub Action `.github/workflows/update-scores.yml`.
  - Runs at 15:00 UTC, by hand (workflow_dispatch), or when the workflow file changes: `build_site.py --refresh --current` (only the newest survivoR season; past seasons are frozen and rebuilt by hand with no flags only after a rules change), then commits `docs/data`, `leagues` and `fixtures` only if they changed.
  - It then POSTs `/pages/builds`, because Actions pushes don't trigger a Pages rebuild.
  - `build_site.py` keeps timestamps unchanged when the data is unchanged (`keep_stamp`), so no-op runs commit nothing.
  - The commit and republish path hasn't run yet; it first will when survivoR next updates.
- DONE: scoring review screen (Review tab; `docs/review.js`).
  - Lists the season's judgment calls from `docs/data/seasonNN.json` → `review`. Each item has a stable `id` (`<advantage_id>:<event>`) and a `kind` (`REVIEW_KINDS` in survivor_data.py: advantage_played, shared_idol_found, handed_out_idol, idol_never_active). Undecided items score nothing.
  - Manual adjustments: elimination, contestant, category, points, reason.
  - Saved in Firestore `reviews/sNN` as `{decisions:{id:"award"|"none"}, adjust:[...]}`. `build_site.py` merges it into the overrides via `sync_draft.fetch_review` and saves a copy to `overrides/seasonNN_review.json`, which the daily job commits. The copy is the fallback if Firestore can't be read.
  - Finished seasons show read-only. `?practice` works here too.
  - Firestore rules need the `reviews` section from `firestore.rules`; the owner publishes it in the console.
  - `docs/store.js` (SFLStore) is the shared storage for the draft and review pages.
- DONE: commissioner-only tools (2026-11-26).
  - The commissioner signs in with Google (footer link; `SFLAuth` in `docs/store.js`). `window.COMMISSIONER_UID` in `docs/firebase-config.js` and the uid in `firestore.rules` must match: `9iaNj5YudyYR6b4rZcuOzKhpyRo2` (a Firebase user ID, not an email).
  - The commissioner alone can start, mark eliminated, undo or delete a draft and edit the review.
  - Drafts are stored as native Firestore fields (`picks`, `taken`, `snake` = full pick order written at start) so the rules can let anyone else add exactly one in-turn pick from the pool and nothing more.
  - Rules use only `get()`/`hasAll()`/`in`/`keys().hasOnly()`: `diff()`, list slicing and `let` made valid picks fail.
  - `drafts/s999` is a scratch doc anyone may create/delete, for rule tests. Verified 17/17 plus a browser-client pick (accepted) and undo (refused).
- DONE: Rules tab and Owners tab (`docs/pages.js`).
  - Rules point values come from `docs/data/rules.json` (written from `scoring.RULES` by `build_site.write_rules`). When a ruling changes, update the plain-language text in `pages.js`.
  - Owners: `docs/data/owners.json` from `build_site.write_owners`, rebuilt every run from all non-test season files.
    - Season totals and wins are the career numbers; contestant points are recalculated.
    - "What works" compares picks by an index: 100 = the season's average owned pick, because season lengths differ (S50 scored 21 eliminations).
    - Traits come from survivoR `castaways` (age, returning) and `castaway_details` (gender, MBTI I/E, collar). Race, ethnicity and LGBT fields are deliberately not used.
- Owner said no to: waivers, Wikipedia backup, manual eliminations for scoring, notifications (2026-11-27). Wiki scraper is now a fallback only. No rosters yet for the current season (51).

## League rules (follow the owner's key)
- 5 players, 3 contestants each, snake draft a few episodes into the season. Pool excludes the first three boots.
- A "week" = one Tribal Council (not one episode; a double-tribal episode is two weeks).
- Challenges: tribal reward 1st/2nd = 2/1; tribal immunity 1st/2nd = 4/2; individual reward 3; individual immunity 6; split-group immunity winners 6. A combined Reward/Immunity challenge pays immunity points only.
- Votes:
  - +2 for voting for the person eliminated.
  - On a revote, +2 only if you also voted for them in the first round. Switching to them on the revote gets +1 (owner ruling 2026-11-25).
  - −1 per counted vote against you (first round only; votes cancelled by an idol don't count).
  - On a tie/revote the eliminated player loses 1 more (confirmed 2026-11-25; the old sheets skipped it).
  - +2 per jury vote.
- Split-group challenges after the merge: the winning team gets reward points (owner confirmed 2026-11-25 that the old sheets were wrong to skip them).
- Sitting out a challenge your tribe or team wins still pays (owner ruling 2026-11-25).
- Survival: surviving week k = k points; in the final week finalists keep climbing (3rd k, 2nd k+(k+1), 1st k+(k+1)+(k+2)).
- Specials: idol found 10; idol or other advantage successfully used 5; voted out with idol in pocket -20; medevac pity 5; quitting forfeits all points.
- Scoring is per CONTESTANT; owner totals are the sum over the roster, which keeps waiver moves simple (Season 46 had a waiver wire).
- Source of truth for votes is Wikipedia. The old sheet sometimes gave "alliance" credit to people who didn't vote for the eliminated player; the engine deliberately does not.

## Constraints and decisions
- Hosting: free only. Plan was GitHub Pages (site) + GitHub Actions cron (weekly scoring) + Firebase Spark/Firestore (live draft and rosters, no payment info needed). AWS free plan expires after 6 months, so avoid it.
- No ongoing Claude/API cost: scoring is plain code. Unscorable items (idol finds, odd challenge formats) go to a small manual review screen.
- The sandbox used earlier could not reach Wikipedia, and a text-flattened copy of the voting table drops blank cells, so voter rows misalign. The scraper must parse the page HTML/wikitext (Wikipedia API `action=parse` or `action=raw`) and handle colspan.
- survivoR dataset (github.com/doehm/survivoR, MIT) evaluated 2026-11-25 against S47. Read the JSON directly from `https://raw.githubusercontent.com/doehm/survivoR/master/dev/json/<table>.json` (records format). The survivoR2py R->py converter isn't needed.
  - Votes: all 12 weeks match `fixtures/season47.json` ballot for ballot, and the jury matches too. Week = boot `order` minus 3. `vote_order` 2 = revote. `nullified`, `tie`, and `vote_event`/`vote_event_outcome` (Steal a vote, Lost vote, Shot in the dark, Block a vote, Fire challenge) are explicit. A vote stealer already gets two rows; don't duplicate them.
  - Challenges: winners match the fixture except the split-group week 4 (ep 7). survivoR says 6 people won reward and Kyle won immunity. Pre-merge 1st and 2nd place are both `result="Won"`, so use `order_of_finish`. Challenge ids can differ between challenge_results and challenge_description (S47 ep 6). Ep 1 has bad order_of_finish.
  - Advantages: advantage_movement + advantage_details give Found/Played/Expired per player and episode, plus `success` and `votes_nullified`. That's enough to auto-detect idol finds, plays, and idol-in-pocket. But `success` doesn't match the owner's "advantage used" calls (Rome's steal is "Not needed" but was awarded). Genevieve's challenge advantage and the shared Teeny/Caroline/Andy idol weren't awarded. So keep specials on the review screen and use survivoR to pre-fill them.
  - Medevac/quit: `castaways.result`. Names are short ("Teeny"); key on `castaway_id`.
  - Update lag: S51 episodes landed 1-3 days after airing (single maintainer).
- Python 3.12 is at `C:\Users\gregr\AppData\Local\Programs\Python\Python312\python.exe`. A shell opened before the install may not have it on PATH. No third-party packages needed.

## Known edge cases for the schema
Medical evacuation (no vote), split Tribal Council, open-poll elimination, ties/revotes, lost votes, Shot in the Dark (sacrifices vote), vote steals (two ballots), idol plays that negate votes, final-3 fire-making.

## Converter conventions (`survivor_data.py`)
- Week = elimination event (boot `order`) from `--first-week-boot` on. A medevac or quit is its own week even with no Tribal. The draft timing sets the first week (S47: 4, S46: 3).
- Challenges attach to a week via `n_boots + 1`; advantage events via `boot_mapping` `sog_id -> n_boots + 1`.
- `won_*` flags map to challenge types as follows:
  - Pre-merge "Team" pays tribal rates.
  - Post-merge "Team" reward pays `indiv_reward`; team immunity pays `group_immunity`.
  - The immunity flag wins over the reward flag within the same scope.
  - A challenge that `challenge_description` lists as one "Immunity and Reward" challenge pays immunity only to anyone who won immunity in it, even across scopes (S44 ep 7, S46 ep 7). `challenge_results` sometimes merges two separate challenges under one id (S47 ep 6, Kyle 2+6), so the description decides.
  - Sitting out still pays.
- Owner rulings 2026-11-25:
  - **Split-group immunity** pays only the people who actually won (the overall winner plus anyone "Won (immunity only)"). Teammates made immune keep just the team reward.
  - **Idol play success** = without the idol, the person it was played for would have had the most first-round votes (alone or tied). Simply cancelling votes isn't enough.
  - **Voted out holding an idol that never had power** (a Beware idol whose condition was never met; survivoR shows only "Found (beware)"): no −20 (S41 Brad). An idol survivoR never marks "Expired" counts as live: S45 Bruce −20, as the owner confirmed (the sheet's 0 was a miss).
  - **Voted out holding several idols:** −20 per idol (and +10 per idol found), e.g. S39 Kellee −40 for two. The engine already does this: one survivoR event per idol.
  - **Handed-out idols** (`HANDED_OUT` in survivor_data.py, e.g. S44 summit idols) don't earn the +10 find. Idols the player earned (bought on Edge of Extinction, won at Ghost Island, made from halves) do count.
  - **S44 Matthew** (advised to leave after a medical exam) is a medevac, not a quit. A real quit can still be forced with `forfeit` in an overrides file.
- Edge of Extinction / Redemption Island:
  - Returnees' first boots come from vote_history (castaways keeps only one row per player).
  - Survival skips the weeks a player is listed "Edge of Extinction"/"Redemption Island" in boot_mapping, plus every week they were voted out. Exile Island still earns survival.
  - "voted out; Quit EoE" is not a forfeit.
- Old seasons: `survival_offset` in a league file = survival started that many weeks after scoring began (read from the sheet's survival ladder; e.g. S36 scored from Brendan's boot, with survival a week later). The engine pays week k as k − offset. New seasons don't use it.
- Auto specials: idol `Found` (not "Found (beware)"), idol "Voted out with advantage" (-20), idol `Played` (+5 if `votes_nullified` > 0), medevac pity, quit (`forfeit` list; the engine zeroes those players). Everything else (non-idol advantages, shared idol finds) goes to `review` and is scored only if an override adds it.
- Sitting out a challenge your tribe or team wins still pays (owner ruling 2026-11-25). The S46 sheet's 0 for Tiffany was an error.

## Next steps
1. Put the folder in a GitHub repo and turn on Pages (main branch, `/docs`).
2. Draft room (Firebase) and waivers. These write `leagues/seasonNN.json`-shaped rosters. Waivers will need dated roster spans, since an owner's total is currently the full-season sum of a static roster.
3. GitHub Actions weekly job: `python build_site.py --refresh` and commit `docs/data`.
4. Review screen = edit `overrides/seasonNN.json` (accept/reject `review` items, patch challenges).
4. Draft room (Firebase) and waivers.
5. GitHub Actions weekly job plus review screen.

## Files
`parse_sheet.py` turns an owner workbook into ground-truth JSON (`truth47.json`, `truth46.json`). The two original `.xlsx` files are in `reference/`. `survivor_data.py` caches survivoR tables in `data/survivoR/` (use `--refresh` in-season). `overrides/` holds per-season owner decisions. `leagues/` holds per-season rosters (survivoR short names) and `first_week_boot`. S46/S47 rosters come from the sheets; S46's are end-of-season rosters, ignoring waivers. `fixtures/survivoR_seasonNN.json` is the generated output. `backtest.py` matches names by surname + first name/nickname and takes `--merge A,B` for sheet columns that hold two Tribals.
