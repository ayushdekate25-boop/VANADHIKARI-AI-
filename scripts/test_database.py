import sqlite3

DB = "data/fra_monitoring.db"

conn = sqlite3.connect(DB)
cursor = conn.cursor()

print("\n===================================")
print("DATABASE TEST")
print("===================================")


# ==========================================
# 1. TOTAL CLAIMS
# ==========================================

cursor.execute("""
SELECT COUNT(*)
FROM claims
""")

total_claims = cursor.fetchone()[0]

print("\nTotal claims:", total_claims)


# ==========================================
# 2. CLAIM STATUS
# ==========================================

print("\nClaim status:")

cursor.execute("""
SELECT status, COUNT(*)
FROM claims
GROUP BY status
ORDER BY COUNT(*) DESC
""")

for status, count in cursor.fetchall():
    print(f"{status}: {count}")


# ==========================================
# 3. CLAIM TYPES
# ==========================================

print("\nClaim types:")

cursor.execute("""
SELECT claim_type, COUNT(*)
FROM claims
GROUP BY claim_type
""")

for claim_type, count in cursor.fetchall():
    print(f"{claim_type}: {count}")


# ==========================================
# 4. STATE-WISE CLAIMS
# ==========================================

print("\nState-wise claims:")

cursor.execute("""
SELECT
    state,
    COUNT(*) AS total_claims
FROM claims
GROUP BY state
ORDER BY total_claims DESC
""")

for state, count in cursor.fetchall():
    print(f"{state}: {count}")


# ==========================================
# 5. STATE-WISE PENDING CLAIMS
# ==========================================

print("\nState-wise pending claims:")

cursor.execute("""
SELECT
    state,
    COUNT(*) AS pending_claims
FROM claims
WHERE status = 'PENDING'
GROUP BY state
ORDER BY pending_claims DESC
""")

for state, count in cursor.fetchall():
    print(f"{state}: {count}")


# ==========================================
# 6. ANOMALY SUMMARY
# ==========================================

print("\nAnomaly summary:")

cursor.execute("""
SELECT
    anomaly_type,
    COUNT(*) AS total
FROM anomalies
GROUP BY anomaly_type
ORDER BY total DESC
""")

for anomaly_type, count in cursor.fetchall():
    print(f"{anomaly_type}: {count}")


# ==========================================
# 7. HIGH SEVERITY ANOMALIES
# ==========================================

print("\nHIGH severity anomalies:")

cursor.execute("""
SELECT
    claim_id,
    state,
    district,
    anomaly_type,
    evidence
FROM anomalies
WHERE severity = 'HIGH'
LIMIT 10
""")

for row in cursor.fetchall():

    print("\nClaim:", row[0])
    print("State:", row[1])
    print("District:", row[2])
    print("Type:", row[3])
    print("Evidence:", row[4])


# ==========================================
# 8. DISTRICTS WITH MOST ANOMALIES
# ==========================================

print("\nTop districts by anomalies:")

cursor.execute("""
SELECT
    district,
    state,
    COUNT(*) AS anomaly_count
FROM anomalies
GROUP BY district, state
ORDER BY anomaly_count DESC
LIMIT 10
""")

for district, state, count in cursor.fetchall():

    print(
        f"{district}, {state}: {count} anomalies"
    )


# ==========================================
# 9. CLAIM SEARCH EXAMPLE
# ==========================================

print("\nExample claim search:")

cursor.execute("""
SELECT
    c.claim_id,
    c.state,
    c.district,
    c.status,
    c.area_claimed,
    l.recorded_area
FROM claims c
LEFT JOIN land_records l
ON c.claim_id = l.claim_id
LIMIT 1
""")

row = cursor.fetchone()

print(row)


# ==========================================
# DONE
# ==========================================

print("\n===================================")
print("DATABASE TEST COMPLETE")
print("===================================")

conn.close()