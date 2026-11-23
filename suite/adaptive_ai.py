"""Adaptive controls and privacy-conscious OpenAI Responses API integration."""
from __future__ import annotations

import json
import os
import re
import unicodedata
from typing import Any

import pandas as pd

from suite.data_dictionary import field_label
from suite.v10_features import scenario_mask

SENSITIVE_TOKENS=("name","ad_soyad","isim","identity","kimlik","tc","iban","account","hesap_no","email","mail","phone","telefon","address","adres","ip_address","device_id","customer_id","recipient_id","employee_id")
FIELD_SYNONYMS={
    "loan_amount":["kredi tutarı","kredi miktarı","kullandırım tutarı"],"credit_score":["kredi skoru","risk skoru","kredi notu"],"collateral_value":["teminat","teminat değeri"],"debt_ratio":["borç gelir oranı","borç oranı"],"monthly_income":["aylık gelir","müşteri geliri"],
    "journal_amount":["muhasebe tutarı","kayıt tutarı","fiş tutarı","yevmiye tutarı"],"transaction_amount":["işlem tutarı","transfer tutarı","gönderilen tutar"],"amount":["tutar","ödeme tutarı"],"age":["yaş","müşteri yaşı"],"inactivity_days":["hareketsizlik","hareketsizlik günü"],
    "pep":["pep","siyasi nüfuz sahibi"],"missing_documents":["eksik belge","belgesi eksik"],"exception_flag":["politika istisnası","istisna"],"approval_override":["yetki aşımı","onay aşımı","istisnai onay"],"out_of_hours":["mesai dışı","gece işlemi"],"cross_border":["sınır ötesi","yurt dışı"],"transaction_type":["işlem türü","işlem tipi"],
}

def _sensitive(column: str) -> bool:
    folded=str(column).casefold();return any(token in folded for token in SENSITIVE_TOKENS)

def _fold(value: str) -> str:
    value=str(value).translate(str.maketrans("çğıöşüÇĞİÖŞÜ","cgiosuCGIOSU")).casefold()
    return " ".join(re.sub(r"[^a-z0-9]+"," ",unicodedata.normalize("NFKD",value)).split())


def api_available() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def model_name() -> str:
    return os.getenv("OPENAI_MODEL","gpt-5.4-mini")


def dataset_schema(data: pd.DataFrame) -> list[dict[str,Any]]:
    rows=[]
    for column in data.columns:
        series=data[column];examples=["***"] if _sensitive(str(column)) and series.notna().any() else [str(x)[:80] for x in series.dropna().head(3).tolist()]
        rows.append({"field":str(column),"label":field_label(str(column)),"dtype":str(series.dtype),"examples":examples,"missing":int(series.isna().sum())})
    return rows


def dataset_summary(data: pd.DataFrame, max_categories=8) -> dict:
    summary={"row_count":len(data),"column_count":len(data.columns),"risk_distribution":data["risk_level"].value_counts().to_dict() if "risk_level" in data else {},"numeric":{},"categories":{}}
    for column in data.columns:
        series=data[column]
        if _sensitive(str(column)):continue
        if pd.api.types.is_numeric_dtype(series):
            desc=series.describe();summary["numeric"][field_label(column)]={k:round(float(desc[k]),3) for k in ["min","mean","max"] if k in desc and pd.notna(desc[k])}
        elif series.nunique(dropna=True)<=30:
            summary["categories"][field_label(column)]={str(k)[:80]:int(v) for k,v in series.value_counts(dropna=False).head(max_categories).items()}
    return summary

def safe_record(record: dict) -> dict:
    return {field_label(str(key)):value for key,value in record.items() if not _sensitive(str(key)) and not str(key).endswith("_json")}


def _extract_json(text: str) -> dict:
    cleaned=text.strip()
    if cleaned.startswith("```"):cleaned=re.sub(r"^```(?:json)?\s*|\s*```$","",cleaned,flags=re.I|re.S)
    start=cleaned.find("{");end=cleaned.rfind("}")
    if start<0 or end<start:raise ValueError("Yapay zekâ yapılandırılmış bir kontrol üretemedi.")
    return json.loads(cleaned[start:end+1])


def _client():
    from openai import OpenAI
    return OpenAI()


