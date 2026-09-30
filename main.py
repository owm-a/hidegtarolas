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

# =========================================================
# 9. EXCEL → AZNAPI MUNKALAP → FIGYELENDŐ FORDÁK
# =========================================================

from datetime import time
import openpyxl


# =========================================================
# 9/a. IDŐ KONVERTÁLÁSA
# =========================================================

def ido_konvertalasa(ertek):

    if pd.isna(ertek):
        return None

    # Ha Excel eleve time értéket adott
    if isinstance(ertek, time):
        return ertek

    # Ha datetime érték
    if isinstance(ertek, datetime):
        return ertek.time()

    # Szöveges idő
    szoveg = str(ertek).strip()

    if not szoveg:
        return None

    for fmt in [
        "%H:%M:%S",
        "%H:%M"
    ]:
        try:
            return datetime.strptime(
                szoveg,
                fmt
            ).time()

        except ValueError:
            continue

    raise ValueError(
        f"Nem értelmezhető időformátum: {ertek}"
    )


# =========================================================
# 9/b. AKTUÁLIS BUDAPESTI DÁTUM
# =========================================================

most = datetime.now(
    ZoneInfo("Europe/Budapest")
)

ev = most.strftime("%Y")
honap = most.strftime("%m")
nap = int(most.strftime("%d"))

ev_honap = f"{ev}.{honap}."
nap_keresett = f"{nap}."


print(
    "Excelhez használt dátum:",
    most.strftime("%Y-%m-%d")
)

print(
    "Keresett év/hónap:",
    ev_honap
)

print(
    "Keresett nap:",
    nap_keresett
)


# =========================================================
# 9/c. HAVI EXCEL FÁJL
# =========================================================

EXCEL_FAJL = (
    f"data/biztor_{ev}-{honap}.xlsx"
)

print(
    "Excel fájl:",
    EXCEL_FAJL
)


if not os.path.exists(EXCEL_FAJL):

    raise FileNotFoundError(
        f"Nem található az Excel fájl:\n"
        f"{EXCEL_FAJL}"
    )


# =========================================================
# 9/d. MUNKALAPOK MEGNYITÁSA
# =========================================================

wb = openpyxl.load_workbook(
    EXCEL_FAJL,
    read_only=True,
    data_only=True
)

munkalapok = wb.sheetnames

print(
    "Munkalapok száma:",
    len(munkalapok)
)

print(
    "Első munkalap kihagyva:",
    munkalapok[0]
)


# =========================================================
# 9/e. AZNAPI MUNKALAP KERESÉSE
# =========================================================

talalt_munkalap = None


for nev in munkalapok[1:]:

    ws = wb[nev]

    c4 = ws["C4"].value
    d4 = ws["D4"].value

    c4_szoveg = (
        ""
        if c4 is None
        else str(c4).strip()
    )

    d4_szoveg = (
        ""
        if d4 is None
        else str(d4).strip()
    )

    # C4-ben az év/hónap keresése
    if ev_honap not in c4_szoveg:
        continue

    # D4-ben a nap keresése
    napok = [
        x.strip()
        for x in d4_szoveg
        .replace(",", " ")
        .split()
    ]

    if nap_keresett in napok:

        talalt_munkalap = nev
        break


# =========================================================
# 9/f. ELLENŐRZÉS
# =========================================================

if talalt_munkalap is None:

    raise ValueError(
        f"Nem található az aktuális naphoz "
        f"tartozó munkalap.\n"
        f"Keresett C4: {ev_honap}\n"
        f"Keresett D4 nap: {nap_keresett}"
    )


print(
    "Talált munkalap:",
    talalt_munkalap
)


# =========================================================
# 9/g. MUNKALAP BEOLVASÁSA
# =========================================================

excel = pd.read_excel(
    EXCEL_FAJL,
    sheet_name=talalt_munkalap,
    header=None
)


print(
    "Munkalap beolvasva."
)

print(
    "Sorok száma:",
    len(excel)
)


# =========================================================
# 9/h. FORDÁK BEOLVASÁSA B8:F OSZLOPBÓL
# =========================================================

figyelt_fordak = []


for i in range(7, len(excel)):

    # -----------------------------------------------------
    # A oszlop
    # -----------------------------------------------------

    a_ertek = excel.iloc[i, 0]

    # Első "Őr" sornál megállunk
    if (
        pd.notna(a_ertek)
        and str(a_ertek).strip() == "Őr"
    ):
        break


    # -----------------------------------------------------
    # B–F oszlopok
    # -----------------------------------------------------

    viszonylat = excel.iloc[i, 1]
    forda = excel.iloc[i, 2]
    kezdes = excel.iloc[i, 3]
    vegzes = excel.iloc[i, 4]
    hely = excel.iloc[i, 5]


    # -----------------------------------------------------
    # Üres B/C sorok kihagyása
    # -----------------------------------------------------

    if (
        pd.isna(viszonylat)
        or pd.isna(forda)
    ):
        continue


    viszonylat = str(
        viszonylat
    ).strip()

    forda = str(
        forda
    ).strip()


    if not viszonylat or not forda:
        continue


    # -----------------------------------------------------
    # Excelből érkező .0 eltávolítása
    # -----------------------------------------------------

    if viszonylat.endswith(".0"):
        viszonylat = viszonylat[:-2]

    if forda.endswith(".0"):
        forda = forda[:-2]


    # -----------------------------------------------------
    # Kezdési idő
    # -----------------------------------------------------

    kezdes = ido_konvertalasa(
        kezdes
    )


    # -----------------------------------------------------
    # Végzési idő
    # -----------------------------------------------------

    vegzes = ido_konvertalasa(
        vegzes
    )


    # -----------------------------------------------------
    # Hely
    # -----------------------------------------------------

    if pd.notna(hely):

        hely = str(
            hely
        ).strip()

    else:

        hely = ""


    # =====================================================
    # 9/i. EXCEL HELY → HELYSZÍN
    # =====================================================

    helyszin_talalatok = []

    hely_normalizalt = (
        hely.casefold()
    )


    for helyszin_kulcs, adat in HELYSZINEK.items():

        kulcsszo = (
            adat["kulcsszo"]
            .casefold()
        )

        if hely_normalizalt.startswith(
            kulcsszo
        ):

            helyszin_talalatok.append(
                helyszin_kulcs
            )


    # =====================================================
    # 9/j. HELYSZÍN ELLENŐRZÉSE
    # =====================================================

    if len(helyszin_talalatok) == 0:

        print(
            f"FIGYELEM: nincs helyszín-"
            f"konfiguráció ehhez: {hely}"
        )

        helyszin = ""


    elif len(helyszin_talalatok) > 1:

        raise ValueError(
            f"Több helyszín illeszkedik ehhez: "
            f"{hely}\n"
            f"Találatok: "
            f"{helyszin_talalatok}"
        )


    else:

        helyszin = (
            helyszin_talalatok[0]
        )


    # =====================================================
    # 9/k. ADAT HOZZÁADÁSA
    # =====================================================

    figyelt_fordak.append({

        "viszonylat": viszonylat,

        "forda": forda,

        "kezdés": kezdes,

        "végzés": vegzes,

        "hely": hely,

        "helyszín": helyszin

    })


# =========================================================
# 9/l. ELLENŐRZÉS
# =========================================================

figyelt_fordak = pd.DataFrame(
    figyelt_fordak
)


print(
    "Figyelt fordák:",
    len(figyelt_fordak)
)

print(
    figyelt_fordak.to_string(
        index=False
    )
)
