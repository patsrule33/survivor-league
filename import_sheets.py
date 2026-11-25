"""One-time importer: the owner's old league workbooks -> league files + ground truth.

    python import_sheets.py            # every workbook in reference/
    python import_sheets.py 32 45      # just these seasons

For each "Season NN ... .xlsx" in reference/:
  leagues/seasonNN.json   rosters from the workbook's DRAFT table, matched to
                          survivoR short names; first_week_boot = boot order of
                          the first drafted contestant to go out
  truthNN.json            the Week-By-Week Scoresheet (seasons 32+), if it has scores
And "Survivor Career Stats.xlsx" -> history/official_totals.json.

Excluded owners (EXCLUDED_OWNERS) are dropped everywhere: their picks become
unowned and their name is never written to any output.
"""
import glob, json, os, re, sys, unicodedata
from openpyxl import load_workbook
from survivor_data import load_tables

ROOT = os.path.dirname(os.path.abspath(__file__))
P = lambda *a: os.path.join(ROOT, *a)
def _excluded_owners():
    """Owners to drop everywhere. Kept in private/excluded_owners.txt (one name per
    line), which is git-ignored so the names never reach the public repo. Fails
    closed: without the file the import refuses to run."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "private", "excluded_owners.txt")
    if not os.path.exists(path):
        raise SystemExit(f"missing {path}: create it (one excluded owner name per line) before importing")
    return {l.strip().lower() for l in open(path, encoding="utf-8") if l.strip()}


EXCLUDED_OWNERS = _excluded_owners()
OWNER_FIX = {"jimy": "Jimmy"}
NOT_OWNERS = {"undrafted", "unpicked", "-", "fa", "n/a", ""}
# sheet spelling -> survivoR short name, where surname/first-name matching can't work
ALIASES = {
    "riz god, baby": "Rizo",
}


def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]+", " ", s).split()


def strip_tag(name):
    """'Jeremy Collins (H)' -> 'Jeremy Collins'"""
    return re.sub(r"\s*\([^)]*\)\s*$", "", str(name)).strip()


class Matcher:
    """Match sheet names to one season's survivoR castaways."""
    def __init__(self, cast):
        self.cast = cast  # list of castaway rows for the season

    def __call__(self, raw):
        name = strip_tag(raw)
        if name.lower() in ALIASES:
            return ALIASES[name.lower()]
        for nick in re.findall(r'"([^"]+)"', name):  # 'Janani "J. Maya" Krishnan-Jha'
            for c in self.cast:
                if norm(c["castaway"]) == norm(nick):
                    return c["castaway"]
        toks = norm(name)
        if not toks:
            return None
        def keys(c):
            full = norm(c["full_name"]); short = norm(c["castaway"])
            return set(full) | set(short), full[-1] if full else "", short
        # 1) exact short name or full name
        for c in self.cast:
            if norm(c["full_name"]) == toks or norm(c["castaway"]) == toks:
                return c["castaway"]
        # 2) same surname, and first name / nickname appears
        hits = [c for c in self.cast if keys(c)[1] == toks[-1] and (toks[0] in keys(c)[0])]
        if len(hits) == 1:
            return hits[0]["castaway"]
        # 3) first name / nickname unique in the season (before surname-only, so a
        #    sheet typo like 'Desiree Abbate' finds Desiree, not Domenick Abbate)
        hits = [c for c in self.cast if toks[0] in keys(c)[0] and toks[0] in (norm(c["castaway"]) + norm(c["full_name"])[:1])]
        if len(hits) == 1:
            return hits[0]["castaway"]
        # 4) unique surname with the same first initial
        hits = [c for c in self.cast if keys(c)[1] == toks[-1]
                and any(k.startswith(toks[0][0]) for k in norm(c["full_name"])[:1] + norm(c["castaway"]))]
        if len(hits) == 1:
            return hits[0]["castaway"]
        return None


def clean_owner(o):
    o = str(o or "").strip()
    if o.lower() in EXCLUDED_OWNERS or o.lower() in NOT_OWNERS:
        return None
    return OWNER_FIX.get(o.lower(), o)


def draft_table(wb):
    """Rows of the DRAFT table: {owner: [picks]} (excluded owners dropped)."""
    for ws in wb.worksheets:
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        for i, r in enumerate(rows):
            if r and r[0] == "Teams:":
                owners = r[1:]
                out = {}
                for row in rows[i + 1:]:
                    if not row or not str(row[0] or "").startswith("Pick"):
                        break
                    for col, pick in enumerate(row[1:]):
                        if col >= len(owners) or not pick:
                            continue
                        o = clean_owner(owners[col])
                        if o:
                            out.setdefault(o, []).append(pick)
                return out
    return {}


def survival_start(wb, match, order):
    """From the sheet's ELIMINATED table ('Survival Points Earned' per finisher),
    return the boot order whose week first earned survival points minus one
    (= first_week_boot + survival_offset), or None if the ladder isn't clean."""
    for ws in wb.worksheets:
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        hit = next(((i, r.index("ELIMINATED")) for i, r in enumerate(rows) if "ELIMINATED" in r), None)
        if not hit:
            continue
        i0, col = hit
        ladder = []
        for r in rows[i0 + 1:]:
            nm, sp = r[col], (r[col + 1] if col + 1 < len(r) else None)
            if nm and isinstance(sp, (int, float)):
                s = match(nm)
                if s and order.get(s):
                    ladder.append((order[s], sp))
        ladder.sort()
        vals = [sp for _, sp in ladder]
        first = next((i for i, v in enumerate(vals) if v > 0), None)
        if first is None:
            return None
        tri = [k * (k + 1) / 2 for k in range(1, 5)]
        if vals[first:first + 4] != tri[:len(vals[first:first + 4])] or len(vals[first:]) < 4:
            return None  # not a clean 1, 3, 6, 10 ladder: don't trust it
        return ladder[first][0] - 1
    return None


