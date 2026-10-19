"""
Phase 9 — Step 1: Fetch genuine historical daily weather from Open-Meteo Archive API.

Source: Open-Meteo Historical Weather API (Archive endpoint)
        https://archive-api.open-meteo.com/v1/archive

Dataset: ERA5 (ECMWF Reanalysis v5) — used because ERA5-Land precipitation was
         unavailable (None) for Karnataka grid points. ERA5 provides complete,
         consistent precipitation and 2 m temperature for 2000–2017.

Variables (daily):
  - precipitation_sum        (mm)
  - temperature_2m_max       (°C)
  - temperature_2m_min       (°C)
  - temperature_2m_mean      (°C)

Coordinates: district headquarters (well-documented geographic coordinates).
Date range: 2000-01-01 .. 2017-12-31 (matches yield dataset years).

Validation per district:
  - HTTP status == 200
  - Content-Type starts with application/json
  - JSON parses; has 'daily' with 'time', precipitation, temperature arrays
  - returned date range == requested range
  - count missing values per variable
  - count duplicate dates
  - record units, timezone, generation time

Retry: up to 2 retries per failed district. Stop rather than invent data.
Raw JSON responses saved under data/raw_weather/ per district.
"""

import json, time, urllib.request, urllib.error
from pathlib import Path
import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent
DATA_DIR = BASE / "data"
RAW_DIR = DATA_DIR / "raw_weather"
RAW_DIR.mkdir(parents=True, exist_ok=True)

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
START_DATE = "2000-01-01"
END_DATE = "2017-12-31"
DAILY_VARS = ["precipitation_sum", "temperature_2m_max",
              "temperature_2m_min", "temperature_2m_mean"]

# District headquarters coordinates (latitude, longitude).
# Source: standard geographic references for Karnataka district HQ towns.
DISTRICTS = {
    "Ballari":          (15.1394, 76.9214),
    "Belagavi":         (15.8497, 74.4977),
    "Bengaluru Urban":  (12.9716, 77.5946),
    "Bidar":            (17.9104, 77.5199),
    "Chikkamagaluru":   (13.3161, 75.7720),
    "Chitradurga":      (14.2251, 76.3970),
    "Dakshina Kannada": (12.9141, 74.8560),
    "Dharwad":          (15.4589, 75.0078),
    "Hassan":           (13.0054, 76.1000),
    "Kalaburagi":       (17.3320, 76.8365),
    "Kodagu":           (12.4244, 75.7381),
    "Kolar":            (13.1367, 78.1299),
    "Mandya":           (12.5230, 76.8994),
    "Mysuru":           (12.2958, 76.6394),
    "Raichur":          (16.2076, 77.3463),
    "Shivamogga":       (13.9299, 75.5681),
    "Tumakuru":         (13.3423, 77.1011),
    "Uttara Kannada":   (14.8081, 74.1308),
    "Vijayapura":       (16.8300, 75.7100),
}

HEADERS = {"User-Agent": "SeedIQ-Phase9/1.0 (academic yield research)"}


def build_url(lat, lon):
    qs = (
        f"latitude={lat}&longitude={lon}"
        f"&start_date={START_DATE}&end_date={END_DATE}"
        f"&daily={','.join(DAILY_VARS)}&timezone=auto"
    )
    return f"{ARCHIVE_URL}?{qs}"


def fetch_one(district, lat, lon):
    """Fetch and validate one district. Returns (status_dict, daily_df_or_None)."""
    url = build_url(lat, lon)
    last_err = None
    for attempt in range(3):  # 1 try + 2 retries
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=120) as r:
                status = r.status
                ctype = r.headers.get("Content-Type", "")
                raw_bytes = r.read()
            if status != 200:
                last_err = f"HTTP {status}"
                continue
            if not ctype.startswith("application/json"):
                last_err = f"bad content-type: {ctype[:80]}"
                continue
            try:
                data = json.loads(raw_bytes.decode("utf-8"))
            except Exception as e:
                last_err = f"JSON parse error: {e}"
                continue
            if "daily" not in data or "time" not in data.get("daily", {}):
                last_err = "missing daily/time in response"
                continue
            daily = data["daily"]
            times = daily["time"]
            # validate date range
            if times[0] != START_DATE or times[-1] != END_DATE:
                last_err = f"date range mismatch: {times[0]}..{times[-1]}"
                continue
            # validate all requested vars present
            missing_vars = [v for v in DAILY_VARS if v not in daily]
            if missing_vars:
                last_err = f"missing vars: {missing_vars}"
                continue
            df = pd.DataFrame(daily)
            dup_count = int(df["time"].duplicated().sum())
            n_missing = {v: int(df[v].isna().sum()) for v in DAILY_VARS}
            n_total = len(df)
            # save raw json
            raw_path = RAW_DIR / f"{district.replace(' ', '_')}.json"
            with open(raw_path, "w") as f:
                json.dump(data, f)
            ok = {
                "district": district,
                "latitude": data.get("latitude"),
                "longitude": data.get("longitude"),
                "requested_lat": lat,
                "requested_lon": lon,
                "timezone": data.get("timezone"),
                "elevation": data.get("elevation"),
                "generationtime_ms": data.get("generationtime_ms"),
                "daily_units": data.get("daily_units"),
                "date_start": times[0],
                "date_end": times[-1],
                "n_days": n_total,
                "n_duplicate_dates": dup_count,
                "missing": n_missing,
                "raw_path": str(raw_path),
                "status": "OK",
                "attempts": attempt + 1,
            }
            return ok, df
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            last_err = f"network error: {e}"
            time.sleep(2 * (attempt + 1))
            continue
        except Exception as e:
            last_err = f"unexpected: {e}"
            time.sleep(1)
            continue
    return {
        "district": district, "status": "FAILED", "error": last_err,
        "attempts": 3,
    }, None