def rule_from_text(request: str, data: pd.DataFrame, process: str, *, filter_only=False) -> dict:
    if not request.strip():raise ValueError("Kontrol talebi boş olamaz.")
    schema=dataset_schema(data)
    if not api_available():return local_rule_from_text(request,schema,process)
    instruction="""Sen bir iç kontrol senaryo tasarım yardımcısısın. Kullanıcının Türkçe talebini SADECE verilen veri alanlarını kullanan güvenli bir kural JSON'una çevir. Uydurma alan kullanma. Çıktı yalnızca JSON olsun. Şema: {name:string, description:string, logic:'VE'|'VEYA', conditions:[{field:string,operator:'>'|'>='|'<'|'<='|'=='|'!='|'contains'|'empty'|'not_empty',value:string}], points:integer 1..50, reason:string, action:string}. Kesin usulsüzlük iddiası kurma; inceleme göstergesi dili kullan."""
    if filter_only:
        instruction += " Bu bir anlık satır filtresidir. Tüm talep tek bir VE/VEYA grubuyla ifade edilemiyorsa, eksik bilgi, belirsiz eşik, toplulaştırma veya dış veri gerekiyorsa conditions boş dön. Soruya eşik veya varsayım ekleme. Talimat olarak sadece bu kuralları izle."
    output_schema={"type":"object","additionalProperties":False,"required":["name","description","logic","conditions","points","reason","action"],"properties":{"name":{"type":"string"},"description":{"type":"string"},"logic":{"type":"string","enum":["VE","VEYA"]},"conditions":{"type":"array","minItems":1,"maxItems":8,"items":{"type":"object","additionalProperties":False,"required":["field","operator","value"],"properties":{"field":{"type":"string"},"operator":{"type":"string","enum":[">",">=","<","<=","==","!=","contains","empty","not_empty"]},"value":{"type":"string"}}}},"points":{"type":"integer","minimum":1,"maximum":50},"reason":{"type":"string"},"action":{"type":"string"}}}
    if filter_only:
        output_schema["properties"]["conditions"]["minItems"] = 0
    response=_client().responses.create(model=model_name(),store=False,input=[{"role":"developer","content":instruction},{"role":"user","content":json.dumps({"process":process,"available_fields":schema,"request":request},ensure_ascii=False,default=str)}],text={"format":{"type":"json_schema","name":"adaptive_control","strict":True,"schema":output_schema}})
    rule=_extract_json(response.output_text)
    if filter_only and not rule.get("conditions"):
        raise ValueError("Bu soru seçili veride filtreye çevrilemiyor. Alanı ve aramak istediğin değeri belirt.")
    validate_rule(rule,{x["field"] for x in schema});return rule


def local_rule_from_text(request: str, schema: list[dict], process: str) -> dict:
    folded=_fold(request);matches=[]
    for item in schema:
        aliases=[item["field"],item["label"]]+FIELD_SYNONYMS.get(item["field"],[]);positions=[folded.find(_fold(alias)) for alias in aliases if _fold(alias) and _fold(alias) in folded]
        if positions:matches.append((min(positions),item))
    matches=sorted(matches,key=lambda x:x[0]);numbers=re.findall(r"\d+(?:[.,]\d+)*",request)
    if not matches:raise ValueError("API bağlantısı kapalı ve talepte veri sütunlarından biri açıkça bulunamadı. Alan adını talebinizde kullanın veya ChatGPT bağlantısını etkinleştirin.")
    conditions=[]
    for index,(position,item) in enumerate(matches[:8]):
        end=matches[index+1][0] if index+1<len(matches) else len(folded);segment=folded[position:end]
        found_numbers=re.findall(r"\d[\d\s.,]*",segment);operator=">=" if any(x in segment for x in ["uzeri","fazla","buyuk","en az"]) else "<=" if any(x in segment for x in ["alti","az","kucuk","en fazla"]) else "!=" if any(x in segment for x in ["degil","olmayan","yok"]) else "=="
        value=re.sub(r"\s","",found_numbers[0]).rstrip(".,").replace(".","").replace(",",".") if found_numbers else "Hayır" if operator=="!=" else "Evet";conditions.append({"field":item["field"],"operator":operator,"value":value})
    field_names=", ".join(field_label(x["field"]) for x in conditions);rule={"name":f"Adaptif {process} kontrolü","description":request,"logic":"VEYA" if " veya " in f" {folded} " else "VE","conditions":conditions,"points":min(40,15+5*len(conditions)),"reason":f"{field_names} alanlarında kullanıcı tanımlı kontrol göstergesi","action":"Eşleşen kayıtları, dayanak belgeleri ve yetki/onay zinciriyle birlikte incele"};validate_rule(rule,{x["field"] for x in schema});return rule