def import_season(path, n, tables):
    wb = load_workbook(path, data_only=True)
    cast = [c for c in tables["castaways"] if c["version_season"] == f"US{n}"]
    match = Matcher(cast)
    order = {c["castaway"]: c.get("order") or 99 for c in cast}
    draft = draft_table(wb)
    owners, unmatched = [], []
    for o, picks in draft.items():
        roster = []
        for p in picks:
            s = match(p)
            if s: roster.append(s)
            else: unmatched.append(p)
        owners.append({"name": o, "roster": roster})
    # excluded owners' picks were still drafted: count them when finding the draft point
    all_drafted = {s for o in owners for s in o["roster"]}
    for ws in wb.worksheets:
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        for i, r in enumerate(rows):
            if r and r[0] == "Teams:":
                for row in rows[i + 1:]:
                    if not row or not str(row[0] or "").startswith("Pick"): break
                    for col, pick in enumerate(row[1:]):
                        hdr = str(r[col + 1] or "").lower()
                        if pick and hdr not in ("undrafted", "unpicked"):
                            s = match(pick)
                            if s: all_drafted.add(s)
    first = min((order[s] for s in all_drafted if order.get(s)), default=4)
    # Scoring starts the week of the first drafted contestant's boot. The sheet's
    # survival ladder shows when survival points started (some old seasons started
    # them a week or two late, e.g. S36); that gap becomes survival_offset.
    offset = 0
    start = survival_start(wb, match, order)
    if start is not None:
        first = min(first, start)
        offset = start - first
    else:  # unreadable ladder: keep a previously calibrated first_week_boot
        prev = P("leagues", f"season{n}.json")
        if os.path.exists(prev):
            first = json.load(open(prev)).get("first_week_boot", first)
    note = "Rosters from the workbook's draft table (import_sheets.py)."
    truth = None
    if "Week-By-Week Scoresheet" in wb.sheetnames:
        from parse_sheet import parse
        t = parse(path)
        if any(v["total"] for v in t.values()):
            for v in t.values():  # 'Mom/Greg' = drafted by both; excluded owners dropped
                parts = [clean_owner(p) for p in str(v["owner"] or "").split("/")]
                v["owner"] = "/".join(p for p in parts if p) or None
            truth = t
            # the score sheet's owner column is the end-of-season roster (waivers
            # included) and is more reliable than the draft table: prefer it
            sheet_owners, sheet_unmatched, seen = {}, [], {}
            for name, v in t.items():
                s = match(name)
                if s and s in seen:
                    print(f"  WARNING S{n}: '{name}' and '{seen[s]}' both match {s}")
                if s: seen[s] = name
                for o in (v["owner"] or "").split("/"):
                    if not o: continue
                    if s: sheet_owners.setdefault(o, []).append(s)
                    else: sheet_unmatched.append(name)
            if sheet_owners:
                draft_order = [o["name"] for o in owners]
                owners = [{"name": o, "roster": sorted(r)} for o, r in
                          sorted(sheet_owners.items(), key=lambda kv: draft_order.index(kv[0]) if kv[0] in draft_order else 99)]
                unmatched = sheet_unmatched
                note = "Rosters from the score sheet's owner column, i.e. end of season incl. waivers (import_sheets.py)."
    league = {"season": n, "league": "Family League", "first_week_boot": first, "notes": note, "owners": owners}
    if offset:
        league["survival_offset"] = offset
    return league, truth, unmatched


def import_career(path):
    ws = load_workbook(path, data_only=True).active
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    hdr = rows[0]
    names = [clean_owner(h) for h in hdr[2:7]]
    out = []
    for r in rows[1:]:
        if not isinstance(r[1], (int, float)):
            continue
        totals = {}
        for name, v in zip(names, r[2:7]):
            if name and isinstance(v, (int, float)) and not (name == "Will" and v == 0 and r[1] < 45):
                totals[name] = v
        out.append({"season": int(r[1]), "totals": totals})
    return {"source": "Survivor Career Stats.xlsx (owner's sheet; official historical totals)", "seasons": out}


if __name__ == "__main__":
    want = {int(a) for a in sys.argv[1:]}
    tables = load_tables()
    os.makedirs(P("leagues"), exist_ok=True)
    for path in sorted(glob.glob(P("reference", "*.xlsx"))):
        m = re.search(r"Season[ _](\d+)", os.path.basename(path))
        if not m:
            continue
        n = int(m.group(1))
        if want and n not in want:
            continue
        league, truth, unmatched = import_season(path, n, tables)
        json.dump(league, open(P("leagues", f"season{n}.json"), "w"), indent=1)
        if truth:
            json.dump(truth, open(P(f"truth{n}.json"), "w"), indent=1)
        sizes = {o["name"]: len(o["roster"]) for o in league["owners"]}
        print(f"S{n}: first_week_boot={league['first_week_boot']} survival_offset={league.get('survival_offset', 0)} rosters={sizes}"
              f"{' truth' if truth else ''}{'  UNMATCHED ' + str(unmatched) if unmatched else ''}")
    career = glob.glob(P("reference", "*Career*.xlsx"))
    if career and not want:
        os.makedirs(P("history"), exist_ok=True)
        h = import_career(career[0])
        json.dump(h, open(P("history", "official_totals.json"), "w"), indent=1)
        print(f"career: {len(h['seasons'])} seasons -> history/official_totals.json")
