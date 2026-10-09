"""Run manually, review JSON, then commit. No API calls during stock search."""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dashboard.catalog import CATALOG_PATH


def refresh(path=CATALOG_PATH, symbols=None, fetch=None):
    payload = json.loads(Path(path).read_text(encoding='utf-8'))
    fetch = fetch or (lambda symbol: yf.Ticker(symbol).get_info())
    failures = []
    for row in payload['companies']:
        if symbols and row['symbol'] not in symbols:
            continue
        try:
            info = fetch(row['symbol'])
            if not info.get('longName') or not info.get('longBusinessSummary'):
                raise ValueError('Provider returned an incomplete company profile')
            row.update(name=info['longName'], overview=info['longBusinessSummary'],
                       sector=info.get('sector'), industry=info.get('industry'),
                       website=info.get('website'), currency=info.get('currency'),
                       source='Yahoo Finance via yfinance',
                       updated_at=datetime.now(timezone.utc).isoformat())
        except Exception as exc:
            failures.append(row['symbol'])
            print(f"{row['symbol']}: refresh failed; previous profile kept ({type(exc).__name__})", file=sys.stderr)
    # Replace atomically so an interrupted write cannot destroy a saved catalog.
    temp = Path(path).with_suffix('.tmp')
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    temp.replace(path)
    return failures


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--symbols', nargs='+', help='Refresh only these saved symbols')
    args = parser.parse_args()
    sys.exit(1 if refresh(symbols=args.symbols) else 0)
