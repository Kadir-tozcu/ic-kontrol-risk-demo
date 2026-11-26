import itertools,json
import numpy as np
import pandas as pd
from scipy.stats import binomtest,chi2
def analyze(d,prefix):
    methods=[c for c in d if c not in ("fold","truth")]
    if d[methods].isna().any().any():raise ValueError("Incomplete paired predictions")
    y=d.truth.to_numpy(bool); p={m:d[m].to_numpy(bool) for m in methods}
    correct=np.column_stack([p[m]==y for m in methods]).astype(int)
    k=len(methods);col=correct.sum(0);row=correct.sum(1);total=col.sum()
    den=k*total-(row**2).sum()
    q=float((k-1)*(k*(col**2).sum()-total**2)/den) if den else 0.
    def metric(y,p):
        tp=(y&p).sum();fp=(~y&p).sum();fn=(y&~p).sum()
        return np.array([2*tp/max(1,2*tp+fp+fn),tp/max(1,y.sum())])
    rng=np.random.default_rng(2026)
    # stratified paired record resampling; conditional on fitted CV predictions
    pos=np.flatnonzero(y);neg=np.flatnonzero(~y)
    boot=[np.r_[rng.choice(pos,len(pos)),rng.choice(neg,len(neg))] for _ in range(2000)]
    tests=[]
    for a,b in itertools.combinations(methods,2):
        ac=p[a]==y;bc=p[b]==y
        n01=int((~ac&bc).sum());n10=int((ac&~bc).sum())
        pv=float(binomtest(n01,n01+n10,.5).pvalue) if n01+n10 else 1.
        diff=metric(y,p[b])-metric(y,p[a])
        bd=np.array([metric(y[ix],p[b][ix])-metric(y[ix],p[a][ix]) for ix in boot])
        lo,hi=np.quantile(bd,[.025,.975],axis=0)
        tests.append(dict(a=a,b=b,a_wrong_b_right=n01,a_right_b_wrong=n10,p=pv,f1_delta=float(diff[0]),f1_low=float(lo[0]),f1_high=float(hi[0]),recall_delta=float(diff[1]),recall_low=float(lo[1]),recall_high=float(hi[1])))
    running=0
    for i,t in enumerate(sorted(tests,key=lambda x:x["p"])):
        running=max(running,min(1.,t["p"]*(len(tests)-i)));t["holm_p"]=running
    out=dict(n=len(d),methods=methods,cochran_q=q,cochran_p=float(chi2.sf(q,k-1)),pairs=tests,note="Exploratory paired OOF inference; bootstrap conditional on fitted models, not training variability; pointwise intervals, Holm adjustment for McNemar only.")
    with open(prefix+"_statistics.json","w") as f:json.dump(out,f,indent=2)
    # retain only aggregates, not record-level predictions
    print("PAIRED_STATISTICS",json.dumps(out),flush=True)
