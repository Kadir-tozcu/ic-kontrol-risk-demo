"""V10 data-quality and no-code scenario helpers."""
from __future__ import annotations

import json
import numpy as np
import pandas as pd

from suite.data_dictionary import field_label, normalize_columns

OPERATORS={"Büyüktür":">","Büyük veya eşittir":">=","Küçüktür":"<","Küçük veya eşittir":"<=","Eşittir":"==","Eşit değildir":"!=","İçerir":"contains","Boştur":"empty","Boş değildir":"not_empty"}

def quality_report(data: pd.DataFrame, required_fields: list[str], optional_fields: list[str] | None=None):
    expected=list(required_fields)+list(optional_fields or []);df=normalize_columns(data,expected);issues=[]
    missing=[c for c in required_fields if c not in df.columns]
    for col in missing:issues.append({"Satır":"—","Sütun":field_label(col),"Sorun":"Zorunlu sütun bulunamadı","Düzey":"Hata"})
    for col in required_fields:
        if col not in df:continue
        blank=df[col].isna()|df[col].astype(str).str.strip().isin(["","nan","None"])
        for idx in df.index[blank][:100]:issues.append({"Satır":int(idx)+2,"Sütun":field_label(col),"Sorun":"Zorunlu değer boş","Düzey":"Hata"})
    id_col=next((c for c in ["transaction_id","record_id"] if c in df),None)
    if id_col:
        dup=df[id_col].astype(str).duplicated(keep=False)&df[id_col].notna()
        for idx in df.index[dup][:100]:issues.append({"Satır":int(idx)+2,"Sütun":field_label(id_col),"Sorun":"Mükerrer kayıt numarası","Düzey":"Uyarı"})
    date_col=next((c for c in ["transaction_datetime","event_date"] if c in df),None)
    if date_col:
        bad=pd.to_datetime(df[date_col],errors="coerce",dayfirst=True,format="mixed").isna()&df[date_col].notna()
        for idx in df.index[bad][:100]:issues.append({"Satır":int(idx)+2,"Sütun":field_label(date_col),"Sorun":"Tarih okunamadı","Düzey":"Hata"})
    report=pd.DataFrame(issues,columns=["Satır","Sütun","Sorun","Düzey"])
    errors=int((report["Düzey"]=="Hata").sum()) if len(report) else 0;warnings=int((report["Düzey"]=="Uyarı").sum()) if len(report) else 0
    return df,report,{"rows":len(df),"columns":len(df.columns),"errors":errors,"warnings":warnings,"missing":len(missing)}

def condition_mask(data: pd.DataFrame, condition: dict) -> pd.Series:
    field=condition.get("field","");operator=condition.get("operator","==");value=condition.get("value","")
    if field not in data:return pd.Series(False,index=data.index)
    s=data[field]
    if operator in [">",">=","<","<="]:
        left=pd.to_numeric(s,errors="coerce");right=pd.to_numeric(pd.Series([value]),errors="coerce").iloc[0]
        if pd.isna(right):return pd.Series(False,index=data.index)
        return {">":left>right,">=":left>=right,"<":left<right,"<=":left<=right}[operator]
    if operator=="empty":return s.isna()|s.astype(str).str.strip().eq("")
    if operator=="not_empty":return ~(s.isna()|s.astype(str).str.strip().eq(""))
    if operator=="contains":return s.astype(str).str.contains(str(value),case=False,na=False,regex=False)
    left=s.astype(str).str.strip().str.casefold();right=str(value).strip().casefold()
    truth={"evet":True,"hayır":False,"hayir":False,"true":True,"false":False}
    if right in truth and pd.api.types.is_bool_dtype(s):result=s.eq(truth[right])
    else:result=left.eq(right)
    return ~result if operator=="!=" else result

def scenario_mask(data: pd.DataFrame, conditions: list[dict], logic: str="VE") -> pd.Series:
    masks=[condition_mask(data,c).fillna(False) for c in conditions]
    if not masks:return pd.Series(False,index=data.index)
    result=masks[0]
    for mask in masks[1:]:result=(result|mask) if logic=="VEYA" else (result&mask)
    return result

def apply_dynamic_scenarios(data: pd.DataFrame, scenarios: pd.DataFrame) -> pd.DataFrame:
    result=data.copy()
    if scenarios is None or scenarios.empty:return result
    for _,rule in scenarios.iterrows():
        conditions=json.loads(rule["conditions_json"]);mask=scenario_mask(result,conditions,rule["logic"]);points=int(rule["points"])
        if not mask.any():continue
        result.loc[mask,"risk_score"]=(result.loc[mask,"risk_score"]+points).clip(upper=100)
        reason=f"+{points}: {rule['reason']}";action=str(rule["action"])
        result.loc[mask,"risk_reasons"]=result.loc[mask,"risk_reasons"].map(lambda x:reason if not x or str(x).startswith("Tetiklenen") else f"{x} | {reason}")
        result.loc[mask,"recommended_actions"]=result.loc[mask,"recommended_actions"].map(lambda x:action if not x or str(x).startswith("Standart") else (str(x) if action in str(x) else f"{x} | {action}"))
    result["risk_level"]=np.select([result.risk_score>=70,result.risk_score>=40],["YUKSEK","ORTA"],default="DUSUK")
    return result

def scenario_performance(data: pd.DataFrame) -> pd.DataFrame:
    if data.empty or "risk_reasons" not in data:return pd.DataFrame(columns=["Senaryo","Tetiklenme","Risk doğrulandı","Yanlış alarm","Yanlış alarm oranı"])
    rows=[]
    for reason,count in data.risk_reasons.str.split(r" \| ").explode().value_counts().items():
        mask=data.risk_reasons.str.contains(str(reason),regex=False,na=False);confirmed=int((data.loc[mask,"case_status"]=="Risk dogrulandi").sum()) if "case_status" in data else 0;false=int((data.loc[mask,"case_status"]=="Yanlis alarm").sum()) if "case_status" in data else 0;reviewed=confirmed+false
        rows.append({"Senaryo":str(reason).split(": ",1)[-1],"Tetiklenme":int(count),"Risk doğrulandı":confirmed,"Yanlış alarm":false,"Yanlış alarm oranı":round(false/reviewed*100,1) if reviewed else 0.0})
    return pd.DataFrame(rows)