def validate_rule(rule: dict, allowed_fields: set[str]) -> None:
    if rule.get("logic") not in ["VE","VEYA"]:raise ValueError("Geçersiz kural mantığı.")
    conditions=rule.get("conditions") or []
    if not 1<=len(conditions)<=8:raise ValueError("Kontrol 1-8 koşul içermelidir.")
    allowed_ops={">",">=","<","<=","==","!=","contains","empty","not_empty"}
    for condition in conditions:
        if condition.get("field") not in allowed_fields:raise ValueError(f"Veri setinde bulunmayan alan: {condition.get('field')}")
        if condition.get("operator") not in allowed_ops:raise ValueError("Desteklenmeyen karşılaştırma işlemi.")
    rule["points"]=max(1,min(50,int(rule.get("points",20))))


def run_rule(data: pd.DataFrame, rule: dict) -> pd.Series:
    validate_rule(rule,set(data.columns));return scenario_mask(data,rule["conditions"],rule["logic"]).fillna(False)


def ask_dataset(question: str, data: pd.DataFrame, process: str, case_context: dict|None=None) -> str:
    if not api_available():return "ChatGPT bağlantısı henüz etkin değil. Sunucuda OPENAI_API_KEY tanımlandığında bu alandan veri özeti ve vaka hakkında anlık soru sorabilirsiniz."
    context={"process":process,"dataset_summary":dataset_summary(data),"case_context":case_context or {}}
    instruction="""Sen bir iç kontrol analiz asistanısın. Yalnızca verilen özet ve vaka bağlamını kullan. Görmediğin ham veri hakkında varsayım yapma. Bulguyu kesin usulsüzlük olarak sunma. Kısa, açık Türkçe cevap ver; gerekiyorsa kontrol adımlarını numaralandır. Kişisel veri isteme."""
    response=_client().responses.create(model=model_name(),store=False,input=[{"role":"developer","content":instruction},{"role":"user","content":json.dumps({"question":question,"context":context},ensure_ascii=False,default=str)}])
    return response.output_text


def read_scenario_text(text, fields, limit=20):
    """Parse the studio's line-based notation without sending data to an API."""
    from difflib import get_close_matches
    from math import isfinite

    if len(text) > 12000:
        return {}, [], ["Bir senaryo metni en fazla 12.000 karakter olabilir."]
    metadata = {"ad":"name", "senaryo adi":"name", "aciklama":"desc", "puan":"points",
                "risk puani":"points", "gerekce":"reason", "risk gerekcesi":"reason",
                "aksiyon":"action", "onerilen kontrol aksiyonu":"action", "baglanti":"logic"}
    operators = {"=":"==", "==":"==", "!=":"!=", ">":">", "<":"<", ">=":">=", "<=":"<=",
                 "≥":">=", "≤":"<=", "en az":">=", "en fazla":"<=", "icerir":"contains",
                 "esittir":"==", "esit degil":"!=", "bos":"empty", "bos degil":"not_empty"}
    expression = re.compile(r"^(.+?)\s*(>=|<=|!=|==|[<>=≥≤]|\s+(?:en az|en fazla|içerir|icerir|eşittir|esittir|eşit değil|esit degil|boş değil|bos degil|boş|bos)\b)\s*(.*?)$", re.I)
    aliases = {}
    for field in fields:
        for alias in (field, field_label(field), *FIELD_SYNONYMS.get(field, [])):
            aliases.setdefault(_fold(alias), set()).add(field)
    details, conditions, errors = {}, [], []
    for line_no, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        try:
            label, separator, value = line.partition(":")
            prop = metadata.get(_fold(label)) if separator else None
            if prop:
                value = value.strip()
                if prop in details or not value:
                    raise ValueError("Başlık tekrarlanmış veya değeri boş.")
                if prop == "points":
                    if not re.fullmatch(r"[0-9]{1,3}", value) or not 1 <= int(value) <= 100:
                        raise ValueError("Risk puanı 1 ile 100 arasında tam sayı olmalı.")
                    value = int(value)
                if prop == "logic":
                    value = value.upper()
                    if value not in ("VE","VEYA"):
                        raise ValueError("Bağlantı için VE veya VEYA yazın.")
                details[prop] = value
                continue
            if len(line) > 500:
                raise ValueError("Koşul satırı en fazla 500 karakter olabilir.")
            match = expression.fullmatch(line)
            if not match:
                raise ValueError("Alan, karşılaştırma ve değer yazın. Her koşulu ayrı satıra girin.")
            label, token, value = (part.strip() for part in match.groups())
            matches = [label] if label in fields else aliases.get(_fold(label), set())
            if len(matches) != 1:
                suggestions = get_close_matches(_fold(label), aliases, n=2)
                choices = sorted({key for alias in suggestions for key in aliases[alias]})
                raise ValueError("Alan tanınmadı veya birden fazla sütuna uyuyor. Teknik adı kullanın." +
                                 (" Yakın alanlar: " + ", ".join(choices) if choices else ""))
            field = next(iter(matches))
            op = operators[token if token in operators else _fold(token)]
            if op in ("empty","not_empty"):
                if value:
                    raise ValueError("Boşluk kontrolünden sonra değer yazılmaz.")
            elif not value:
                raise ValueError("Karşılaştırma değeri eksik.")
            elif op in (">","<",">=","<="):
                if not re.fullmatch(r"[+-]?(?:[0-9]+|[0-9]{1,3}(?:\.[0-9]{3})+)(?:,[0-9]+)?",value):
                    raise ValueError("Sayısal eşiği 250000, 250.000 veya 0,60 biçiminde yazın.")
                value = value.replace(".","").replace(",",".")
                if not isfinite(float(value)):
                    raise ValueError("Sayısal eşik çok büyük.")
            conditions.append(dict(field=field,operator=op,value=value))
        except ValueError as error:
            errors.append(f"{line_no}. satır: {error}")
    if len(conditions) > limit:
        errors.append(f"En fazla {limit} koşul girilebilir.")
    return details, conditions, errors


