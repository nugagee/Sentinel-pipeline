from datetime import datetime, timedelta

import pandas as pd
import requests

from _s3 import configure_aws

# Load .env, export AWS creds, and get the landing bucket
AWS_BUCKET = configure_aws()

# Zip code coordinates
zip_codes = {
    "43215": (39.9622, -83.0007),
    "46204": (39.7684, -86.1581),
    "60601": (41.8864, -87.6186),
}

# Date range (last 7 days). Note: the Open-Meteo archive (ERA5) lags a few
# days, so the most recent dates may return null values.
end_date = datetime.today().date()
start_date = end_date - timedelta(days=7)

weather_frames = []

for zip_code, (lat, lon) in zip_codes.items():

    url = (
        "https://archive-api.open-meteo.com/v1/archive"
        f"?latitude={lat}"
        f"&longitude={lon}"
        f"&start_date={start_date}"
        f"&end_date={end_date}"
        "&daily=temperature_2m_max,"
        "temperature_2m_min,"
        "precipitation_sum,"
        "windspeed_10m_max,"
        "weathercode"
        "&timezone=auto"
    )

    response = requests.get(url, timeout=30)
    response.raise_for_status()
    daily = response.json()["daily"]

    df = pd.DataFrame(
        {
            "weather_date": daily["time"],
            "zip_code": zip_code,
            "max_temp_c": daily["temperature_2m_max"],
            "min_temp_c": daily["temperature_2m_min"],
            "precipitation_mm": daily["precipitation_sum"],
            "max_wind_kmh": daily["windspeed_10m_max"],
            "weather_code": daily["weathercode"],
        }
    )

    weather_frames.append(df)
    print(f"Fetched {len(df)} days for zip {zip_code}")

# Combine all zip codes into a single frame
weather_df = pd.concat(weather_frames, ignore_index=True)

# Today's partition
today = datetime.today().strftime("%Y-%m-%d")

s3_path = (
    f"s3://{AWS_BUCKET}/"
    f"source=weather_api/"
    f"day={today}/"
    f"weather.parquet"
)

weather_df.to_parquet(
    s3_path,
    engine="pyarrow",
    compression="snappy",
    index=False,
)

print(f"\n✅ Weather data uploaded ({len(weather_df)} rows): {s3_path}")
