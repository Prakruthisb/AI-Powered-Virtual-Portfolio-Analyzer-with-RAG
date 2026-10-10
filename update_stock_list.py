"""Refresh the NSE stock list used by the add-holding dropdown.

  python update_stock_list.py                 download from NSE now
  python update_stock_list.py EQUITY_L.csv    use a file you downloaded from NSE yourself
"""
import sys
import stock_list

ok, msg = stock_list.import_csv(sys.argv[1]) if len(sys.argv) > 1 else stock_list.refresh()
print(("OK: " if ok else "FAILED: ") + msg)
sys.exit(0 if ok else 1)