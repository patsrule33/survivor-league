"""Compare engine output to the hand-built spreadsheet, per contestant / week / category.

    python backtest.py fixtures/season47.json truth47.json
    python backtest.py fixtures/survivoR_season46.json truth46.json --merge 5,6

--merge A,B  engine weeks A and B are one column in the sheet (a double-Tribal
             episode the sheet kept in a single column). Repeatable.
"""
import argparse, json, re
from scoring import score_season, contestant_totals

CATS = ["challenges", "votes", "survival", "special"]

def clean(n): return re.sub(r"\s*\((?:E|B|Nu|S|N|Y|T|L|G)\)\s*$", "", n).strip()

def _keys(n):
    """'Jerome "Rome" Cooney' -> {('cooney','jerome'), ('cooney','rome')}"""
    nick = re.findall(r'"([^"]+)"', n)
    parts = re.sub(r'"[^"]+"', " ", n).split()
    last = parts[-1].lower()
    return {(last, f.lower()) for f in [parts[0]] + nick}

def match_names(engine_names, truth_names):
    """Map engine names to sheet names: exact, else surname + first name or nickname."""
    out = {}
    for e in engine_names:
        if e in truth_names:
            out[e] = e; continue
        hits = [t for t in truth_names if _keys(e) & _keys(t)]
        if len(hits) == 1:
            out[e] = hits[0]
    return out

def column_map(n_weeks, merges):
    """engine week -> sheet column (1-based), collapsing merged weeks."""
    merged_into = {}
    for a, b in merges:
        merged_into[b] = a
    col, out = 0, {}
    for k in range(1, n_weeks + 1):
        if k in merged_into:
            out[k] = out[merged_into[k]]
        else:
            col += 1; out[k] = col
    return out

def run(season_json, truth_json, merges=(), verbose=True):
    season = json.load(open(season_json, encoding="utf-8"))
    truth = {clean(k): v for k, v in json.load(open(truth_json, encoding="utf-8")).items()}
    scores = score_season(season)
    names = match_names(list(scores), list(truth))
    n_weeks = len(season["weeks"])
    cols = column_map(n_weeks, merges)

    # sum engine weeks into sheet columns
    eng_cols = {}
    for name, wk in scores.items():
        d = {}
        for k, cats in wk.items():
            c = d.setdefault(cols[k], {x: 0.0 for x in CATS})
            for x in CATS: c[x] += cats[x]
        eng_cols[name] = d

    diffs, exact, cells = [], 0, 0
    for name, wk in eng_cols.items():
        t = truth.get(names.get(name))
        if not t:
            diffs.append((name, "-", "missing in sheet", 0, 0)); continue
        for col, d in wk.items():
            sheet_wk = t["weeks"][col - 1]
            for c in CATS:
                cells += 1
                if abs(d[c] - sheet_wk[c]) < 1e-9: exact += 1
                else: diffs.append((name, col, c, d[c], sheet_wk[c]))
    eng = contestant_totals(scores)
    if verbose:
        print(f"{season_json}: {exact}/{cells} category-cells match ({100*exact/max(cells,1):.1f}%)")
        unmatched = [t for t in truth if t not in names.values()]
        if unmatched: print("Sheet names with no engine contestant:", unmatched)
        print("\nContestant totals (engine vs sheet, summed from the weekly cells):")
        for n in eng:
            t = truth.get(names.get(n))
            s = sum(w[c] for w in t["weeks"] for c in CATS) if t else None
            flag = "" if s is not None and abs(eng[n]-s) < 1e-9 else "   <-- differs"
            print(f"  {n:34s} {eng[n]:7.1f} {'-' if s is None else format(s,'7.1f')}{flag}")
        print("\nCell differences (week = sheet column):")
        for n, k, c, e, s in diffs:
            print(f"  wk{k:<3} {n:34s} {c:10s} engine={e:g} sheet={s:g}")
    return scores, diffs, truth

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("season_json"); ap.add_argument("truth_json")
    ap.add_argument("--merge", action="append", default=[],
                    help="A,B: engine weeks A and B share one sheet column")
    a = ap.parse_args()
    run(a.season_json, a.truth_json, [tuple(map(int, m.split(","))) for m in a.merge])
