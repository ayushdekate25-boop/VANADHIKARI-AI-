import pandas as pd
from datetime import datetime

# ==========================================
# LOAD DATA
# ==========================================

claims = pd.read_csv(
    "data/processed/claims.csv"
)

land = pd.read_csv(
    "data/processed/land_records.csv"
)

# Convert dates
claims["submission_date"] = pd.to_datetime(
    claims["submission_date"],
    errors="coerce"
)

claims["last_updated"] = pd.to_datetime(
    claims["last_updated"],
    errors="coerce"
)

claims["decision_date"] = pd.to_datetime(
    claims["decision_date"],
    errors="coerce"
)

# ==========================================
# MERGE CLAIM + LAND RECORD
# ==========================================

df = claims.merge(
    land,
    on="claim_id",
    how="left"
)

print("Total claims:", len(df))


# ==========================================
# ANOMALY LIST
# ==========================================

anomalies = []


# ==========================================
# 1. LAND AREA MISMATCH
# ==========================================

for _, row in df.iterrows():

    claimed = row["area_claimed"]
    recorded = row["recorded_area"]

    if pd.isna(claimed) or pd.isna(recorded):
        continue

    difference = abs(claimed - recorded)

    # Percentage difference
    percentage_difference = (
        difference / claimed
    ) * 100

    if percentage_difference >= 30:

        severity = "HIGH"

        anomalies.append({
            "claim_id": row["claim_id"],
            "state": row["state"],
            "district": row["district"],
            "anomaly_type": "LAND_MISMATCH",
            "severity": severity,
            "description":
                "Claimed land area differs significantly "
                "from the recorded land area.",
            "evidence":
                f"Claimed: {claimed} ha | "
                f"Recorded: {recorded} ha | "
                f"Difference: {difference:.2f} ha "
                f"({percentage_difference:.1f}%)"
        })


# ==========================================
# 2. DELAYED PENDING CLAIM
# ==========================================

today = pd.Timestamp("2026-09-04")

for _, row in df.iterrows():

    if row["status"] != "PENDING":
        continue

    submission = row["submission_date"]

    if pd.isna(submission):
        continue

    age_days = (
        today - submission
    ).days

    if age_days > 365:

        if age_days > 730:
            severity = "HIGH"
        else:
            severity = "MEDIUM"

        anomalies.append({
            "claim_id": row["claim_id"],
            "state": row["state"],
            "district": row["district"],
            "anomaly_type": "DELAYED_CLAIM",
            "severity": severity,
            "description":
                "Pending claim has remained unresolved "
                "for more than one year.",
            "evidence":
                f"Submitted: {submission.date()} | "
                f"Pending for approximately "
                f"{age_days} days"
        })


# ==========================================
# 3. MISSING DECISION DATE
# ==========================================

for _, row in df.iterrows():

    if row["status"] in ["APPROVED", "REJECTED"]:

        if pd.isna(row["decision_date"]):

            anomalies.append({
                "claim_id": row["claim_id"],
                "state": row["state"],
                "district": row["district"],
                "anomaly_type": "MISSING_DECISION_DATE",
                "severity": "MEDIUM",
                "description":
                    "Claim has a final status but "
                    "decision date is missing.",
                "evidence":
                    f"Status: {row['status']} | "
                    f"Decision date: Missing"
            })


# ==========================================
# 4. MISSING LAST UPDATE
# ==========================================

for _, row in df.iterrows():

    if pd.isna(row["last_updated"]):

        anomalies.append({
            "claim_id": row["claim_id"],
            "state": row["state"],
            "district": row["district"],
            "anomaly_type": "MISSING_UPDATE",
            "severity": "LOW",
            "description":
                "Claim does not contain a last-updated date.",
            "evidence":
                "Last updated field is missing."
        })


# ==========================================
# CREATE DATAFRAME
# ==========================================

anomaly_df = pd.DataFrame(anomalies)


# ==========================================
# SAVE
# ==========================================

anomaly_df.to_csv(
    "data/processed/anomalies.csv",
    index=False
)


# ==========================================
# SUMMARY
# ==========================================

print("\n===================================")
print("ANOMALY DETECTION COMPLETE")
print("===================================")

print(
    "Total anomalies detected:",
    len(anomaly_df)
)

print("\nAnomaly types:")

print(
    anomaly_df["anomaly_type"].value_counts()
)

print("\nSeverity:")

print(
    anomaly_df["severity"].value_counts()
)

print("\nFile created:")

print(
    "data/processed/anomalies.csv"
)