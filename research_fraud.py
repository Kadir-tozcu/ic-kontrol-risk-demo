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
    timecol=next(c for c in x if c.lower()=="time")
    ix=np.argsort(x[timecol].to_numpy(),kind="stable")
    x=x.iloc[ix].drop(columns=[timecol]);y=y[ix]
    a=int(len(y)*.6);b=int(len(y)*.8)
    model=HistGradientBoostingClassifier(max_iter=150,max_leaf_nodes=31,random_state=2026,class_weight="balanced")
    model.fit(x.iloc[:a],y[:a]);val=model.predict_proba(x.iloc[a:b])[:,1];test=model.predict_proba(x.iloc[b:])[:,1]
    pr,re,th=precision_recall_curve(y[a:b],val);f=2*pr[:-1]*re[:-1]/np.maximum(1e-12,pr[:-1]+re[:-1]);threshold=float(th[np.argmax(f)])
    truth=y[b:];p=test>=threshold;tp=int((p&truth).sum());fp=int((p&~truth).sum());fn=int((~p&truth).sum());tn=int((~p&~truth).sum())
    out=dict(n=len(y),positive=int(y.sum()),train_n=a,calibration_n=b-a,test_n=len(truth),test_positive=int(truth.sum()),threshold=threshold,tp=tp,fp=fp,fn=fn,tn=tn,precision=tp/max(1,tp+fp),recall=tp/max(1,tp+fn),f1=2*tp/max(1,2*tp+fp+fn),average_precision=average_precision_score(truth,test),roc_auc=roc_auc_score(truth,test),note="OpenML 1597 historical fraud labels, supervised benchmark only; not audit violations or validation of LLM/hybrid; chronological 60/20/20; PCA features supplied by dataset.")
    print("FRAUD_RESULTS",json.dumps(out),flush=True)
    with open("fraud_results.json","w") as f:json.dump(out,f,indent=2)
if __name__=="__main__":main()
