import sqlite3

DB_PATH = "data/fra_monitoring.db"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Remove old view if it exists
cursor.execute("DROP VIEW IF EXISTS district_risk")

cursor.execute("""
CREATE VIEW district_risk AS
SELECT
    d.district_id,
    d.district_name,
    s.state_name,

    COUNT(DISTINCT c.claim_id) AS total_claims,

    SUM(
        CASE
            WHEN c.status = 'PENDING' THEN 1
            ELSE 0
        END
    ) AS pending_claims,

    SUM(
        CASE
            WHEN a.severity = 'HIGH' THEN 1
            ELSE 0
        END
    ) AS high_anomalies,

    SUM(
        CASE
            WHEN a.severity = 'MEDIUM' THEN 1
            ELSE 0
        END
    ) AS medium_anomalies,

    SUM(
        CASE
            WHEN a.severity = 'LOW' THEN 1
            ELSE 0
        END
    ) AS low_anomalies

FROM districts d

JOIN states s
    ON d.state_id = s.state_id

LEFT JOIN claims c
    ON c.district = d.district_name

LEFT JOIN anomalies a
    ON a.claim_id = c.claim_id

GROUP BY
    d.district_id,
    d.district_name,
    s.state_name
""")

conn.commit()


# Read district data
cursor.execute("""
SELECT
    district_id,
    district_name,
    state_name,
    total_claims,
    pending_claims,
    high_anomalies,
    medium_anomalies,
    low_anomalies
FROM district_risk
ORDER BY high_anomalies DESC
""")

rows = cursor.fetchall()

print("\n========== DISTRICT RISK ANALYSIS ==========\n")

for row in rows:

    (
        district_id,
        district_name,
        state_name,
        total_claims,
        pending_claims,
        high,
        medium,
        low
    ) = row

    total_claims = total_claims or 0
    pending_claims = pending_claims or 0
    high = high or 0
    medium = medium or 0
    low = low or 0

    if total_claims == 0:
        continue

    # Weighted anomaly count
    weighted_anomalies = (
        high * 3 +
        medium * 2 +
        low
    )

    # Normalize anomaly density
    anomaly_density = weighted_anomalies / total_claims

    # Pending percentage
    pending_rate = pending_claims / total_claims

    # Convert into 0-100 score
    anomaly_score = min(70, anomaly_density * 700)

    pending_score = min(30, pending_rate * 100)

    risk_score = round(
        anomaly_score + pending_score,
        2
    )

    # Risk level
    if risk_score >= 60:
        risk_level = "HIGH"
    elif risk_score >= 30:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    print(
        f"{district_name}, {state_name} | "
        f"Claims: {total_claims} | "
        f"Pending: {pending_claims} | "
        f"Anomalies: {high + medium + low} | "
        f"Risk: {risk_score}/100 | "
        f"{risk_level}"
    )

conn.close()