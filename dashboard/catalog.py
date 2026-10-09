"""Local company search; API calls belong to the refresh script, not the UI."""
import json
from pathlib import Path

CATALOG_PATH = Path(__file__).resolve().parents[1] / 'data' / 'companies.json'


def load_catalog(path=CATALOG_PATH):
    payload = json.loads(Path(path).read_text(encoding='utf-8'))
    companies = payload['companies']
    if not companies or any(not row.get('symbol') or not row.get('name') for row in companies):
        raise ValueError('Company catalog needs symbols and names.')
    return {row['symbol']: row for row in companies}


def search_catalog(companies, query):
    query = query.strip().casefold()
    return [symbol for symbol, row in companies.items()
            if query in symbol.casefold() or query in row['name'].casefold()]
