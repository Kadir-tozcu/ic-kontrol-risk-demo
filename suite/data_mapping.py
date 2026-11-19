"""Institution-friendly column matching and common value conversions."""
from __future__ import annotations

import re
from difflib import SequenceMatcher

import pandas as pd

from suite.data_dictionary import field_label, normalize_columns


COMMON_ALIASES = {
    "transaction_id":["islem no","islem numarasi","trx id","transaction no"],
    "record_id":["kayit no","fis no","belge no","evrak no","record no"],
    "customer_id":["musteri no","musteri numarasi","customer no","client id"],
    "transaction_datetime":["islem tarihi","islem zamani","trx date","tarih saat"],
    "event_date":["kayit tarihi","fis tarihi","belge tarihi","muhasebe tarihi"],
    "transaction_amount":["islem tutari","transfer tutari","trx amount","bedel"],
    "journal_amount":["muhasebe tutari","kayit tutari","fis tutari","borc tutari","alacak tutari"],
    "loan_amount":["kredi tutari","kullandirim tutari","loan amount"],
    "amount":["tutar","islem bedeli","amount"],
    "employee_id":["personel no","kullanici no","sicil no","operator id"],
}


def _key(value) -> str:
    table=str.maketrans("çğıöşüÇĞİÖŞÜ","cgiosuCGIOSU")
    return re.sub(r"[^a-z0-9]+"," ",str(value).translate(table).casefold()).strip()


def suggest_mapping(columns, expected_fields, saved_mapping=None) -> pd.DataFrame:
    expected=list(dict.fromkeys(expected_fields));saved=saved_mapping or {};used=set();rows=[]
    normalized_probe=normalize_columns(pd.DataFrame(columns=list(columns)),expected).columns.tolist()
    for source,probe in zip(columns,normalized_probe):
        target="";confidence=0;method="Eşleşme bulunamadı"
        if str(source) in saved and saved[str(source)] in expected:
            target=saved[str(source)];confidence=100;method="Kayıtlı kurum eşleştirmesi"
        elif probe in expected:
            target=probe;confidence=100;method="Otomatik tam eşleşme"
        else:
            source_key=_key(source);best=(0,"")
            for field in expected:
                candidates=[field,field_label(field)]+COMMON_ALIASES.get(field,[])
                score=max(SequenceMatcher(None,source_key,_key(candidate)).ratio() for candidate in candidates)
                if score>best[0]:best=(score,field)
            if best[0]>=0.72:
                target=best[1];confidence=round(best[0]*100);method="Akıllı öneri"
        if target in used:target="";confidence=0;method="Aynı hedef alan daha önce kullanıldı"
        if target:used.add(target)
        rows.append({"Kurumdaki Sütun":str(source),"Sistemdeki Karşılığı":target,"Türkçe Alan":field_label(target) if target else "Seçilmedi","Güven (%)":confidence,"Eşleştirme Yöntemi":method})
    return pd.DataFrame(rows)


def mapping_dict(mapping_table: pd.DataFrame) -> dict[str,str]:
    return {str(row["Kurumdaki Sütun"]):str(row["Sistemdeki Karşılığı"]) for _,row in mapping_table.iterrows() if str(row.get("Sistemdeki Karşılığı","")).strip()}


def apply_mapping(data: pd.DataFrame, mapping: dict[str,str], expected_fields) -> pd.DataFrame:
    result=data.rename(columns=mapping).copy()
    result=normalize_columns(result,expected_fields)
    bool_values={"evet":True,"e":True,"yes":True,"y":True,"true":True,"1":True,"hayir":False,"hayır":False,"h":False,"no":False,"n":False,"false":False,"0":False}
    date_fields={"transaction_datetime","event_date","transaction_date"}
    id_fields={field for field in result.columns if field.endswith("_id") or field in {"transaction_id","record_id","customer_id"}}
    for field in result.columns:
        if field in date_fields:
            result[field]=pd.to_datetime(result[field],errors="coerce",dayfirst=True,format="mixed")
        elif field in id_fields:
            result[field]=result[field].map(lambda x:"" if pd.isna(x) else str(x).strip())
        elif pd.api.types.is_object_dtype(result[field]) or pd.api.types.is_string_dtype(result[field]):
            cleaned=result[field].astype(str).str.strip();folded=cleaned.map(_key)
            nonblank=folded[folded.ne("") & folded.ne("nan")]
            if len(nonblank) and nonblank.isin(bool_values).all():result[field]=folded.map(bool_values)
            elif len(nonblank) and any(token in field for token in ("amount","count","days","hours","age","ratio","score","value","income","limit","total","bps","salary","loss","balance")):
                numeric_like=cleaned.str.replace(r"[₺$€£\s]","",regex=True).str.match(r"^-?[\d.,]+$")
                if numeric_like[cleaned.ne("") & cleaned.ne("nan")].all():
                    def parse_number(value):
                        if pd.isna(value) or str(value).strip()=="":return None
                        text=re.sub(r"[₺$€£\s]","",str(value))
                        if "," in text and "." in text:text=text.replace(".","").replace(",",".") if text.rfind(",")>text.rfind(".") else text.replace(",","")
                        elif "," in text:text=text.replace(",",".")
                        elif text.count(".")>1:text=text.replace(".","")
                        return pd.to_numeric(text,errors="coerce")
                    result[field]=result[field].map(parse_number)
    return result


def missing_required(mapping_table: pd.DataFrame, required_fields) -> list[str]:
    mapped=set(mapping_dict(mapping_table).values())
    return [field for field in required_fields if field not in mapped]
