import numpy as np
import pandas as pd


def generate_synthetic_data(n=10000, seed=42):
    rng=np.random.default_rng(seed)
    age=rng.integers(18,91,n)
    inactive=rng.integers(0,730,n)
    amount=np.round(rng.lognormal(8.4,1.15,n),2)
    avg=np.round(rng.lognormal(8.1,0.85,n),2)
    new_recipient=rng.random(n)<0.21
    hour=rng.integers(0,24,n)
    daily_count=rng.poisson(2.2,n)+1
    daily_total=np.round(amount*rng.uniform(1,3,n),2)
    times=pd.Timestamp('2026-11-18')-pd.to_timedelta(rng.integers(0,30,n),unit='D')+pd.to_timedelta(hour,unit='h')
    df=pd.DataFrame({'transaction_id':[f'TX-{i:06d}' for i in range(1,n+1)],'customer_id':[f'DEMO-{x:05d}' for x in rng.integers(1,4500,n)],'transaction_datetime':times,'age':age,'inactivity_days':inactive,'transaction_amount':amount,'historical_avg_amount':avg,'new_recipient':new_recipient,'transaction_hour':hour,'daily_transaction_count':daily_count,'daily_transfer_total':daily_total})
    return df
