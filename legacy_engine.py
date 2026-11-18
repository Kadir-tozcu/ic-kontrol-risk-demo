import numpy as np

REQUIRED_COLUMNS = ["transaction_id", "customer_id", "transaction_datetime", "age",
                    "inactivity_days", "transaction_amount", "historical_avg_amount",
                    "new_recipient", "transaction_hour", "daily_transaction_count", "daily_transfer_total"]

# Optional amount thresholds start above the range of the original synthetic sample.
RULE_FIELDS = {
    "inactivity_days_threshold": ("Hareketsizlik (gün)", 365, 1, 3650),
    "elderly_daily_age": ("İleri yaş eşiği", 65, 18, 110),
    "high_amount": ("Yüksek işlem tutarı (TL)", 1000000, 1, 100000000),
    "daily_amount": ("Günlük transfer toplamı (TL)", 150000, 1, 100000000),
    "daily_count": ("Günlük işlem sayısı", 6, 1, 10000),
    "elderly_daily_amount": ("İleri yaş günlük tutarı (TL)", 1000000, 1, 100000000),
    "high_sla_hours": ("Yüksek risk inceleme süresi (saat)", 24, 1, 720),
    "medium_sla_hours": ("Orta risk inceleme süresi (saat)", 72, 1, 2160),
}
DEFAULTS = {key: field[1] for key, field in RULE_FIELDS.items()}


def score_transactions(data, rules):
    df = data[REQUIRED_COLUMNS].copy()
    dormant = df.inactivity_days >= rules["inactivity_days_threshold"]
    older = df.age >= rules["elderly_daily_age"]
    triggers = [
        ("Hareketsiz hesap", dormant, 20),
        ("İleri yaş", older, 10),
        ("Hareketsizlik ve ileri yaş", dormant & older, 15),
        ("Yeni alıcı", df.new_recipient, 15),
        ("Gece işlemi", df.transaction_hour < 6, 10),
        ("Geçmiş ortalamanın en az 5 katı", df.transaction_amount >= 5 * df.historical_avg_amount, 15),
        ("Günlük işlem adedi", df.daily_transaction_count >= rules["daily_count"], 10),
        ("Yüksek günlük transfer", df.daily_transfer_total >= rules["daily_amount"], 15),
        ("Yüksek işlem tutarı", df.transaction_amount >= rules["high_amount"], 15),
        ("İleri yaş ve yüksek günlük tutar", older & (df.daily_transfer_total >= rules["elderly_daily_amount"]), 10),
    ]
    flags = np.column_stack([mask for _, mask, _ in triggers])
    df["risk_score"] = (flags @ np.array([weight for _, _, weight in triggers])).clip(0, 100)
    high, medium = df.risk_score >= 60, df.risk_score >= 30
    df["risk_level"] = np.select([high, medium], ["YÜKSEK", "ORTA"], default="DÜŞÜK")
    df["risk_reasons"] = [" | ".join(triggers[i][0] for i in np.flatnonzero(row)) or "Kural tetiklenmedi" for row in flags]
    df["recommended_actions"] = np.select([high, medium], ["Öncelikli manuel inceleme ve alıcı doğrulaması", "İşlem geçmişiyle karşılaştırma"], default="Rutin izleme")
    return df
