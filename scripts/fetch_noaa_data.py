"""
fetch_noaa_data.py
==================
Pulls U.S. commercial fisheries landings from the NOAA Fisheries
"FOSS" (Fisheries One Stop Shop) public REST API (Oracle ORDS) and
writes the result to data/landings_raw.csv.

The base endpoint is:
    https://www.st.nmfs.noaa.gov/ords/foss/landings/
Hitting it returns JSON shaped like:
    {"items": [ {...}, ... ], "hasMore": true, "limit": 25, "offset": 0, ...}
with offset/limit paging.

ROBUSTNESS NOTES (why this is written defensively):
- ORDS sometimes returns an HTML error page instead of JSON (bad params,
  server hiccup, maintenance). Calling .json() on that raises the exact
  "Expecting value: line 1 column 1" error. So we inspect status code and
  content-type FIRST and print the body when it is not JSON, instead of
  blindly parsing.
- Some government servers behave better with an explicit User-Agent.
- We page conservatively and honor the server's reported limit/hasMore.
"""

import csv
import sys
import time
import requests

# NOTE: NOAA migrated ODS/ORDS to the cloud in 2025. The old host
# (www.st.nmfs.noaa.gov/ords/...) now serves an "Under Maintenance" / "We've
# Moved!" HTML page. The current FOSS base is apps-st.fisheries.noaa.gov/ods/foss/.
BASE_URL = "https://apps-st.fisheries.noaa.gov/ods/foss/landings/"
METADATA_URL = "https://apps-st.fisheries.noaa.gov/ods/foss/metadata-catalog/landings/"
PAGE_LIMIT = 1000           # conservative; ORDS may cap this anyway
REQUEST_TIMEOUT = 60
SLEEP_BETWEEN_PAGES = 0.3
OUTPUT_PATH = "data/landings_raw.csv"

HEADERS = {
    # A plain UA avoids some automated-traffic filters on gov servers.
    "User-Agent": "fisheries-trend-analysis/1.0 (student project)",
    "Accept": "application/json",
}


def get_json_or_explain(url, params):
    """GET a URL and return parsed JSON, or print a clear diagnostic and exit."""
    resp = requests.get(url, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)

    ctype = resp.headers.get("Content-Type", "")
    if resp.status_code != 200:
        print(f"\nHTTP {resp.status_code} from {resp.url}", file=sys.stderr)
        print("First 500 chars of response:\n", resp.text[:500], file=sys.stderr)
        sys.exit(1)

    if "json" not in ctype.lower():
        # This is the case that produced your error: the body isn't JSON.
        print(f"\nExpected JSON but got Content-Type: {ctype!r}", file=sys.stderr)
        print(f"Requested URL: {resp.url}", file=sys.stderr)
        print("First 800 chars of what the server actually returned:\n",
              resp.text[:800], file=sys.stderr)
        print("\nLikely causes: endpoint moved, server maintenance, or the "
              "query params were rejected. Try opening the Requested URL "
              "above in a browser to see the raw response.", file=sys.stderr)
        sys.exit(1)

    try:
        return resp.json()
    except ValueError:
        print(f"\nContent-Type claimed JSON but parsing failed. URL: {resp.url}",
              file=sys.stderr)
        print("First 800 chars:\n", resp.text[:800], file=sys.stderr)
        sys.exit(1)


def fetch_all_landings():
    """Generator yielding landing records (dicts) across all pages."""
    offset = 0
    page = 0
    while True:
        payload = get_json_or_explain(BASE_URL, {"offset": offset, "limit": PAGE_LIMIT})

        items = payload.get("items", [])
        if not items:
            break

        for row in items:
            yield row

        page += 1
        print(f"  page {page}: +{len(items)} rows (offset {offset})", file=sys.stderr)

        if not payload.get("hasMore", False):
            break

        # Advance by the server's actual returned count (it may cap our limit).
        offset += len(items)
        time.sleep(SLEEP_BETWEEN_PAGES)


def main():
    print("Fetching NOAA FOSS commercial landings...", file=sys.stderr)
    print(f"Endpoint: {BASE_URL}", file=sys.stderr)
    rows = list(fetch_all_landings())
    if not rows:
        print("No rows returned.", file=sys.stderr)
        sys.exit(1)

    # Fixed scalar columns matching the schema/loader. We drop the nested
    # `links` object the API attaches to each row (it's HATEOAS navigation,
    # not data) and ignore any future extra fields for a stable CSV.
    fieldnames = [
        "tsn", "ts_afs_name", "ts_scientific_name", "region_name",
        "state_name", "year", "pounds", "dollars", "tot_count",
        "source", "collection",
    ]

    with open(OUTPUT_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k) for k in fieldnames})

    print(f"\nWrote {len(rows):,} rows -> {OUTPUT_PATH}", file=sys.stderr)
    print(f"Columns written: {fieldnames}", file=sys.stderr)


if __name__ == "__main__":
    main()
