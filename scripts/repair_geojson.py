import json
import shutil
import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "fra_monitoring.db"
GEOJSON_PATH = BASE_DIR / "data" / "geo" / "india_districts.geojson"
BACKUP_PATH = GEOJSON_PATH.with_suffix(".corrupt")


def main():
    if GEOJSON_PATH.exists() and not BACKUP_PATH.exists():
        shutil.move(GEOJSON_PATH, BACKUP_PATH)

    with sqlite3.connect(DB_PATH) as connection:
        rows = connection.execute(
            """
            SELECT d.district_name, s.state_name, d.latitude, d.longitude
            FROM districts AS d
            JOIN states AS s ON s.state_id = d.state_id
            WHERE d.latitude IS NOT NULL AND d.longitude IS NOT NULL
            ORDER BY s.state_name, d.district_name
            """
        ).fetchall()

    features = []
    for district_name, state_name, latitude, longitude in rows:
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "district_name": district_name,
                    "state_name": state_name,
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [longitude, latitude],
                },
            }
        )

    geojson = {
        "type": "FeatureCollection",
        "features": features,
    }
    GEOJSON_PATH.write_text(
        json.dumps(geojson, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Created {GEOJSON_PATH} with {len(features)} district points.")
    print(f"Original file backed up to {BACKUP_PATH}.")


if __name__ == "__main__":
    main()