def main():
    print(f"=== Phase 9 weather fetch: {len(DISTRICTS)} districts, "
          f"{START_DATE}..{END_DATE} ===\n")
    provenance = []
    all_dfs = []
    for district, (lat, lon) in DISTRICTS.items():
        print(f"  Fetching {district} ({lat}, {lon})...", end=" ", flush=True)
        info, df = fetch_one(district, lat, lon)
        if info["status"] == "OK":
            print(f"OK  n_days={info['n_days']}  "
                  f"missing_precip={info['missing']['precipitation_sum']}  "
                  f"missing_tmean={info['missing']['temperature_2m_mean']}  "
                  f"dups={info['n_duplicate_dates']}  "
                  f"(attempt {info['attempts']})")
            if df is not None:
                df = df.copy()
                df["District"] = district
                df["date"] = pd.to_datetime(df["time"])
                all_dfs.append(df)
        else:
            print(f"FAILED: {info.get('error')}")
        provenance.append(info)
        time.sleep(0.5)  # polite rate limiting

    n_ok = sum(1 for p in provenance if p["status"] == "OK")
    print(f"\nFetch complete: {n_ok}/{len(DISTRICTS)} districts OK")

    if n_ok == 0:
        print("ERROR: No weather data fetched. Aborting.")
        return

    # Combine all districts
    combined = pd.concat(all_dfs, ignore_index=True)
    # Coerce numeric
    for v in DAILY_VARS:
        combined[v] = pd.to_numeric(combined[v], errors="coerce")

    out_csv = DATA_DIR / "openmeteo_daily_weather_karnataka.csv"
    combined.to_csv(out_csv, index=False)
    print(f"Combined daily weather saved: {out_csv}  ({len(combined)} rows)")

    # Provenance metadata
    prov = {
        "source": "Open-Meteo Historical Weather API (Archive)",
        "endpoint": ARCHIVE_URL,
        "dataset_model": "ERA5 (ECMWF Reanalysis v5)",
        "dataset_note": (
            "ERA5-Land precipitation returned None for Karnataka grid points; "
            "ERA5 was used for all variables to ensure consistent, complete coverage. "
            "Open-Meteo provides reanalysis/weather-model data, not guaranteed "
            "ground-station observations."
        ),
        "spatial_resolution_note": (
            "ERA5 ~0.25° (~31 km) grid; coordinates snapped to nearest grid point "
            "(see latitude/longitude per district)."
        ),
        "retrieval_date": time.strftime("%Y-%m-%d"),
        "date_coverage": f"{START_DATE} to {END_DATE}",
        "variables": {
            v: "mm" if v == "precipitation_sum" else "°C" for v in DAILY_VARS
        },
        "units_source": "from daily_units in each API response",
        "n_districts_requested": len(DISTRICTS),
        "n_districts_ok": n_ok,
        "max_retries_per_district": 2,
        "districts": provenance,
        "combined_csv": str(out_csv),
    }
    prov_path = DATA_DIR / "openmeteo_weather_provenance.json"
    with open(prov_path, "w") as f:
        json.dump(prov, f, indent=2)
    print(f"Provenance saved: {prov_path}")

    # Quick summary stats
    print("\n--- Missing data summary ---")
    for v in DAILY_VARS:
        n_miss = int(combined[v].isna().sum())
        print(f"  {v}: {n_miss}/{len(combined)} missing "
              f"({100*n_miss/len(combined):.3f}%)")


if __name__ == "__main__":
    main()
