import os,time,json,urllib.request,tempfile,platform
import pandas as pd
from pyspark.sql import SparkSession,functions as F
def main():
    with tempfile.TemporaryDirectory() as tmp:
        path=tmp+"/trans.asc"
        urllib.request.urlretrieve("https://raw.githubusercontent.com/jlacko/berka-dataset/master/trans.asc",path)
        raw=pd.read_csv(path,sep=";",encoding="latin1",low_memory=False)[["amount","balance"]]
        assert len(raw)==1056320
        spark=SparkSession.builder.master("local[2]").appName("bank-control-benchmark").config("spark.ui.enabled","false").config("spark.sql.shuffle.partitions","4").getOrCreate()
        spark.sparkContext.setLogLevel("ERROR")
        rows=[]
        for n in (100000,500000,1056320,5000000,10000000):
            d=pd.concat([raw]*((n+len(raw)-1)//len(raw)),ignore_index=True).iloc[:n]
            threshold=float(d.amount.quantile(.99))
            csv=tmp+"/bench.csv";d.to_csv(csv,index=False)
            for trial in range(3):
                start=time.perf_counter();p=pd.read_csv(csv);a=int((p.balance<0).sum());b=int((p.amount>=threshold).sum());pt=time.perf_counter()-start
                start=time.perf_counter();s=spark.read.schema("amount double,balance double").option("header",True).csv(csv)
                z=s.agg(F.count("*").alias("n"),F.sum(F.when(F.col("balance")<0,1).otherwise(0)).alias("negative"),F.sum(F.when(F.col("amount")>=threshold,1).otherwise(0)).alias("high")).first();st=time.perf_counter()-start
                assert (z.n,z.negative,z.high)==(n,a,b)
                rows.append(dict(n=n,trial=trial,negative=a,high=b,pandas_seconds=pt,spark_seconds=st,replicated=n>len(raw)))
            print("SPARK_PROGRESS",n,flush=True)
        spark.stop()
        pd.DataFrame(rows).to_csv("spark_results.csv",index=False)
        print("SPARK_RESULTS",json.dumps(rows),flush=True)
        with open("spark_protocol.json","w") as f:json.dump(dict(mode="local[2], single host, not multi-node",timing="CSV read plus two aggregations, Spark session startup excluded, file cache uncontrolled",cpu=os.cpu_count(),platform=platform.platform(),memory="not measured",replication="above original rows repeated, not new real transactions"),f)
if __name__=="__main__":main()
