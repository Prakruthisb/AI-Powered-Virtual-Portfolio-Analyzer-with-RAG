"""
Steps 1-2: download documents into data/<TICKER>/.

Fill data/sources.csv (header: company,url,filename), then run:  python download_docs.py
  company   folder name = ticker without .NS, e.g. TCS, INFY, RELIANCE, HDFCBANK, ICICIBANK
  url       direct link to the PDF (investor-relations page, or BSE/NSE filings)
  filename  name to save as — use the convention  annual_report_2025.pdf / earnings_q2_fy26.pdf
            (document type and year are read from the filename)
"""
import csv
import sys
from pathlib import Path

import requests

DATA_DIR = Path(__file__).parent / "data"
SOURCES = DATA_DIR / "sources.csv"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; portfolio-research-bot)"}  # many IR sites block default UAs


def main():
    if not SOURCES.exists():
        sys.exit(f"Create {SOURCES} first (columns: company,url,filename).")

    ok = failed = skipped = 0
    with open(SOURCES, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            company, url, filename = (row[k].strip() for k in ("company", "url", "filename"))
            dest = DATA_DIR / company.upper() / filename
            if dest.exists():
                skipped += 1
                continue
            try:
                r = requests.get(url, headers=HEADERS, timeout=60)
                r.raise_for_status()
                if not r.content.startswith(b"%PDF"):
                    raise ValueError("response isn't a PDF (login page / HTML?)")
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(r.content)
                print(f"  ✓ {company}/{filename} ({len(r.content) / 1e6:.1f} MB)")
                ok += 1
            except Exception as e:
                print(f"  ✗ {company}/{filename}: {e}")
                failed += 1
    print(f"Downloaded {ok}, already had {skipped}, failed {failed}. Now run: python ingest.py")


if __name__ == "__main__":
    main()