# -*- coding: utf-8 -*-

# Adatok forrása: BKK Zrt., CC BY 4.0

# =========================================================
# BKK FORDA → RENDSZÁM → POZÍCIÓ
# GitHub Actions verzió
# =========================================================


# =========================================================
# 1. API-KULCS
# =========================================================

import os

API_KEY = os.environ.get("BKK_API_KEY")

if not API_KEY:
    raise ValueError(
        "A BKK_API_KEY nincs beállítva a GitHub Secrets között."
    )

print("API-kulcs betöltve.")


# =========================================================
# 2. SZÜKSÉGES MODULOK
# =========================================================

import requests
import pandas as pd
import zipfile
import io

from datetime import datetime
from zoneinfo import ZoneInfo

from google.transit import gtfs_realtime_pb2

print("Modulok betöltve.")


# =========================================================
# 3. BKK GTFS BETÖLTÉSE
# =========================================================

GTFS_URL = (
    "https://go.bkk.hu/api/static/v1/public-gtfs/"
    "budapest_gtfs.zip"
)

gtfs_response = requests.get(GTFS_URL)

if gtfs_response.status_code != 200:
    raise Exception(
        f"GTFS letöltési hiba. "
        f"HTTP státusz: {gtfs_response.status_code}"
    )

gtfs_zip = zipfile.ZipFile(
    io.BytesIO(gtfs_response.content)
)

print("GTFS betöltve.")
print(
    f"Fájlok száma: {len(gtfs_zip.namelist())}"
)


# =========================================================
# 4. GTFS ADATOK BETÖLTÉSE
# =========================================================

with gtfs_zip.open("trips.txt") as f:
    trips = pd.read_csv(
        f,
        dtype=str
    )

with gtfs_zip.open("stop_times.txt") as f:
    stop_times = pd.read_csv(
        f,
        dtype=str
    )

print(
    "trips.txt:",
    len(trips),
    "sor"
)

print(
    "stop_times.txt:",
    len(stop_times),
    "sor"
)


# =========================================================
# 5. MAI NAPHOZ TARTOZÓ GTFS TRIP-EK
# =========================================================

mai_datum = datetime.now(
    ZoneInfo("Europe/Budapest")
).strftime("%Y%m%d")


# ---------------------------------------------------------
# calendar_dates.txt betöltése
# ---------------------------------------------------------

with gtfs_zip.open("calendar_dates.txt") as f:
    calendar_dates = pd.read_csv(
        f,
        dtype=str
    )


# ---------------------------------------------------------
# Csak a mai nap rekordjai
# ---------------------------------------------------------

mai_calendar = calendar_dates[
    calendar_dates["date"].astype(str)
    == mai_datum
].copy()


# ---------------------------------------------------------
# Csak a szolgáltatásként érvényes rekordok
# ---------------------------------------------------------

mai_service_ids = set(
    mai_calendar.loc[
        mai_calendar["exception_type"].astype(str) == "1",
        "service_id"
    ].astype(str)
)


# ---------------------------------------------------------
# Mai trip-ek
# ---------------------------------------------------------

trips_ma = trips[
    trips["service_id"]
    .astype(str)
    .isin(mai_service_ids)
].copy()


print(
    "Mai dátum:",
    mai_datum
)

print(
    "Mai service_id-k:",
    len(mai_service_ids)
)

print(
    "Mai trip-ek:",
    len(trips_ma)
)


# =========================================================
# 6. STOP_TIMES OPTIMALIZÁLÁSA
# =========================================================

stop_times_fast = stop_times[
    [
        "trip_id",
        "arrival_time",
        "departure_time"
    ]
].copy()

print(
    "Optimalizált stop_times:",
    len(stop_times_fast),
    "sor"
)


# =========================================================
# 7. HELYSZÍNEK / GEO-KONFIGURÁCIÓ
# =========================================================

HELYSZINEK = {

    "bekasmegyer": {
        "kulcsszo": "Békásmegyer",
        "lat_min": 47.602215,
        "lat_max": 47.603865,
        "lon_min": 19.064990,
        "lon_max": 19.067875
    },

    "csepel_szent_imre": {
        "kulcsszo": "Csepel, Sz",
        "lat_min": 47.429951,
        "lat_max": 47.432414,
        "lon_min": 19.069806,
        "lon_max": 19.071954
    },

    "kobanya_also": {
        "kulcsszo": "Kőbánya a",
        "lat_min": 47.48245839589874,
        "lat_max": 47.484549999038826,
        "lon_min": 19.126114819497406,
        "lon_max": 19.12958305744741
    },

    "kobanya_kispest": {
        "kulcsszo": "Kőbánya-K",
        "lat_min": 47.46170217328866,
        "lat_max": 47.46269954567189,
        "lon_min": 19.15013411602212,
        "lon_max": 19.151115563166837
    },

    "mexikoi_ut": {
        "kulcsszo": "Mexikói út",
        "lat_min": 47.51961606697856,
        "lat_max": 47.52095851759252,
        "lon_min": 19.08940531844454,
        "lon_max": 19.092618832603126
    },

    "ors_vezer_E": {
        "kulcsszo": "Örs vezér tere M+H (é",
        "lat_min": 47.5037844857071,
        "lat_max": 47.505753039404794,
        "lon_min": 19.135811875938057,
        "lon_max": 19.137435732899583
    },

    "ors_vezer_D": {
        "kulcsszo": "Örs vezér tere M+H (d",
        "lat_min": 47.49940180349382,
        "lat_max": 47.50073054813034,
        "lon_min": 19.134581747988502,
        "lon_max": 19.136151481399818
    },

    "pestszentlorinc": {
        "kulcsszo": "Pestszentl",
        "lat_min": 47.45337269162761,
        "lat_max": 47.45651651124522,
        "lon_min": 19.178530697809354,
        "lon_max": 19.18350366084327
    }

}


print(
    "Helyszín-konfiguráció betöltve:",
    len(HELYSZINEK),
    "helyszín"
)


# =========================================================
# 8. EXCEL FÁJL
# =========================================================
#
# Az Excel a GitHub repón belül található:
#
# data/biztor_2026.10.xlsx
#
# Az év és hónap meghatározását az Excel-kezelő részben
# fogjuk elvégezni.
#
# =========================================================

print("GTFS és helyszín-konfiguráció betöltése kész.")
