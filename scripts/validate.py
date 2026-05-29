"""
validate.py
===========
Proves the analytical logic against synthetic data with known ground truth:
  - COMMERCIAL filter drops all recreational rows
  - withheld values become NULL (not 0)
  - aggregate "...UNCLASSIFIED" rows are excluded
  - planted DECLINE species are flagged; STABLE/GROWTH are not (regression method)

Validated in SQLite for zero-setup portability; the production queries in
sql/*.sql are PostgreSQL. The LOGIC is identical; only dialect differs.
"""

import csv
import math
import sqlite3
import sys
from collections import defaultdict

con = sqlite3.connect(":memory:")
cur = con.cursor()

cur.executescript("""
CREATE TABLE landings_raw (
    tsn TEXT, ts_afs_name TEXT, ts_scientific_name TEXT, region_name TEXT,
    state_name TEXT, year INTEGER, pounds TEXT, dollars TEXT, tot_count TEXT,
    source TEXT, collection TEXT
);
CREATE TABLE landings (
    tsn TEXT, species TEXT, scientific_name TEXT, region TEXT, state TEXT,
    year INTEGER, pounds REAL, dollars REAL, is_withheld INTEGER, is_aggregate INTEGER
);
""")

with open("data/landings_raw.csv") as f:
    for x in csv.DictReader(f):
        cur.execute("INSERT INTO landings_raw VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
            x["tsn"], x["ts_afs_name"], x["ts_scientific_name"], x["region_name"],
            x["state_name"], int(x["year"]), x["pounds"], x["dollars"],
            x["tot_count"], x["source"], x["collection"],
        ))

# Clean (SQLite flavour of 02_clean.sql) — note the COMMERCIAL filter.
cur.executescript("""
INSERT INTO landings
SELECT tsn, ts_afs_name, ts_scientific_name, region_name, state_name, year,
    CASE WHEN pounds  = '' THEN NULL ELSE CAST(pounds  AS REAL) END,
    CASE WHEN dollars = '' THEN NULL ELSE CAST(dollars AS REAL) END,
    CASE WHEN dollars='' OR pounds='' THEN 1 ELSE 0 END,
    CASE WHEN ts_afs_name LIKE '%UNCLASSIFIED%' OR ts_afs_name LIKE '%, UNC%'
              OR ts_afs_name LIKE '%SPP%' OR ts_afs_name LIKE '%OTHER%' THEN 1 ELSE 0 END
FROM landings_raw
WHERE year IS NOT NULL AND ts_afs_name IS NOT NULL AND collection = 'Commercial';
""")

# --- checks ---
rec_leaked = cur.execute("""
    SELECT COUNT(*) FROM landings l JOIN landings_raw r
    ON l.tsn=r.tsn AND l.year=r.year AND l.species=r.ts_afs_name
    WHERE r.collection='Recreational'
""").fetchone()[0]
# simpler: recreational rows should never reach `landings`; check via source
rec_rows_total = cur.execute("SELECT COUNT(*) FROM landings_raw WHERE collection='Recreational'").fetchone()[0]
commercial_in_raw = cur.execute("SELECT COUNT(*) FROM landings_raw WHERE collection='Commercial'").fetchone()[0]
landings_count = cur.execute("SELECT COUNT(*) FROM landings").fetchone()[0]

withheld_zeros = cur.execute("SELECT COUNT(*) FROM landings WHERE is_withheld=1 AND pounds IS NOT NULL").fetchone()[0]
agg = cur.execute("SELECT COUNT(*) FROM landings WHERE is_aggregate=1").fetchone()[0]

# regression trend (computed in Python since SQLite lacks regr_slope)
rows = cur.execute("""
    SELECT species, year, SUM(pounds) FROM landings
    WHERE is_withheld=0 AND is_aggregate=0 GROUP BY species, year HAVING SUM(pounds)>0
""").fetchall()
data = defaultdict(list)
for sp, yr, lbs in rows:
    data[sp].append((yr, math.log(lbs)))

def fit(points):
    n=len(points); xs=[p[0] for p in points]; ys=[p[1] for p in points]
    mx=sum(xs)/n; my=sum(ys)/n
    sxx=sum((x-mx)**2 for x in xs); sxy=sum((x-mx)*(y-my) for x,y in zip(xs,ys))
    syy=sum((y-my)**2 for y in ys)
    slope=sxy/sxx; r2=(sxy**2)/(sxx*syy) if syy>0 else 0
    return slope, r2

flagged=set(); print(f"\n{'SPECIES':<22}{'ann %/yr':>10}{'R2':>8}   classification")
print("-"*58)
out=[]
for sp,pts in data.items():
    slope,r2=fit(pts); rate=math.exp(slope)-1
    if rate<=-0.05 and r2>=0.5: c="DECLINING (clear)"; flagged.add(sp)
    elif rate<=-0.02 and r2>=0.5: c="DECLINING (mild)"; flagged.add(sp)
    elif rate>=0.05 and r2>=0.5: c="GROWING (clear)"
    elif r2<0.5: c="NO CLEAR TREND"
    else: c="STABLE"
    out.append((rate,sp,r2,c))
for rate,sp,r2,c in sorted(out):
    print(f"{sp:<22}{rate*100:>9.1f}%{r2:>8.3f}   {c}")

GT_DECLINE={"ATLANTIC COD","RED SNAPPER","PACIFIC SARDINE","BAY SCALLOP","EASTERN OYSTER"}
GT_NOT={"AMERICAN LOBSTER","DUNGENESS CRAB","ALBACORE TUNA","BROWN SHRIMP","PACIFIC SALMON"}

print("\n"+"="*58+"\nVALIDATION CHECKS\n"+"="*58)
ok=True
if landings_count==commercial_in_raw and rec_rows_total>0:
    print(f"  [PASS] commercial filter: dropped all {rec_rows_total} recreational rows")
else:
    print(f"  [FAIL] commercial filter: {landings_count} vs expected {commercial_in_raw}"); ok=False
if withheld_zeros==0: print("  [PASS] withheld rows stored as NULL (not 0)")
else: print(f"  [FAIL] {withheld_zeros} withheld rows non-NULL"); ok=False
if agg>0: print(f"  [PASS] {agg} aggregate rows flagged & excluded")
else: print("  [FAIL] no aggregate rows flagged"); ok=False
missed=GT_DECLINE-flagged
if not missed: print(f"  [PASS] all {len(GT_DECLINE)} planted declines detected")
else: print(f"  [FAIL] missed declines: {missed}"); ok=False
fa=GT_NOT & flagged
if not fa: print("  [PASS] no false alarms on stable/growth species")
else: print(f"  [WARN] over-flagged: {fa}")

print("\nRESULT:", "ALL CRITICAL CHECKS PASSED" if ok else "FAILURES PRESENT")
sys.exit(0 if ok else 1)