def instant_filter(question, data, process):
    """Interpret a one-off filter. Only column definitions are needed for remote interpretation."""
    question = question.strip()
    if not question or len(question) > 2000:
        raise ValueError("1 ile 2.000 karakter arasında bir kontrol sorusu yaz.")
    body = re.sub(r"\s+(?:(?:olan|olanları)\s+)?(?:(?:işlemleri|kayıtları|transferleri|hesapları)\s+)?(?:göster|listele|bul|tara|kaç tane var)\s*[?.!]*$", "", question, flags=re.I).strip()
    body = re.sub(r"(\d+)\s+yaş\s+ve\s+(?:üzeri(?:ndeki)?|üstü(?:ndeki)?)", r"Müşteri yaşı >= \1", body, flags=re.I)
    body = re.sub(r"(?<=\d)\s+yaşında(?:ki)?", " yaşında", body, flags=re.I)
    pieces = re.split(r"\s+(veya|ya da|ve)\s+|\n+", body, flags=re.I)
    clauses = [part.strip() for part in pieces[::2] if part.strip()]
    joins = {("VE" if word.lower()=="ve" else "VEYA") for word in pieces[1::2] if word}
    logic = next(iter(joins), "VE")
    normalized = []
    for clause in clauses:
        # Common Turkish phrases with the threshold before the field or operator.
        clause = re.sub(r"^(\d+)\s+yaş(?:ın)?\s+(?:üzeri(?:ndeki)?|üstü(?:ndeki)?|üstünde)$", r"Müşteri yaşı > \1", clause, flags=re.I)
        clause = re.sub(r"^(\d+) yaşında$", r"Müşteri yaşı = \1", clause, flags=re.I)
        clause = re.sub(r"^(?:en az\s+)?(\d+)\s+(gün(?:dür)?|yıl(?:dır)?)\s+(?:işlem görmeyen|hareketsiz)(?: olan)?$",
                        lambda m: f"Hareketsizlik günü >= {int(m[1]) * (365 if m[2].lower().startswith('yıl') else 1)}", clause, flags=re.I)
        risk = re.fullmatch(r"(yüksek|orta|düşük)\s+riskli(?: olan)?", clause, flags=re.I)
        if risk:
            clause = "risk_level = " + {"yuksek":"YUKSEK","orta":"ORTA","dusuk":"DUSUK"}[_fold(risk[1])]
        clause = re.sub(r"^(.+?)\s+([\d.,]+)\s*(?:TL)?(?:['’]?(?:den|dan|ten|tan|nin|nın|in|ın))?\s+(aşan|geçen|fazla|üzerinde(?:ki)?|altında(?:ki)?|az)(?: olan)?$",
                        lambda m: f"{m[1]} {'<' if m[3].lower() in ('altında','altındaki','az') else '>'} {m[2]}", clause, flags=re.I)
        clause = re.sub(r"(\d)\s*TL$", r"\1", clause, flags=re.I)
        normalized.append(clause)
    _, terms, errors = read_scenario_text("\n".join(normalized), data.columns)
    if len(joins) <= 1 and not errors and terms and len(terms) == len(clauses):
        return terms, logic
    if len(joins) > 1:
        raise ValueError("VE ve VEYA birlikte kullanıldığında kapsam belirsiz. İki ayrı tarama çalıştır.")
    if not api_available():
        raise ValueError("Soruyu seçili veri alanlarıyla eşleştiremedim. Örneğin “Risk Skoru en az 70 olan işlemleri göster” yazabilir veya alan listesine bakabilirsin.")
    rule = rule_from_text(question, data.iloc[:0], process, filter_only=True)
    return rule["conditions"], rule["logic"]
