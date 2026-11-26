"""Pull finished drafts from the draft room (Firestore) into leagues/seasonNN.json.

    python sync_draft.py          # every season with a draft doc
    python sync_draft.py 51

Reads the Firebase project id from docs/firebase-config.js and fetches
drafts/sNN through Firestore's public REST API (the security rules allow
reads, so no key is needed). Only a complete draft is written, and an existing
league file is replaced only if it came from the draft room. build_site.py runs
this first, so the leaderboard picks up new rosters on its next build.
"""
import json, os, re, sys, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.abspath(__file__))
P = lambda *a: os.path.join(ROOT, *a)


def project_id():
    try:
        text = open(P("docs", "firebase-config.js"), encoding="utf-8").read()
    except FileNotFoundError:
        return None
    m = re.search(r"projectId\s*:\s*[\"']([^\"']+)[\"']", text)
    return m.group(1) if m else None


def fetch_review(season):
    """Review-screen decisions for a season: {"decisions": {...}, "adjust": [...]}.
    Reads Firestore reviews/sNN and saves a copy to overrides/seasonNN_review.json
    (committed, so every decision is on record). If Firestore can't be reached,
    falls back to that copy. Returns None if there's nothing."""
    copy = P("overrides", f"season{season}_review.json")
    pid = project_id()
    if pid:
        try:
            state = fetch_state(pid, season, collection="reviews")
            if state is None:
                if os.path.exists(copy):
                    os.remove(copy)  # review doc deleted: drop the copy too
                return None
            state = {"decisions": state.get("decisions", {}), "adjust": state.get("adjust", [])}
            json.dump(state, open(copy, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
            return state
        except Exception as e:
            print(f"review: couldn't read Firestore for S{season} ({e}); using the saved copy")
    if os.path.exists(copy):
        return json.load(open(copy, encoding="utf-8"))
    return None


def _decode(v):
    """Firestore REST typed value -> plain Python."""
    if "stringValue" in v: return v["stringValue"]
    if "integerValue" in v: return int(v["integerValue"])
    if "doubleValue" in v: return v["doubleValue"]
    if "booleanValue" in v: return v["booleanValue"]
    if "nullValue" in v: return None
    if "timestampValue" in v: return v["timestampValue"]
    if "arrayValue" in v: return [_decode(x) for x in v["arrayValue"].get("values", [])]
    if "mapValue" in v: return {k: _decode(x) for k, x in v["mapValue"].get("fields", {}).items()}
    return None


def fetch_state(pid, season, collection="drafts"):
    url = f"https://firestore.googleapis.com/v1/projects/{pid}/databases/(default)/documents/{collection}/s{season}"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            doc = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    fields = doc.get("fields", {})
    if "state" in fields:  # JSON-string format (reviews, older drafts)
        return json.loads(fields["state"]["stringValue"])
    state = {k: _decode(v) for k, v in fields.items() if k != "updated"}  # native fields (drafts)
    return state


def to_league(state):
    rosters = {o: [] for o in state["owners"]}
    for p in state["picks"]:
        rosters[p["owner"]].append(p["name"])
    return {"season": state["season"], "league": "Family League", "first_week_boot": state["startBoot"],
            "source": "draft room", "test": bool(state.get("test")), "drafted_at": state.get("createdAt"),
            "draft_order": state["owners"],
            "notes": "Written by sync_draft.py from the draft room. Scoring starts with the first elimination after the draft began.",
            "owners": [{"name": o, "roster": r} for o, r in rosters.items()]}


def complete(state, live):
    if len(state["picks"]) >= state["rosterSize"] * len(state["owners"]):
        return True
    in_game = {c["name"] for c in (live or {}).get("cast", []) if c["in_game"]}
    taken = {p["name"] for p in state["picks"]}
    out = set(state.get("out", []))  # marked eliminated in the draft room
    return live is not None and not [n for n in state["pool"] if n not in taken and n in in_game and n not in out]


def sync(seasons=None, verbose=True):
    pid = project_id()
    if not pid:
        if verbose: print("sync_draft: no Firebase config yet; skipping")
        return []
    live = None
    if os.path.exists(P("docs", "data", "live.json")):
        live = json.load(open(P("docs", "data", "live.json"), encoding="utf-8"))
    # test drafts from earlier seasons too, so deleting one later still cleans up
    test_seasons = []
    for f in os.listdir(P("leagues")):
        lg = json.load(open(P("leagues", f)))
        if lg.get("source") == "draft room" and lg.get("test"):
            test_seasons.append(lg["season"])
    if not seasons:
        seasons = sorted({*( [live["season"]] if live else []), *test_seasons})
    written = []
    for n in seasons:
        state = fetch_state(pid, n)
        if not state:
            if n in test_seasons:  # test draft was deleted: remove everything it produced
                for path in (P("leagues", f"season{n}.json"), P("docs", "data", f"season{n}.json"),
                             P("fixtures", f"survivoR_season{n}.json")):
                    if os.path.exists(path):
                        os.remove(path)
                if verbose: print(f"sync_draft: S{n} test draft was deleted; removed its rosters and site data")
            elif verbose:
                print(f"sync_draft: no draft for S{n}")
            continue
        if not complete(state, live):
            if verbose: print(f"sync_draft: S{n} draft in progress ({len(state['picks'])} picks)")
            continue
        path = P("leagues", f"season{n}.json")
        if os.path.exists(path) and json.load(open(path)).get("source") != "draft room":
            if verbose: print(f"sync_draft: {path} wasn't made by the draft room; leaving it alone")
            continue
        json.dump(to_league(state), open(path, "w"), indent=1)
        written.append(n)
        if verbose: print(f"sync_draft: wrote {path}")
    return written


if __name__ == "__main__":
    sync([int(a) for a in sys.argv[1:]] or None)
