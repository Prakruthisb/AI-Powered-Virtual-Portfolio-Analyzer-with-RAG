"""Run after adding PDFs:  python ingest.py        (only new files)
                          python ingest.py --rebuild  (wipe and re-index everything)"""
import argparse
import rag

parser = argparse.ArgumentParser()
parser.add_argument("--rebuild", action="store_true", help="wipe the index and re-ingest all PDFs")
args = parser.parse_args()

s = rag.ingest(rebuild=args.rebuild)
print(f"Added {len(s['added'])} file(s), {s['chunks']} chunks")
for f in s["added"]:
    print("  +", f)
if s["skipped"]:
    print(f"Already indexed: {len(s['skipped'])} file(s)")
for f in s["changed"]:
    print(f"  ! {f} changed since it was indexed — run with --rebuild to refresh")
for f in s["no_text"]:
    print(f"  ! {f}: no extractable text (scanned PDF?) — needs OCR, skipped")
print("Indexed chunks per company:", rag.index_status())