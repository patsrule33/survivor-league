"""Parse a league workbook's contestant week-by-week table into ground-truth JSON."""
import sys, json
from openpyxl import load_workbook

CATS = ["challenges", "votes", "survival", "special", "total"]

def num(v):
    try: return float(v) if v not in (None, "") else 0.0
    except Exception: return 0.0

def parse(path):
    wb = load_workbook(path, data_only=True)
    rows = list(wb["Week-By-Week Scoresheet"].iter_rows(values_only=True))
    hdr = next(i for i, r in enumerate(rows) if r[0] == "Contestant")
    out = {}
    for r in rows[hdr+1:]:
        name, owner = r[0], r[1]
        if not name or str(name).startswith("Points Key"): break
        weeks, c = [], 3
        while c + 4 < len(r):
            weeks.append(dict(zip(CATS, [num(x) for x in r[c:c+5]])))
            c += 5
        out[str(name)] = {"owner": owner, "total": num(r[2]), "weeks": weeks}
    return out

if __name__ == "__main__":
    json.dump(parse(sys.argv[1]), open(sys.argv[2], "w"), indent=1)
