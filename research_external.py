import io,zipfile,hashlib,urllib.request,json
import pandas as pd
from research_validation import validate
URL="https://archive.ics.uci.edu/static/public/573/south+german+credit+update.zip"
def main():
    with urllib.request.urlopen(URL,timeout=90) as r: raw=r.read()
    z=zipfile.ZipFile(io.BytesIO(raw))
    name=next(n for n in z.namelist() if n.lower().endswith("southgermancredit.asc"))
    d=pd.read_csv(io.BytesIO(z.read(name)),sep=r"\s+")
    assert len(d)==1000 and set(d.kredit.unique())=={0,1}
    assert int((d.kredit==0).sum())==300
    fields=["laufzeit","hoehe","rate","laufkont","sparkont","moral","bishkred"]
    d=d[fields+["kredit"]].copy()
    d["status"]=d.kredit.map({0:"B",1:"A"})
    assert not d[fields].isna().any().any()
    print("EXTERNAL_DATA",json.dumps({"n":len(d),"positive":300,"source":URL,"fields":fields}),flush=True)
    validate(d,{"n":1000,"positive":300},{"zip":hashlib.sha256(raw).hexdigest()},fields=fields,prefix="german",label="Independent dataset methodological replication with local calibration, not frozen Berka model transfer; oversampled bad credits, historical data, transformed amount")
if __name__=="__main__":main()
