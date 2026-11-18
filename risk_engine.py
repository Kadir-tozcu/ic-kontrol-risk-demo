"""Aciklanabilir, kural tabanli ic kontrol risk motoru."""

from __future__ import annotations

import json
import re
from typing import Any

import numpy as np
import pandas as pd
from data_dictionary import field_label, normalize_columns


REQUIRED_COLUMNS = [
    "transaction_id", "customer_id", "transaction_datetime", "inactivity_days", "age",
    "transaction_amount", "historical_avg_amount", "new_recipient",
    "transaction_hour", "transaction_count_after_reactivation",
]
OPTIONAL_COLUMNS = [
    "recipient_id", "account_balance_before", "device_id", "ip_address", "channel",
    "currency", "destination_country", "transaction_status", "original_transaction_id",
    "employee_id", "new_currency_or_country",
]


def _truthy(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower().isin(
        {"true", "1", "yes", "evet", "e", "y"}
    )


def _parse_number(value: Any) -> float:
    """Accept Excel numbers and common Turkish/international number formats."""
    if pd.isna(value):
        return np.nan
    if isinstance(value, (int, float, np.integer, np.floating)):
        return float(value)

    text = str(value).strip()
    if not text:
        return np.nan
    # Remove currency labels, spaces and other presentation characters.
    text = text.replace("\u00a0", "").replace(" ", "")
    text = re.sub(r"(?i)(TRY|TL|₺)", "", text)
    text = text.rstrip("+")
    text = re.sub(r"[^0-9,.-]", "", text)
    if not text or text in {"-", ".", ","}:
        return np.nan

    if "," in text and "." in text:
        # The rightmost separator is the decimal separator.
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        parts = text.split(",")
        if len(parts) > 2 or (len(parts) == 2 and len(parts[1]) == 3):
            text = "".join(parts)
        else:
            text = text.replace(",", ".")
    elif "." in text:
        parts = text.split(".")
        if len(parts) > 2 or (len(parts) == 2 and len(parts[1]) == 3):
            text = "".join(parts)

    try:
        return float(text)
    except ValueError:
        return np.nan


def validate_input(data: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalize an uploaded transaction table."""
    df = normalize_columns(data, REQUIRED_COLUMNS + OPTIONAL_COLUMNS)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError("Eksik zorunlu sütunlar: " + ", ".join(field_label(c) for c in missing))

    df["transaction_datetime"] = pd.to_datetime(df["transaction_datetime"], errors="coerce", dayfirst=True, format="mixed")
    bad_dates = df["transaction_datetime"].isna()
    if bad_dates.any():
        examples = ", ".join(df.loc[bad_dates, "transaction_id"].astype(str).head(5))
        raise ValueError(
            "transaction_datetime alaninda gecersiz veya bos tarih var. "
            f"Ornek islem no: {examples}. Ornek tarih: 2026-08-15 10:34:27"
        )

    numeric = [
        "inactivity_days", "age", "transaction_amount", "historical_avg_amount",
        "transaction_hour", "transaction_count_after_reactivation",
    ]
    original_numeric = df[numeric].copy()
    for col in numeric:
        df[col] = df[col].map(_parse_number)
    bad_cells = df[numeric].isna()
    if bad_cells.any(axis=None):
        details = []
        field_labels = {
            "inactivity_days": "inactivity_days / hareketsiz gun sayisi",
            "age": "age / musteri yasi",
            "transaction_amount": "transaction_amount / islem tutari",
            "historical_avg_amount": "historical_avg_amount / gecmis ortalama tutar",
            "transaction_hour": "transaction_hour / islem saati",
            "transaction_count_after_reactivation": "transaction_count_after_reactivation / yeniden aktivasyon sonrasi islem adedi",
        }
        for row_idx, col_idx in zip(*np.where(bad_cells.to_numpy())):
            tx_id = str(df.iloc[row_idx]["transaction_id"])
            col_name = numeric[col_idx]
            raw = original_numeric.iloc[row_idx, col_idx]
            shown = "bos" if pd.isna(raw) or str(raw).strip() == "" else repr(str(raw))
            details.append(f"{tx_id} → {field_labels[col_name]} ({shown})")
            if len(details) == 8:
                break
        raise ValueError(
            "Bazi sayisal hucreler okunamadi: " + "; ".join(details)
            + ". Bos hucreleri doldurun; tutarlari 250000, 250.000 veya 250.000,50 biciminde yazabilirsiniz."
        )
    if (df["transaction_amount"] < 0).any() or (df["historical_avg_amount"] < 0).any():
        raise ValueError("Tutar alanlari negatif olamaz.")
    if (~df["transaction_hour"].between(0, 23)).any():
        raise ValueError("transaction_hour 0 ile 23 arasinda olmalidir.")
    if (~df["age"].between(18, 110)).any():
        raise ValueError("age 18 ile 110 arasinda olmalidir.")
    df["new_recipient"] = _truthy(df["new_recipient"])
    defaults = {
        "recipient_id": "", "account_balance_before": np.nan, "device_id": "",
        "ip_address": "", "channel": "Bilinmiyor", "currency": "TRY",
        "destination_country": "TR", "transaction_status": "Tamamlandi",
        "original_transaction_id": "", "employee_id": "", "new_currency_or_country": False,
    }
    for col, default in defaults.items():
        if col not in df.columns:
            df[col] = default
    df["account_balance_before"] = df["account_balance_before"].map(_parse_number)
    df["new_currency_or_country"] = _truthy(df["new_currency_or_country"])
    for col in ["recipient_id", "device_id", "ip_address", "channel", "currency", "destination_country", "transaction_status", "original_transaction_id", "employee_id"]:
        df[col] = df[col].fillna("").astype(str).str.strip()
    return df


def score_transactions(data: pd.DataFrame, rules: dict[str, Any] | None = None, custom_rules: list[dict[str, Any]] | None = None) -> pd.DataFrame:
    """Score every transaction from 0 to 100 and explain every triggered rule."""
    from platform_store import DEFAULT_RULES
    cfg = {**DEFAULT_RULES, **(rules or {})}
    df = validate_input(data)
    n = len(df)
    score = np.zeros(n, dtype=int)
    reasons: list[list[str]] = [[] for _ in range(n)]
    actions: list[list[str]] = [[] for _ in range(n)]

    def apply(mask: pd.Series, points: int, reason: str, action: str) -> None:
        nonlocal score
        active = mask.fillna(False).to_numpy(dtype=bool)
        score[active] += points
        for idx in np.flatnonzero(active):
            reasons[idx].append(f"+{points}: {reason}")
            if action not in actions[idx]:
                actions[idx].append(action)

    inactive = df["inactivity_days"] >= cfg["inactivity_days_threshold"]
    senior = df["age"] >= cfg["senior_age"]
    very_senior = df["age"] >= cfg["very_senior_age"]
    avg_safe = df["historical_avg_amount"].replace(0, np.nan)
    ratio = (df["transaction_amount"] / avg_safe).replace([np.inf, -np.inf], np.nan)
    high_absolute = df["transaction_amount"] >= cfg["high_amount"]
    off_hours = (df["transaction_hour"] < cfg["off_hours_end"]) | (df["transaction_hour"] >= cfg["off_hours_start"])
    repeated = df["transaction_count_after_reactivation"] >= cfg["reactivation_count"]
    df["transaction_date"] = df["transaction_datetime"].dt.date
    daily_group = df.groupby(["customer_id", "transaction_date"], dropna=False)["transaction_amount"]
    df["daily_transfer_total"] = daily_group.transform("sum").round(2)
    df["daily_transaction_count"] = daily_group.transform("size").astype(int)
    daily_volume_and_count = (df["daily_transfer_total"] >= cfg["daily_amount"]) & (df["daily_transaction_count"] >= cfg["daily_count"])
    senior_daily_million = (df["age"] > cfg["elderly_daily_age"]) & (df["daily_transfer_total"] >= cfg["elderly_daily_amount"])

    # Extended scenario library. Calendar-day grouping keeps the logic auditable.
    near_limit = df["transaction_amount"].between(450_000, 499_999.99)
    near_limit_count = near_limit.astype(int).groupby([df["customer_id"], df["transaction_date"]]).transform("sum")
    split_transactions = near_limit & (near_limit_count >= 3)
    recipient_valid = df["recipient_id"].ne("")
    recipient_group = [df["customer_id"], df["recipient_id"], df["transaction_date"]]
    recipient_count = recipient_valid.astype(int).groupby(recipient_group).transform("sum")
    recipient_total = df["transaction_amount"].where(recipient_valid, 0).groupby(recipient_group).transform("sum")
    serial_recipient = recipient_valid & (recipient_count >= 5) & (recipient_total >= 750_000)
    first_high_recipient = df["new_recipient"] & (df["transaction_amount"] >= 500_000)
    night = df["transaction_hour"].between(0, 6)
    two_hour_bucket = df["transaction_datetime"].dt.floor("2h")
    night_count = night.astype(int).groupby([df["customer_id"], two_hour_bucket]).transform("sum")
    night_total = df["transaction_amount"].where(night, 0).groupby([df["customer_id"], two_hour_bucket]).transform("sum")
    night_series = night & (night_count >= 3) & (night_total >= 250_000)
    drain_ratio = df["transaction_amount"] / df["account_balance_before"].replace(0, np.nan)
    account_drain = inactive & (drain_ratio >= 0.80)
    recipient_day_group = [df["recipient_id"], df["transaction_date"]]
    distinct_senders = df["customer_id"].where(recipient_valid).groupby(recipient_day_group).transform("nunique")
    incoming_total = df["transaction_amount"].where(recipient_valid, 0).groupby(recipient_day_group).transform("sum")
    common_recipient = recipient_valid & (distinct_senders >= 10) & (incoming_total >= 2_000_000)
    profile_mismatch = df["new_currency_or_country"] & (df["transaction_amount"] >= 250_000)
    cancellation_redirect = df["original_transaction_id"].ne("") & df["transaction_status"].str.lower().isin(["tamamlandi", "completed"])
    access_key = df["device_id"].where(df["device_id"].ne(""), df["ip_address"])
    access_valid = access_key.ne("")
    access_customers = df["customer_id"].where(access_valid).groupby([access_key, df["transaction_date"]]).transform("nunique")
    shared_access = access_valid & (access_customers >= 5)
    employee_valid = df["employee_id"].ne("")
    customer_total_30 = employee_valid.astype(int).groupby(df["customer_id"]).transform("sum")
    employee_customer_count = employee_valid.astype(int).groupby([df["employee_id"], df["customer_id"]]).transform("sum")
    employee_concentration = employee_valid & (employee_customer_count > 10) & ((employee_customer_count / customer_total_30.replace(0, np.nan)) >= 0.70)

    apply(inactive, cfg["inactivity_points"], f"Hesap en az {cfg['inactivity_days_threshold']} gundur hareketsiz", "Musteri iradesini bagimsiz kanaldan dogrula")
    apply(senior & ~very_senior, cfg["senior_points"], f"Musteri {cfg['senior_age']}-{cfg['very_senior_age']-1} yas bandinda", "Yasli musteri suistimali gostergelerini incele")
    apply(very_senior, cfg["very_senior_points"], f"Musteri {cfg['very_senior_age']} yas veya uzerinde", "Yasli musteri suistimali gostergelerini incele")
    apply(high_absolute, cfg["high_amount_points"], f"Islem tutari {cfg['high_amount']:,.0f} TL veya uzerinde", "Islemin ekonomik amacini ve belge destegini kontrol et")
    apply(ratio >= cfg["ratio_high"], cfg["ratio_high_points"], f"Tutar tarihsel ortalamanin en az {cfg['ratio_high']} kati", "Musterinin gecmis islem deseniyle karsilastir")
    apply((ratio >= cfg["ratio_medium"]) & (ratio < cfg["ratio_high"]), cfg["ratio_medium_points"], f"Tutar tarihsel ortalamanin {cfg['ratio_medium']}-{cfg['ratio_high']} kati", "Musterinin gecmis islem deseniyle karsilastir")
    apply(df["new_recipient"], cfg["new_recipient_points"], "Alici daha once kullanilmamis", "Alici iliskisini ve hesap sahipligini arastir")
    apply(off_hours, cfg["off_hours_points"], "Islem mesai disi saatte gerceklesti", "Kanal, cihaz, IP ve oturum kayitlarini incele")
    apply(repeated, cfg["reactivation_count_points"], f"Yeniden aktivasyon sonrasi kisa surede en az {cfg['reactivation_count']} islem", "Baglantili islemleri birlikte vaka olarak incele")
    apply(inactive & senior, cfg["inactive_senior_combo_points"], "Hareketsizlik ile ileri yas birlikte gerceklesti", "Islem icin ikinci seviye onay ve telefon teyidi uygula")
    apply(
        daily_volume_and_count,
        cfg["daily_volume_count_points"],
        f"Ayni gun toplam transfer en az {cfg['daily_amount']:,.0f} TL ve islem adedi en az {cfg['daily_count']}",
        "Ayni gundeki baglantili islemleri birlikte incele ve bolme ihtimalini arastir",
    )
    apply(
        senior_daily_million,
        cfg["elderly_daily_points"],
        f"{cfg['elderly_daily_age']} yas uzeri musterinin ayni gun toplam transferi en az {cfg['elderly_daily_amount']:,.0f} TL",
        "Musteriyi kayitli iletisim kanalindan teyit et ve ikinci seviye onay uygula",
    )
    apply(split_transactions, 30, "Kontrol limitinin hemen altinda en az 3 bolunmus islem", "Islemlerin yukumlulukten kacinmak icin bolunup bolunmedigini incele")
    apply(serial_recipient, 25, "Ayni aliciya gun icinde en az 5 islem ve 750.000 TL toplam transfer", "Musteri-alici iliskisini ve islemlerin ekonomik amacini arastir")
    apply(first_high_recipient, 25, "Yeni aliciya ilk transfer en az 500.000 TL", "Alici hesap sahipligi, musteri teyidi ve islem belgesini kontrol et")
    apply(night_series, 25, "Gece iki saatlik dilimde en az 3 islem ve 250.000 TL toplam", "Cihaz, IP, oturum ve musteri iradesini dogrula")
    apply(account_drain, 35, "Hareketsizlik sonrasi bakiyenin en az %80'i transfer edildi", "Hesabi incelemeye al, musteri teyidi ve ikinci seviye onay uygula")
    apply(common_recipient, 30, "Ayni aliciya bir gunde en az 10 farkli musteriden 2.000.000 TL transfer", "Para toplama ve mule hesap ihtimalini incele")
    apply(profile_mismatch, 20, "Musteri profilinde olmayan para birimi veya ulkeye yuksek transfer", "Islem amaci, ulke riski, lehtar ve belgeleri kontrol et")
    apply(cancellation_redirect, 25, "Iptal edilen islemle baglantili farkli transfer", "Iptal nedeni, yeni alici ve kullanici hareketlerini birlikte incele")
    apply(shared_access, 35, "Ayni cihaz veya IP bir gunde en az 5 farkli hesapta kullanildi", "Hesap ele gecirme ve organize islem ihtimalini arastir")
    apply(employee_concentration, 30, "Personel belirli musterinin islemlerinin en az %70'ini ve 10'dan fazlasini yapti", "Gorevler ayriligi ve personel iliskisini incele")
    apply(senior & df["new_recipient"], 10, "65+ yas ile yeni alici birlikte gerceklesti", "Musteriyi kayitli telefonundan teyit et")
    apply((df["age"] > 70) & night, 15, "70+ yas ile gece islemi birlikte gerceklesti", "Islem iradesini acilen dogrula")
    apply(inactive & df["new_recipient"], 15, "Hareketsizlik sonrasi yeni alici", "Alici iliskisini ve hesap erisimini incele")
    apply(account_drain, 20, "Hareketsizlik ve hesap bosaltma kombinasyonu", "Isleme ikinci seviye onay uygula")
    apply(shared_access & df["new_recipient"], 15, "Ortak cihaz/IP ile yeni alici birlikte gerceklesti", "Dijital erisim kayitlarini derinlemesine incele")
    apply(serial_recipient & split_transactions, 20, "Seri transfer ve limit alti bolme birlikte gerceklesti", "Baglantili islemleri tek vaka altinda birlestir")
    apply(profile_mismatch & df["new_recipient"], 15, "Profil disi ulke/para birimi ile yeni alici birlikte", "Uyum birimine yonlendir")

    allowed_custom_fields = {
        "inactivity_days", "age", "transaction_amount", "historical_avg_amount",
        "new_recipient", "transaction_hour", "transaction_count_after_reactivation",
        "daily_transfer_total", "daily_transaction_count", "recipient_id",
        "account_balance_before", "channel", "currency", "destination_country",
        "transaction_status", "employee_id", "new_currency_or_country",
    }

    def custom_condition(field: str, operator: str, raw_value: Any) -> pd.Series:
        if field not in allowed_custom_fields or field not in df.columns:
            return pd.Series(False, index=df.index)
        series = df[field]
        if pd.api.types.is_bool_dtype(series):
            value = str(raw_value).strip().lower() in {"true", "1", "yes", "evet", "e", "y"}
            return {"==": series == value, "!=": series != value}.get(operator, pd.Series(False, index=df.index))
        if pd.api.types.is_numeric_dtype(series):
            value = _parse_number(raw_value)
            if pd.isna(value):
                return pd.Series(False, index=df.index)
            numeric = pd.to_numeric(series, errors="coerce")
            return {">=": numeric >= value, ">": numeric > value, "<=": numeric <= value,
                    "<": numeric < value, "==": numeric == value, "!=": numeric != value}.get(operator, pd.Series(False, index=df.index))
        text = series.fillna("").astype(str).str.lower()
        value = str(raw_value).strip().lower()
        if operator == "contains": return text.str.contains(value, regex=False)
        if operator == "==": return text == value
        if operator == "!=": return text != value
        return pd.Series(False, index=df.index)

    for rule in custom_rules or []:
        if not bool(rule.get("active", 1)): continue
        mask = custom_condition(str(rule.get("field1", "")), str(rule.get("operator1", "")), rule.get("value1", ""))
        if rule.get("field2"):
            mask &= custom_condition(str(rule["field2"]), str(rule.get("operator2", "")), rule.get("value2", ""))
        apply(mask, int(rule.get("points", 0)), f"Ozel senaryo: {rule.get('reason', rule.get('name', ''))}", str(rule.get("action", "Yetkili incelemesi yap")))

    score = np.minimum(score, 100)
    level = np.select([score >= 70, score >= 40], ["YUKSEK", "ORTA"], default="DUSUK")
    age_band = pd.cut(df["age"], bins=[17, 64, 74, 200], labels=["18-64", "65-74", "75+"])

    df["age_band"] = age_band.astype(str)
    df["amount_vs_average"] = ratio.fillna(0).round(2)
    df["risk_score"] = score
    df["risk_level"] = level
    df["risk_reasons"] = [" | ".join(x) if x else "Tetiklenen risk kurali yok" for x in reasons]
    df["recommended_actions"] = [
        " | ".join(x) if x else "Standart izleme surecine devam et" for x in actions
    ]
    df["risk_reasons_json"] = [json.dumps(x, ensure_ascii=False) for x in reasons]
    df["recommended_actions_json"] = [json.dumps(x, ensure_ascii=False) for x in actions]
    return df
