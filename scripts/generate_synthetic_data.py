"""
generate_synthetic_data.py
===========================
Produces a STRUCTURALLY FAITHFUL stand-in for the live NOAA FOSS landings
feed so the SQL/dashboard can be developed and validated without network
access. Replace its output with fetch_noaa_data.py for the real project.

Mirrors the REAL feed columns:
  tsn, ts_afs_name, ts_scientific_name, region_name, state_name,
  year, pounds, dollars, tot_count, source, collection

And the REAL feed's quirks, because the quirks are what the analysis must
survive:

1. COMMERCIAL + RECREATIONAL mix: recreational rows (source='MRIP') have
   NULL dollars and must be filtered out of a commercial analysis.
2. CONFIDENTIALITY: some commercial species-years have withheld (NULL)
   pounds/dollars — NOT zero.
3. UNCLASSIFIED rollups: aggregate "species" that must be excluded.
4. PLANTED GROUND TRUTH: known declining / stable / growing species so the
   validation harness can prove the detector works.
"""

import csv
import random

random.seed(42)

YEARS = list(range(2000, 2024))

# species: (base_pounds, price/lb, annual_trend, region, state, tsn, sci_name)
SPECIES = {
    "ATLANTIC COD":      (3_000_000, 2.10, 0.93, "New England", "MASSACHUSETTS", "164712", "Gadus morhua"),
    "RED SNAPPER":       (1_200_000, 4.50, 0.95, "Gulf", "FLORIDA", "168853", "Lutjanus campechanus"),
    "PACIFIC SARDINE":   (8_000_000, 0.35, 0.90, "Pacific", "CALIFORNIA", "161706", "Sardinops sagax"),
    "AMERICAN LOBSTER":  (5_000_000, 6.20, 1.04, "New England", "MAINE", "97314", "Homarus americanus"),
    "DUNGENESS CRAB":    (2_500_000, 5.10, 1.01, "Pacific", "OREGON", "98678", "Metacarcinus magister"),
    "PACIFIC SALMON":    (4_000_000, 3.30, 0.98, "Pacific", "ALASKA", "161975", "Oncorhynchus"),
    "BAY SCALLOP":       (  400_000, 9.00, 0.88, "Mid-Atlantic", "NORTH CAROLINA", "79718", "Argopecten irradians"),
    "ALBACORE TUNA":     (1_800_000, 2.80, 1.00, "Pacific", "WASHINGTON", "172419", "Thunnus alalunga"),
    "BROWN SHRIMP":      (6_000_000, 1.90, 0.99, "Gulf", "TEXAS", "551516", "Farfantepenaeus aztecus"),
    "EASTERN OYSTER":    (  900_000, 7.40, 0.96, "Gulf", "LOUISIANA", "79866", "Crassostrea virginica"),
}

UNCLASSIFIED = [
    ("FINFISHES, UNCLASSIFIED", "New England", "MASSACHUSETTS", "100001"),
    ("SHELLFISHES, UNCLASSIFIED", "Gulf", "LOUISIANA", "100002"),
]


def jitter(value, pct=0.08):
    return value * (1 + random.uniform(-pct, pct))


def main():
    rows = []
    for species, (base_lbs, price, trend, region, state, tsn, sci) in SPECIES.items():
        for i, year in enumerate(YEARS):
            pounds = jitter(base_lbs * (trend ** i))
            dollars = pounds * jitter(price, 0.05)
            withheld = random.random() < 0.06  # ~6% confidential

            # Commercial row
            rows.append({
                "tsn": tsn, "ts_afs_name": species, "ts_scientific_name": sci,
                "region_name": region, "state_name": state, "year": year,
                "pounds": "" if withheld else round(pounds),
                "dollars": "" if withheld else round(dollars, 2),
                "tot_count": "", "source": "ACL",
                "collection": "Commercial",
            })

            # Recreational row for the same species-year (~half the time):
            # has tot_count + pounds but NULL dollars. Must be filtered out.
            if random.random() < 0.5:
                rec_lbs = jitter(pounds * 0.3)
                rows.append({
                    "tsn": tsn, "ts_afs_name": species, "ts_scientific_name": sci,
                    "region_name": region, "state_name": state, "year": year,
                    "pounds": round(rec_lbs), "dollars": "",
                    "tot_count": round(rec_lbs * 1.2), "source": "MRIP",
                    "collection": "Recreational",
                })

    # Aggregate rollups (commercial), must be excluded from per-species analysis.
    for name, region, state, tsn in UNCLASSIFIED:
        for year in YEARS:
            pounds = jitter(500_000)
            rows.append({
                "tsn": tsn, "ts_afs_name": name, "ts_scientific_name": "",
                "region_name": region, "state_name": state, "year": year,
                "pounds": round(pounds), "dollars": round(pounds * jitter(1.5), 2),
                "tot_count": "", "source": "ACL", "collection": "Commercial",
            })

    fieldnames = ["tsn", "ts_afs_name", "ts_scientific_name", "region_name",
                  "state_name", "year", "pounds", "dollars", "tot_count",
                  "source", "collection"]
    with open("data/landings_raw.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    print(f"Wrote {len(rows):,} synthetic rows -> data/landings_raw.csv")
    n_rec = sum(1 for r in rows if r["collection"] == "Recreational")
    print(f"  ({n_rec} recreational rows that the commercial filter must drop)")
    print("Planted declining species (ground truth):")
    for s, v in SPECIES.items():
        t = v[2]
        tag = "DECLINE" if t < 0.97 else ("GROWTH" if t > 1.02 else "stable")
        print(f"  {s:<22} trend={t:.2f}  [{tag}]")


if __name__ == "__main__":
    main()
