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


def fetch_state(pid, season):
    url = f"https://firestore.googleapis.com/v1/projects/{pid}/databases/(default)/documents/drafts/s{season}"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            doc = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    return json.loads(doc["fields"]["state"]["stringValue"])


def to_league(state):
    rosters = {o: [] for o in state["owners"]}
    for p in state["picks"]:
        rosters[p["owner"]].append(p["name"])
    return {"season": state["season"], "league": "Family League", "first_week_boot": state["startBoot"],
            "source": "draft room", "drafted_at": state.get("createdAt"),
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
    if not seasons:
        seasons = [live["season"]] if live else []
    written = []
    for n in seasons:
        state = fetch_state(pid, n)
        if not state:
            if verbose: print(f"sync_draft: no draft for S{n}")
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
