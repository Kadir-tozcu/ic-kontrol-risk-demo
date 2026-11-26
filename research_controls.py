"""Real-data rule reproduction; NOT labelled fraud or compliance detection."""
import io,json,time,hashlib,urllib.request
import numpy as np
import pandas as pd
from openai import OpenAI

BASE="https://raw.githubusercontent.com/jlacko/berka-dataset/master/"
def load(name):
    with urllib.request.urlopen(BASE+name+".asc",timeout=120) as r: raw=r.read()
    return pd.read_csv(io.BytesIO(raw),sep=";",encoding="latin1",low_memory=False),hashlib.sha256(raw).hexdigest()
def date(s):
    return pd.to_datetime(s.astype(str),format="%y%m%d",errors="raise")
def main():
    tables={}; hashes={}
    for name in ("trans","loan","client","disp","account","order","card","district"):
        tables[name],hashes[name]=load(name)
    t=tables["trans"].sort_values(["account_id","date","trans_id"]).copy()
    t["dt"]=date(t.date);t["gap_days"]=t.groupby("account_id").dt.diff().dt.days.fillna(0)
    t["outgoing_transfer"]=(t.operation=="PREVOD NA UCET").astype(int)
    c=tables["client"].copy()
    b=c.birth_number.astype(str).str.zfill(6)
    month=b.str[2:4].astype(int);month=month.where(month<=50,month-50)
    c["birth"]=pd.to_datetime(dict(year=1900+b.str[:2].astype(int),month=month,day=b.str[4:6].astype(int)),errors="raise")
    owners=tables["disp"].query("type == 'OWNER'")[["account_id","client_id"]].merge(c[["client_id","birth"]],on="client_id",validate="many_to_one")
    t=t.merge(owners[["account_id","birth"]],on="account_id",how="left",validate="many_to_one")
    t["age"]=t.dt.dt.year-t.birth.dt.year-((t.dt.dt.month*100+t.dt.dt.day)<(t.birth.dt.month*100+t.birth.dt.day)).astype(int)
    assert len(t)==1056320
    l=tables["loan"].copy()
    l["repayment_total"]=l.duration*l.payments
    l["repayment_difference"]=(l.amount-l.repayment_total).abs()
    l["invalid_terms"]=((l.amount<=0)|(l.duration<=0)|(l.payments<=0)).astype(int)
    l["dt"]=date(l.date)
    accounts=tables["account"][["account_id","date"]].rename(columns={"date":"account_date"})
    l=l.merge(accounts,on="account_id",how="left",validate="many_to_one")
    l["before_account_open"]=(l.dt<date(l.account_date)).astype(int)
    # Reference thresholds are transparent research conventions, not bank policy.
    transfer=t[t.outgoing_transfer==1].copy()
    threshold=float(transfer.amount.quantile(.99))
    high=float(t.amount.quantile(.99))
    scenarios=[
      ("negative_balance",t,[("balance","<",0)]),
      ("dormant_90",t,[("gap_days",">=",90)]),
      ("dormant_365",t,[("gap_days",">=",365)]),
      ("high_amount",t,[("amount",">=",high)]),
      ("outgoing_transfer_high",transfer,[("amount",">=",threshold)]),
      ("older_owner_high_transfer",transfer,[("age",">=",65),("amount",">=",threshold)]),
      ("loan_repayment_arithmetic",l,[("repayment_difference",">",1)]),
      ("loan_invalid_terms",l,[("invalid_terms","==",1)]),
      ("loan_before_account_open",l,[("before_account_open","==",1)]),
    ]
    def mask(d,conds):
        p=np.ones(len(d),bool)
        for field,op,v in conds:
            a=d[field].to_numpy()
            p &= {">=":lambda:a>=v,">":lambda:a>v,"<":lambda:a<v,"==":lambda:a==v}[op]()
        return p
    results=[];protocol=[];client=OpenAI(timeout=60,max_retries=0)
    for name,d,conds in scenarios:
        truth=mask(d,conds); fields=sorted({x[0] for x in conds})
        options=[dict(id=i,field=f,op=o,threshold=float(v)) for i,(f,o,v) in enumerate(conds)]
        # Also include distractors, to measure rule translation rather than fraud prediction.
        options += [dict(id=len(options)+i,field=f,op=">=",threshold=float(d[f].median())) for i,f in enumerate(fields)]
        schema={"type":"object","properties":{"ids":{"type":"array","items":{"type":"integer","enum":list(range(len(options)))}}},"required":["ids"],"additionalProperties":False}
        chosen=None;err=None
        try:
            resp=client.responses.create(model="gpt-4.1-mini",store=False,max_output_tokens=200,text={"format":{"type":"json_schema","name":"control_rule","strict":True,"schema":schema}},input="Translate exactly this AND control rule into candidate IDs. Do not change thresholds or operators. Rule: "+json.dumps(conds)+" Candidates: "+json.dumps(options))
            ids=json.loads(resp.output_text)["ids"]
            if not ids or len(set(ids))!=len(ids):raise ValueError("invalid ids")
            chosen=[(options[i]["field"],options[i]["op"],options[i]["threshold"]) for i in ids]
        except Exception as e:err=type(e).__name__
        protocol.append(dict(scenario=name,reference=conds,llm=chosen,error=err))
        for method in ("sample","single","algorithmic_reference","llm_translation"):
            if method=="llm_translation" and chosen is None:continue
            start=time.perf_counter(); coverage=1.
            if method=="sample":
                p=np.zeros(len(d),bool);ix=np.random.default_rng(42).choice(len(d),max(1,len(d)//20),replace=False);p[ix]=mask(d.iloc[ix],conds);coverage=len(ix)/len(d)
            elif method=="single":p=mask(d,conds[:1])
            elif method=="algorithmic_reference":p=mask(d,conds)
            else:p=mask(d,chosen)
            tp=int((p&truth).sum());fp=int((p&~truth).sum());fn=int((~p&truth).sum());tn=int((~p&~truth).sum())
            results.append(dict(scenario=name,method=method,n=len(d),reference_positive=int(truth.sum()),coverage=coverage,tp=tp,fp=fp,fn=fn,tn=tn,precision=tp/(tp+fp) if tp+fp else None,recall=tp/(tp+fn) if tp+fn else None,f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None,scan_seconds=time.perf_counter()-start))
    unavailable={"credit_authority_limit":"No bank approval matrix or delegated limits","collateral_adequacy":"No collateral type/value or policy LTV","unauthorized_transaction":"No approval logs or maker-checker fields","kyc_masak":"No identity verification, sanctions/PEP, beneficial ownership or reporting fields","loan_disbursement_conditions":"No approved contractual conditions or evidence; only arithmetic/date checks tested"}
    d=pd.DataFrame(results);d.to_csv("control_results.csv",index=False)
    with open("control_protocol.json","w") as f:json.dump(dict(hashes=hashes,scenarios=protocol,unavailable=unavailable,note="Rule reproduction on real records, reference labels defined by rules; not observed fraud, compliance or credit defaults. Owner age is not evidence of suspicious activity."),f,indent=2)
    print("CONTROL_RESULTS",d.to_json(orient="records"),flush=True)
    print("CONTROL_UNAVAILABLE",json.dumps(unavailable),flush=True)
if __name__=="__main__":main()
