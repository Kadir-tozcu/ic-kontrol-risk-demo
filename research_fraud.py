import json,time
import numpy as np
import pandas as pd
from sklearn.datasets import fetch_openml
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score,roc_auc_score,precision_recall_curve
def main():
    ds=fetch_openml(data_id=1597,as_frame=True,parser="auto")
    x=ds.data.copy();y=pd.to_numeric(ds.target).to_numpy()==1
    assert len(x)==284807 and y.sum()==492
    timecol=next((c for c in x if c.lower()=="time"),None)
    if timecol is not None:
        ix=np.argsort(x[timecol].to_numpy(),kind="stable");x=x.iloc[ix].drop(columns=[timecol]);y=y[ix];split="chronological"
    else:
        from sklearn.model_selection import train_test_split
        ix=np.arange(len(y));tr,rest=train_test_split(ix,test_size=.4,stratify=y,random_state=2026);va,te=train_test_split(rest,test_size=.5,stratify=y[rest],random_state=2026);ix=np.r_[tr,va,te];x=x.iloc[ix];y=y[ix];split="stratified random (Time absent from OpenML features)"
    a=int(len(y)*.6);b=int(len(y)*.8)
    model=HistGradientBoostingClassifier(max_iter=150,max_leaf_nodes=31,random_state=2026,class_weight="balanced")
    model.fit(x.iloc[:a],y[:a]);val=model.predict_proba(x.iloc[a:b])[:,1];test=model.predict_proba(x.iloc[b:])[:,1]
    pr,re,th=precision_recall_curve(y[a:b],val);f=2*pr[:-1]*re[:-1]/np.maximum(1e-12,pr[:-1]+re[:-1]);threshold=float(th[np.argmax(f)])
    truth=y[b:];p=test>=threshold;tp=int((p&truth).sum());fp=int((p&~truth).sum());fn=int((~p&truth).sum());tn=int((~p&~truth).sum())
    out=dict(split=split,n=len(y),positive=int(y.sum()),train_n=a,calibration_n=b-a,test_n=len(truth),test_positive=int(truth.sum()),threshold=threshold,tp=tp,fp=fp,fn=fn,tn=tn,precision=tp/max(1,tp+fp),recall=tp/max(1,tp+fn),f1=2*tp/max(1,2*tp+fp+fn),average_precision=average_precision_score(truth,test),roc_auc=roc_auc_score(truth,test),note="OpenML 1597 historical fraud labels, supervised benchmark only; not audit violations or validation of LLM/hybrid; 60/20/20 approximate split; PCA features supplied by dataset.")
    print("FRAUD_RESULTS",json.dumps(out),flush=True)
    with open("fraud_results.json","w") as f:json.dump(out,f,indent=2)
if __name__=="__main__":main()
