import pandas as pd
import pytest
from scripts.evaluate_models import evaluate


def test_study_only_supplies_history_available_at_each_snapshot():
    data=pd.DataFrame({'Date':pd.bdate_range('2023-01-02',periods=800),'Close':100.,'Volume':1000})
    supplied=[]
    def runner(frame,horizon):
        supplied.append((frame.copy(),horizon))
        return {'available':False,'reason':'No model passed.'}
    clock=data.Date.iloc[-1]+pd.Timedelta(hours=36)
    report=evaluate({'AAPL':data},clock,horizons=(5,42),offsets=(252,0),runner=runner)
    assert report['checks']==4 and report['accepted']==0
    assert len(supplied[0][0])==548 and len(supplied[2][0])==800
    assert supplied[0][0].Date.max()<supplied[2][0].Date.max()
    assert [h for _,h in supplied]==[5,42,5,42]
    assert 'prediction accuracy' not in report['method']


def test_study_rejects_unbounded_work_and_excludes_recent_bar():
    data=pd.DataFrame({'Date':pd.to_datetime(['2026-10-07','2026-10-08','2026-10-09']), 'Close':100.,'Volume':1000})
    supplied=[]
    def runner(frame,horizon): supplied.append(frame); return {'available':False}
    evaluate({'AAPL':data},'2026-10-10T05:00:00Z',horizons=(5,),offsets=(0,),runner=runner)
    assert supplied[0].Date.max()==pd.Timestamp('2026-10-08')
    with pytest.raises(ValueError): evaluate({'AAPL':data},'2026-10-10',horizons=(5,7,21,42))
