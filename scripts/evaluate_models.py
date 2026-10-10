"""Small offline benchmark study from exported daily CSVs; no API or database access."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dashboard.forecast import forecast


def evaluate(histories, as_of, horizons=(5, 21, 42), offsets=(504, 252, 0), runner=forecast):
    if not 1 <= len(histories) <= 3 or len(horizons) > 3 or len(offsets) > 3:
        raise ValueError('Limit this study to three stocks, three horizons and three snapshots.')
    if not horizons or not offsets or any(not isinstance(h, int) or not 1 <= h <= 63 for h in horizons):
        raise ValueError('Provide one to three horizons between 1 and 63 trading days.')
    if any(not isinstance(offset, int) or offset < 0 for offset in offsets):
        raise ValueError('Snapshot offsets must be nonnegative row counts.')
    clock = pd.Timestamp(as_of)
    clock = clock.tz_localize('UTC') if clock.tzinfo is None else clock.tz_convert('UTC')
    rows, sources = [], []
    for symbol, supplied in histories.items():
        frame = supplied[['Date', 'Close', 'Volume']].copy()
        frame['Date'] = pd.to_datetime(frame.Date, errors='raise').dt.tz_localize(None).dt.normalize()
        for col in ['Close', 'Volume']:
            frame[col] = pd.to_numeric(frame[col], errors='raise')
        if frame.empty or frame.isna().any().any() or not np.isfinite(frame[['Close','Volume']]).all().all():
            raise ValueError('CSV must contain finite dates, prices and volumes.')
        if (frame.Close <= 0).any() or (frame.Volume < 0).any():
            raise ValueError('CSV prices must be positive and volumes nonnegative.')
        frame = frame.sort_values('Date').drop_duplicates('Date').reset_index(drop=True)
        frame = frame.loc[frame.Date + pd.Timedelta(hours=36) <= clock.tz_localize(None)]
        frame = frame.loc[frame.Date >= clock.tz_localize(None).normalize()-pd.DateOffset(years=5)].tail(1500).reset_index(drop=True)
        fingerprint = hashlib.sha256(frame.to_csv(index=False,float_format='%.17g').encode()).hexdigest()
        sources.append({'symbol':symbol, 'eligible_rows':len(frame), 'data_fingerprint':fingerprint})
        for offset in offsets:
            stop = len(frame)-offset
            if stop < 2:
                continue
            snapshot = frame.iloc[:stop].copy()
            for horizon in horizons:
                result = runner(snapshot,horizon)
                scores = {entry['method']:entry['mae_pct'] for entry in result.get('validation_scores',[])}
                learned = {name:error for name,error in scores.items() if name != 'Unchanged-price baseline'}
                best_learned = min(learned,key=learned.get) if learned else None
                rows.append({'symbol':symbol, 'snapshot_date':str(snapshot.Date.iloc[-1].date()),
                    'horizon':horizon, 'input_rows':len(snapshot), 'accepted':bool(result.get('available')),
                    'selected_method':result.get('model'), 'reason':result.get('reason'),
                    'development_error_pp':scores.get(result.get('model')),
                    'development_benchmark_pp':scores.get('Unchanged-price baseline'),
                    'best_learned_method':best_learned, 'best_learned_development_error_pp':learned.get(best_learned),
                    'development_scores':result.get('validation_scores',[]),
                    'recent_error_pp':result.get('mae_pct'), 'recent_benchmark_pp':result.get('baseline_mae_pct'),
                    'test_rows':result.get('test_rows'), 'test_start':result.get('test_start'),
                    'test_end':result.get('test_end')})
    return {'evaluated_at':datetime.now(timezone.utc).isoformat(), 'as_of':clock.isoformat(),
        'source':'Daily CSV exports from Stock Explorer / Yahoo Finance via yfinance',
        'method':'Fixed app models; three purged development folds; separate recent holdout; no tuning during this study',
        'completion_policy':'36h-utc-v1', 'horizons':list(horizons), 'snapshot_offsets':list(offsets),
        'sources':sources, 'checks':len(rows), 'accepted':sum(row['accepted'] for row in rows), 'results':rows,
        'limitations':['Only three deliberately chosen US stocks; not representative of all markets.',
            'Historical snapshots use currently adjusted prices, not archived point-in-time provider vintages.',
            'Test targets and some snapshot windows overlap; counts are not independent trials.',
            'Passing an error comparison does not establish statistical significance or future trading profit.',
            'No hyperparameters or acceptance thresholds were changed after seeing these results.']}


def markdown(report):
    lines=['# Small historical model study', '',
        f"Data cutoff: {report['as_of']}. Source: {report['source']}.", '',
        f"{report['accepted']} of {report['checks']} stock/period/horizon checks passed both benchmark checks.", '',
        'This count is an acceptance result, not prediction accuracy.', '',
        '| Stock | History ending | Trading days ahead | Best learned method in earlier tests | Model error (pp) | No-change error (pp) | Passed both checks? |',
        '| --- | --- | ---: | --- | ---: | ---: | --- |']
    for row in report['results']:
        def display(value): return '—' if value is None else f'{value:.2f}'
        lines.append(f"| {row['symbol']} | {row['snapshot_date']} | {row['horizon']} | {row['best_learned_method'] or 'Insufficient data'} | {display(row['best_learned_development_error_pp'])} | {display(row['development_benchmark_pp'])} | {'Yes' if row['accepted'] else 'No'} |")
    lines += ['', 'The table compares errors in earlier development tests. Errors measure percentage points of future price change; smaller is better. JSON includes every candidate score and the separate recent test results.', '',
              'Models are chosen on earlier tests. The recent holdout only accepts or rejects that choice; it does not choose a replacement model.', '',
              'Limitations:', *['- '+item for item in report['limitations']], '']
    return '\n'.join(lines)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csv',action='append',required=True,metavar='SYMBOL=PATH')
    parser.add_argument('--as-of',required=True,help='UTC timestamp used for the completion buffer')
    parser.add_argument('--output',required=True,help='Destination JSON path; Markdown is written alongside it')
    args=parser.parse_args()
    histories={}
    for spec in args.csv:
        symbol,path=spec.split('=',1)
        if symbol in histories: parser.error('Use each symbol once.')
        histories[symbol]=pd.read_csv(path)
    report=evaluate(histories,args.as_of)
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    output.with_suffix('.md').write_text(markdown(report))
    print(f"{report['accepted']} / {report['checks']} checks passed; saved {output}")


if __name__ == '__main__':
    main()
