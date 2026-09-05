import sqlite3
import pandas as pd
from pathlib import Path


# ==========================================
# PATHS
# ==========================================

BASE_DIR = Path(__file__).resolve().parent.parent

DB_PATH = BASE_DIR / "data" / "fra_monitoring.db"

CLAIMS_FILE = BASE_DIR / "data" / "processed" / "claims.csv"
LAND_FILE = BASE_DIR / "data" / "processed" / "land_records.csv"
ANOMALIES_FILE = BASE_DIR / "data" / "processed" / "anomalies.csv"


# ==========================================
# CONNECT DATABASE
# ==========================================

print("Creating database...")

conn = sqlite3.connect(DB_PATH)

cursor = conn.cursor()


# ==========================================
# 1. STATES TABLE
# ==========================================

cursor.execute("""
CREATE TABLE IF NOT EXISTS states (

    state_id INTEGER PRIMARY KEY AUTOINCREMENT,

    state_name TEXT UNIQUE NOT NULL,

    total_claims INTEGER DEFAULT 0,

    approved_claims INTEGER DEFAULT 0,

    pending_claims INTEGER DEFAULT 0,

    rejected_claims INTEGER DEFAULT 0,

    under_review_claims INTEGER DEFAULT 0
)
""")


# ==========================================
# 2. DISTRICTS TABLE
# ==========================================

cursor.execute("""
CREATE TABLE IF NOT EXISTS districts (

    district_id INTEGER PRIMARY KEY AUTOINCREMENT,

    district_name TEXT NOT NULL,

    state_id INTEGER NOT NULL,

    latitude REAL,

    longitude REAL,

    geometry TEXT,

    FOREIGN KEY (state_id)
        REFERENCES states(state_id),

    UNIQUE(district_name, state_id)
)
""")


# ==========================================
# 3. CLAIMS TABLE
# ==========================================

cursor.execute("""
CREATE TABLE IF NOT EXISTS claims (

    claim_id TEXT PRIMARY KEY,

    state TEXT NOT NULL,

    district TEXT NOT NULL,

    village TEXT,

    claim_type TEXT,

    claimant_id TEXT,

    latitude REAL,

    longitude REAL,

    area_claimed REAL,

    submission_date TEXT,

    last_updated TEXT,

    decision_date TEXT,

    status TEXT
)
""")


# ==========================================
# 4. LAND RECORDS TABLE
# ==========================================

cursor.execute("""
CREATE TABLE IF NOT EXISTS land_records (

    land_record_id TEXT PRIMARY KEY,

    claim_id TEXT NOT NULL,

    recorded_area REAL,

    land_status TEXT,

    survey_reference TEXT,

    FOREIGN KEY (claim_id)
        REFERENCES claims(claim_id)
)
""")


# ==========================================
# 5. ANOMALIES TABLE
# ==========================================

cursor.execute("""
CREATE TABLE IF NOT EXISTS anomalies (

    anomaly_id INTEGER PRIMARY KEY AUTOINCREMENT,

    claim_id TEXT NOT NULL,

    state TEXT,

    district TEXT,

    anomaly_type TEXT,

    severity TEXT,

    description TEXT,

    evidence TEXT,

    detected_at TEXT DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (claim_id)
        REFERENCES claims(claim_id)
)
""")


# ==========================================
# LOAD CSV DATA
# ==========================================

print("Loading CSV files...")

claims_df = pd.read_csv(CLAIMS_FILE)

land_df = pd.read_csv(LAND_FILE)

anomalies_df = pd.read_csv(ANOMALIES_FILE)


# ==========================================
# INSERT CLAIMS
# ==========================================

print("Inserting claims...")

claims_df.to_sql(
    "claims",
    conn,
    if_exists="append",
    index=False
)


# ==========================================
# INSERT LAND RECORDS
# ==========================================

print("Inserting land records...")

land_df.to_sql(
    "land_records",
    conn,
    if_exists="append",
    index=False
)


# ==========================================
# INSERT ANOMALIES
# ==========================================

print("Inserting anomalies...")

anomalies_df.to_sql(
    "anomalies",
    conn,
    if_exists="append",
    index=False
)


# ==========================================
# CREATE STATES
# ==========================================

print("Creating states...")

states = claims_df["state"].unique()

for state in states:

    cursor.execute("""
    INSERT OR IGNORE INTO states (state_name)
    VALUES (?)
    """, (state,))


# ==========================================
# UPDATE STATE STATISTICS
# ==========================================

for state in states:

    total = len(
        claims_df[
            claims_df["state"] == state
        ]
    )

    approved = len(
        claims_df[
            (claims_df["state"] == state) &
            (claims_df["status"] == "APPROVED")
        ]
    )

    pending = len(
        claims_df[
            (claims_df["state"] == state) &
            (claims_df["status"] == "PENDING")
        ]
    )

    rejected = len(
        claims_df[
            (claims_df["state"] == state) &
            (claims_df["status"] == "REJECTED")
        ]
    )

    under_review = len(
        claims_df[
            (claims_df["state"] == state) &
            (claims_df["status"] == "UNDER_REVIEW")
        ]
    )

    cursor.execute("""
    UPDATE states

    SET
        total_claims = ?,
        approved_claims = ?,
        pending_claims = ?,
        rejected_claims = ?,
        under_review_claims = ?

    WHERE state_name = ?
    """, (
        total,
        approved,
        pending,
        rejected,
        under_review,
        state
    ))


# ==========================================
# CREATE DISTRICTS
# ==========================================

print("Creating districts...")

districts = claims_df[
    ["district", "state", "latitude", "longitude"]
].groupby(
    ["district", "state"]
).first().reset_index()


for _, row in districts.iterrows():

    cursor.execute("""
    SELECT state_id
    FROM states
    WHERE state_name = ?
    """, (row["state"],))

    result = cursor.fetchone()

    if result:

        state_id = result[0]

        cursor.execute("""
        INSERT OR IGNORE INTO districts
        (
            district_name,
            state_id,
            latitude,
            longitude
        )

        VALUES (?, ?, ?, ?)
        """, (
            row["district"],
            state_id,
            row["latitude"],
            row["longitude"]
        ))


# ==========================================
# INDEXES
# ==========================================

print("Creating indexes...")

cursor.execute("""
CREATE INDEX IF NOT EXISTS idx_claims_state
ON claims(state)
""")

cursor.execute("""
CREATE INDEX IF NOT EXISTS idx_claims_district
ON claims(district)
""")

cursor.execute("""
CREATE INDEX IF NOT EXISTS idx_claims_status
ON claims(status)
""")

cursor.execute("""
CREATE INDEX IF NOT EXISTS idx_claims_type
ON claims(claim_type)
""")

cursor.execute("""
CREATE INDEX IF NOT EXISTS idx_anomalies_claim
ON anomalies(claim_id)
""")

cursor.execute("""
CREATE INDEX IF NOT EXISTS idx_anomalies_severity
ON anomalies(severity)
""")


# ==========================================
# COMMIT
# ==========================================

conn.commit()


# ==========================================
# DATABASE SUMMARY
# ==========================================

print("\n===================================")
print("DATABASE CREATED SUCCESSFULLY")
print("===================================")

tables = [
    "states",
    "districts",
    "claims",
    "land_records",
    "anomalies"
]

for table in tables:

    cursor.execute(
        f"SELECT COUNT(*) FROM {table}"
    )

    count = cursor.fetchone()[0]

    print(f"{table}: {count} records")


print("\nDatabase location:")
print(DB_PATH)


conn.close()