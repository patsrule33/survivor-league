# Survivor Fantasy League

A free, static site for a family Survivor fantasy league: leaderboard, results by elimination or episode, contestant scoring, all-time stats, and a draft room. Scores come from the [survivoR](https://github.com/doehm/survivoR) dataset.

## Updating scores

This happens automatically. The **Update scores** GitHub Action (`.github/workflows/update-scores.yml`) runs every day at 15:00 UTC. It re-downloads survivoR, pulls any finished draft, rescores **only the season now airing** (`--current`), and commits `docs/data/` only if something changed. Then it asks GitHub Pages to republish. Past seasons are finished and aren't touched.

- **Run it now:** Actions tab → **Update scores** → **Run workflow**.
- **By hand:** `python build_site.py --refresh --current`, then commit and push.
- **Finished seasons are frozen.** They are never rescored, so changing the scoring rules only affects seasons from then on.

**Test drafts:** check "Test draft" when starting a draft to try things out with made-up rosters. The season shows on the site labelled "(test)", never counts toward All time, and deleting the draft (Commissioner tools) removes it everywhere at the next update, even after the season is over.

The site is plain files in `docs/`, served by GitHub Pages (Settings → Pages → `main` branch, `/docs` folder).

GitHub pauses scheduled workflows after 60 days with no commits to the repo, which can happen in the off-season. If it does, GitHub emails you; re-enable it from the Actions tab.

## Draft room setup (one time)

1. Create a project at https://console.firebase.google.com (no billing needed).
2. **Build → Firestore Database → Create database** (production mode, any region).
3. **Firestore → Rules**: paste the contents of `firestore.rules` and publish.
4. **Project settings → Your apps → Web app (`</>`)**: register an app, copy the `firebaseConfig` object, and paste it into `docs/firebase-config.js` as `window.FIREBASE_CONFIG = { ... };`.
5. Commit and push. The **Draft** tab now shares picks with everyone.

Until step 4 is done, the Draft tab runs in test mode (picks stay in your browser).

## Files

| Path | What |
|---|---|
| `scoring.py` | The scoring engine (league rules) |
| `survivor_data.py` | survivoR → season data the engine scores |
| `build_site.py` | Scores everything and writes the site data |
| `sync_draft.py` | Finished draft → `leagues/seasonNN.json` |
| `leagues/` | Rosters per season |
| `overrides/` | Commissioner decisions (review items, corrections) |
| `history/official_totals.json` | Official past results used for all-time stats |
| `docs/` | The website |
