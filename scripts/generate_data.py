import pandas as pd
import random
import uuid
from datetime import datetime, timedelta

random.seed(42)

# States and sample districts
locations = {
    "Madhya Pradesh": [
        "Mandla", "Dindori", "Balaghat", "Betul", "Chhindwara"
    ],
    "Maharashtra": [
        "Gadchiroli", "Nandurbar", "Nashik", "Amravati", "Yavatmal"
    ],
    "Odisha": [
        "Mayurbhanj", "Koraput", "Kandhamal", "Keonjhar", "Sundargarh"
    ],
    "Chhattisgarh": [
        "Bastar", "Dantewada", "Kanker", "Surguja", "Korba"
    ],
    "Jharkhand": [
        "Ranchi", "Gumla", "Simdega", "West Singhbhum", "Latehar"
    ],
    "Rajasthan": [
        "Udaipur", "Dungarpur", "Banswara", "Pratapgarh", "Sirohi"
    ],
    "Gujarat": [
        "Dangs", "Narmada", "Valsad", "Tapi", "Bharuch"
    ]
}

claim_types = ["IFR", "CFR", "CFRR"]
statuses = ["PENDING", "APPROVED", "REJECTED", "UNDER_REVIEW"]

claims = []
land_records = []

start_date = datetime(2020, 1, 1)
end_date = datetime(2026, 6, 30)

for i in range(10000):

    state = random.choice(list(locations.keys()))
    district = random.choice(locations[state])

    claim_id = f"FRA-{10000 + i}"

    claim_type = random.choices(
        claim_types,
        weights=[70, 20, 10]
    )[0]

    status = random.choices(
        statuses,
        weights=[28, 50, 12, 10]
    )[0]

    submission_date = start_date + timedelta(
        days=random.randint(
            0,
            (end_date - start_date).days
        )
    )

    # More recent update normally
    last_updated = submission_date + timedelta(
        days=random.randint(5, 500)
    )

    # Keep date within demo period
    if last_updated > end_date:
        last_updated = end_date

    # Area in hectares
    area_claimed = round(random.uniform(0.5, 8.0), 2)

    # Normally recorded area is close to claimed area
    area_recorded = round(
        area_claimed * random.uniform(0.90, 1.05),
        2
    )

    decision_date = None

    if status in ["APPROVED", "REJECTED"]:
        decision_date = submission_date + timedelta(
            days=random.randint(30, 400)
        )

        if decision_date > end_date:
            decision_date = end_date

    # Generate approximate coordinates
    latitude = round(random.uniform(17.5, 24.5), 6)
    longitude = round(random.uniform(73.0, 85.5), 6)

    village = f"Village-{random.randint(1, 500)}"

    claimant_id = f"CLM-{random.randint(100000, 999999)}"

    claims.append({
        "claim_id": claim_id,
        "state": state,
        "district": district,
        "village": village,
        "claim_type": claim_type,
        "claimant_id": claimant_id,
        "latitude": latitude,
        "longitude": longitude,
        "area_claimed": area_claimed,
        "submission_date": submission_date.date(),
        "last_updated": last_updated.date(),
        "decision_date": decision_date.date()
        if decision_date else None,
        "status": status
    })

    land_records.append({
        "land_record_id": f"LR-{10000 + i}",
        "claim_id": claim_id,
        "recorded_area": area_recorded,
        "land_status": random.choice([
            "FOREST",
            "REVENUE",
            "COMMUNITY",
            "UNCLASSIFIED"
        ]),
        "survey_reference": f"SUR-{random.randint(10000, 99999)}"
    })


claims_df = pd.DataFrame(claims)
land_df = pd.DataFrame(land_records)

# ------------------------------------------------
# PLANT REALISTIC ANOMALIES
# ------------------------------------------------

# 1. Land mismatch
for idx in random.sample(range(10000), 400):

    claims_df.loc[idx, "area_claimed"] = round(
        random.uniform(5, 12), 2
    )

    claim_id = claims_df.loc[idx, "claim_id"]

    land_idx = land_df[
        land_df["claim_id"] == claim_id
    ].index[0]

    land_df.loc[land_idx, "recorded_area"] = round(
        random.uniform(0.5, 3), 2
    )


# 2. Old pending claims
for idx in random.sample(range(10000), 300):

    claims_df.loc[idx, "status"] = "PENDING"

    old_date = datetime(2021, 1, 1) + timedelta(
        days=random.randint(0, 365)
    )

    claims_df.loc[idx, "submission_date"] = old_date.date()


# 3. Approved but missing decision date
for idx in random.sample(range(10000), 150):

    claims_df.loc[idx, "status"] = "APPROVED"
    claims_df.loc[idx, "decision_date"] = None


# 4. Missing last update
for idx in random.sample(range(10000), 150):

    claims_df.loc[idx, "last_updated"] = None


# Save files
claims_df.to_csv(
    "data/processed/claims.csv",
    index=False
)

land_df.to_csv(
    "data/processed/land_records.csv",
    index=False
)

print("===================================")
print("FRA DATA GENERATION COMPLETE")
print("===================================")

print(f"Claims generated: {len(claims_df)}")
print(f"Land records: {len(land_df)}")

print("\nStatus distribution:")
print(claims_df["status"].value_counts())

print("\nClaim type distribution:")
print(claims_df["claim_type"].value_counts())

print("\nFiles created:")
print("data/processed/claims.csv")
print("data/processed/land_records.csv")