"""Reproducible, anonymous synthetic transaction generator."""

from __future__ import annotations

import numpy as np
import pandas as pd


def generate_synthetic_data(n: int = 10_000, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    customer_num = rng.integers(1, max(2, n // 2), n)
    inactive_flag = rng.random(n) < 0.34
    inactivity = np.where(
        inactive_flag,
        rng.integers(365, 1_100, n),
        rng.integers(0, 365, n),
    )
    age = np.clip(np.rint(rng.normal(51, 17, n)), 18, 95).astype(int)
    historical_avg = np.maximum(rng.lognormal(mean=9.8, sigma=0.9, size=n), 500).round(2)
    multiplier = rng.lognormal(mean=0.15, sigma=0.75, size=n)

    # Deliberately inject realistic risky patterns without using real identities.
    risk_cluster = inactive_flag & (age >= 65) & (rng.random(n) < 0.55)
    multiplier[risk_cluster] *= rng.uniform(3.5, 10.0, risk_cluster.sum())
    amount = np.minimum(historical_avg * multiplier, 5_000_000).round(2)
    new_recipient = rng.random(n) < np.where(inactive_flag, 0.42, 0.16)
    off_hour = rng.random(n) < np.where(risk_cluster, 0.45, 0.18)
    hour = rng.integers(8, 20, n)
    hour[off_hour] = rng.choice([0, 1, 2, 3, 4, 5, 6, 20, 21, 22, 23], off_hour.sum())
    tx_count = rng.poisson(np.where(risk_cluster, 2.8, 0.8), n) + 1

    start = pd.Timestamp("2026-08-15 00:00:00")
    timestamps = (start + pd.to_timedelta(rng.integers(0, 86_400, n), unit="s")).to_numpy(copy=True)
    customer_ids = np.array([f"CUST-{i:05d}" for i in customer_num], dtype=object)
    recipient_ids = np.array([f"REC-{i:05d}" for i in rng.integers(1, max(2, n // 3), n)], dtype=object)
    device_ids = np.array([f"DEV-{i:05d}" for i in rng.integers(1, max(2, n // 2), n)], dtype=object)
    ip_addresses = np.array([f"10.{i // 65536 % 256}.{i // 256 % 256}.{i % 256}" for i in rng.integers(1, 2_000_000, n)], dtype=object)
    employee_ids = np.array([f"EMP-{i:04d}" for i in rng.integers(1, 500, n)], dtype=object)
    currency = np.full(n, "TRY", dtype=object)
    country = np.full(n, "TR", dtype=object)
    original_ids = np.full(n, "", dtype=object)
    new_profile = np.zeros(n, dtype=bool)
    balance = np.maximum(amount * rng.uniform(1.05, 5.0, n), amount).round(2)

    if n >= 100:
        # Auditable injected clusters ensuring every extended scenario has demo examples.
        customer_ids[:25] = "CUST-SPLIT"; recipient_ids[:25] = "REC-SERIAL"
        amount[:25] = 460_000; historical_avg[:25] = 50_000; timestamps[:25] = (start + pd.to_timedelta(np.arange(25) * 1200, unit="s")).to_numpy()
        for i in range(25, 35): customer_ids[i] = f"CUST-COMMON-{i}"; recipient_ids[i] = "REC-COMMON"; amount[i] = 250_000
        for i in range(35, 40): customer_ids[i] = f"CUST-DEVICE-{i}"; device_ids[i] = "DEV-SHARED"; ip_addresses[i] = "10.10.10.10"
        customer_ids[40] = "CUST-DRAIN"; inactivity[40] = 500; amount[40] = 900_000; balance[40] = 1_000_000
        new_recipient[41] = True; amount[41] = 600_000
        currency[42] = "USD"; country[42] = "US"; new_profile[42] = True; amount[42] = 300_000
        original_ids[43] = "TXN-CANCELLED-1"
        customer_ids[50:62] = "CUST-EMP"; employee_ids[50:62] = "EMP-CONCENTRATED"

    return pd.DataFrame({
        "transaction_id": [f"TXN-{i:06d}" for i in range(1, n + 1)],
        "customer_id": customer_ids,
        "transaction_datetime": timestamps,
        "inactivity_days": inactivity,
        "age": age,
        "transaction_amount": amount,
        "historical_avg_amount": historical_avg,
        "new_recipient": new_recipient,
        "transaction_hour": hour,
        "transaction_count_after_reactivation": tx_count,
        "recipient_id": recipient_ids,
        "account_balance_before": balance,
        "device_id": device_ids,
        "ip_address": ip_addresses,
        "channel": rng.choice(["Mobil", "Internet", "Sube", "ATM"], n, p=[0.5, 0.3, 0.15, 0.05]),
        "currency": currency,
        "destination_country": country,
        "transaction_status": "Tamamlandi",
        "original_transaction_id": original_ids,
        "employee_id": employee_ids,
        "new_currency_or_country": new_profile,
    })


if __name__ == "__main__":
    from pathlib import Path
    from risk_engine import score_transactions

    target = Path(__file__).resolve().parent / "demo_data"
    target.mkdir(exist_ok=True)
    raw = generate_synthetic_data()
    scored = score_transactions(raw)
    raw.to_csv(target / "sentetik_10000_islem.csv", index=False, encoding="utf-8-sig")
    scored.to_csv(target / "sentetik_10000_skorlu.csv", index=False, encoding="utf-8-sig")
    print(f"{len(scored):,} anonim islem olusturuldu: {target}")
