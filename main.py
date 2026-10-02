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

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from google.transit import gtfs_realtime_pb2

print("Modulok betöltve.")


# =========================================================
# 3. BKK GTFS BETÖLTÉSE
# =========================================================
#
# A GTFS-t naponta csak egyszer töltjük le.
#
# Az első napi futáskor:
#   1. ellenőrizzük a GTFS cache-t
#   2. ha előző napi GTFS van benne, töröljük
#   3. letöltjük az aktuális GTFS-t
#   4. elmentjük a cache-be
#
# A nap további futásai ugyanazt a GTFS-t használják.
#
# =========================================================

GTFS_URL = (
    "https://go.bkk.hu/api/static/v1/public-gtfs/"
    "budapest_gtfs.zip"
)

GTFS_CACHE_DIR = "gtfs_cache"

GTFS_CACHE_FILE = os.path.join(
    GTFS_CACHE_DIR,
    "budapest_gtfs.zip"
)

GTFS_DATE_FILE = os.path.join(
    GTFS_CACHE_DIR,
    "letoltes_datum.txt"
)


# =========================================================
# 3/a. CACHE MAPPA LÉTREHOZÁSA
# =========================================================

os.makedirs(
    GTFS_CACHE_DIR,
    exist_ok=True
)


# =========================================================
# 3/b. AKTUÁLIS BUDAPESTI DÁTUM
# =========================================================

budapesti_datum = datetime.now(
    ZoneInfo("Europe/Budapest")
).strftime("%Y-%m-%d")


# =========================================================
# 3/c. MEGNÉZZÜK, MELYIK NAPHOZ TARTOZIK A CACHE
# =========================================================

tarolt_datum = None

if os.path.exists(GTFS_DATE_FILE):

    with open(
        GTFS_DATE_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        tarolt_datum = f.read().strip()


# =========================================================
# 3/d. ELSŐ FUTÁS / ÚJ NAP ELLENŐRZÉSE
# =========================================================

if (
    tarolt_datum != budapesti_datum
    or not os.path.exists(GTFS_CACHE_FILE)
):

    print()
    print(
        "Új nap vagy hiányzó GTFS cache."
    )

    print(
        "Régi GTFS törlése..."
    )


    # -----------------------------------------------------
    # Régi GTFS törlése
    # -----------------------------------------------------

    if os.path.exists(GTFS_CACHE_FILE):

        os.remove(
            GTFS_CACHE_FILE
        )

        print(
            "Régi GTFS törölve."
        )


    # -----------------------------------------------------
    # Új GTFS letöltése
    # -----------------------------------------------------

    print(
        "Új GTFS letöltése..."
    )

    gtfs_response = requests.get(
        GTFS_URL,
        timeout=60
    )


    if gtfs_response.status_code != 200:

        raise Exception(
            f"GTFS letöltési hiba. "
            f"HTTP státusz: "
            f"{gtfs_response.status_code}"
        )


    # -----------------------------------------------------
    # Új GTFS mentése
    # -----------------------------------------------------

    with open(
        GTFS_CACHE_FILE,
        "wb"
    ) as f:

        f.write(
            gtfs_response.content
        )


    # -----------------------------------------------------
    # Aktuális dátum mentése
    # -----------------------------------------------------

    with open(
        GTFS_DATE_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(
            budapesti_datum
        )


    print(
        "Új GTFS sikeresen letöltve."
    )


# =========================================================
# 3/e. HA MÁR VAN MAI GTFS
# =========================================================

else:

    print()
    print(
        "A mai GTFS már rendelkezésre áll."
    )

    print(
        "Új letöltés nem szükséges."
    )


# =========================================================
# 3/f. GTFS ZIP MEGNYITÁSA
# =========================================================

with open(
    GTFS_CACHE_FILE,
    "rb"
) as f:

    gtfs_zip = zipfile.ZipFile(
        io.BytesIO(
            f.read()
        )
    )


print()
print(
    "GTFS betöltve."
)

print(
    f"Fájlok száma: "
    f"{len(gtfs_zip.namelist())}"
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
        "kulcsszo": "Csepel, Szent Imre tér",
        "lat_min": 47.429951,
        "lat_max": 47.432414,
        "lon_min": 19.069806,
        "lon_max": 19.071954
    },

    "kobanya_also": {
        "kulcsszo": "Kőbánya alsó",
        "lat_min": 47.482374761566106,
        "lat_max": 47.48497049937554,
        "lon_min": 19.126160600151543,
        "lon_max": 19.131138742642598
    },

    "kobanya_kispest": {
        "kulcsszo": "Kőbánya-Kispest",
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
        "kulcsszo": "Örs vezér tere M+H (észak",
        "lat_min": 47.5037844857071,
        "lat_max": 47.505753039404794,
        "lon_min": 19.135811875938057,
        "lon_max": 19.137435732899583
    },

    "ors_vezer_D": {
        "kulcsszo": "Örs vezér tere M+H (dél",
        "lat_min": 47.49940180349382,
        "lat_max": 47.50073054813034,
        "lon_min": 19.134581747988502,
        "lon_max": 19.136151481399818
    },

    "pestszentlorinc": {
        "kulcsszo": "Pestszentlőrinc",
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

def forda_aktiv_e(kezdés, végzés, időpont):

    if not kezdés or not végzés or not időpont:
        return False

    try:
        kezdés_dt = datetime.strptime(kezdés, "%H:%M:%S")
        végzés_dt = datetime.strptime(végzés, "%H:%M:%S")
        időpont_dt = datetime.strptime(időpont, "%H:%M:%S")
    except (ValueError, TypeError):
        return False

    ellenőrzési_kezdés = kezdés_dt - timedelta(minutes=5)
    ellenőrzési_végzés = végzés_dt + timedelta(minutes=10)

    return ellenőrzési_kezdés <= időpont_dt <= ellenőrzési_végzés


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

# =========================================================
# 10. FORDA → RENDSZÁM
# 07:00–08:30 AZONOSÍTÁSI FÁZIS
# =========================================================

import json

# =========================================================
# 10/a. AKTUÁLIS FÁZIS
# =========================================================

fazis_ideje = datetime.now(
    ZoneInfo("Europe/Budapest")
).time()

azonositas_idoszak = (
    time(7, 0)
    <= fazis_ideje
    <= time(13, 0)
)

pozicio_idoszak = (
    time(8, 0)
    <= fazis_ideje
    <= time(17, 0)
)

print()
print(
    "Budapesti aktuális idő:",
    fazis_ideje.strftime("%H:%M:%S")
)

if azonositas_idoszak:

    print(
        "Aktív fázis: 07:00–08:30 "
        "forda → rendszám"
    )

elif pozicio_idoszak:

    print(
        "Aktív fázis: 08:00–17:00 "
        "rendszám → pozíció"
    )

else:

    print(
        "Jelenleg nincs aktív adatgyűjtési fázis."
    )
# =========================================================
# 10/a. NAPI ADATFÁJL
# =========================================================

NAPI_ADATOK_FAJL = "napi_adatok.json"

MAI_NAP = datetime.now(
    ZoneInfo("Europe/Budapest")
).strftime("%Y-%m-%d")


# =========================================================
# 10/b. KORÁBBI NAPI ADATOK BETÖLTÉSE
# =========================================================

if os.path.exists(NAPI_ADATOK_FAJL):

    with open(
        NAPI_ADATOK_FAJL,
        "r",
        encoding="utf-8"
    ) as f:

        napi_adatok = json.load(f)

else:

    napi_adatok = {}


# ---------------------------------------------------------
# Ha új nap van, új napi adatállomány indul
# ---------------------------------------------------------

if napi_adatok.get("datum") != MAI_NAP:

    napi_adatok = {
        "datum": MAI_NAP,
        "forda_rendszamok": {},
        "pozicio_tortenet": []
    }


# =========================================================
# 10/c. FORDA → RENDSZÁM ADATOK
# =========================================================

forda_rendszamok = napi_adatok.get(
    "forda_rendszamok",
    {}
)


print(
    "Napi adatfájl:",
    NAPI_ADATOK_FAJL
)

print(
    "Napi dátum:",
    MAI_NAP
)

print(
    "Korábban mentett forda → rendszám párok:",
    len(forda_rendszamok)
)


# =========================================================
# 10/d. AKTUÁLIS VEHICLEPOSITIONS LEKÉRÉSE
# =========================================================

url = (
    "https://go.bkk.hu/api/query/v1/ws/"
    "gtfs-rt/full/VehiclePositions.pb"
)

response = requests.get(
    url,
    params={"key": API_KEY},
    timeout=30
)

if response.status_code != 200:

    raise Exception(
        f"GTFS-RT lekérési hiba. "
        f"HTTP státusz: {response.status_code}"
    )


print(
    "GTFS-RT HTTP státusz:",
    response.status_code
)

print(
    "Kapott adatmennyiség:",
    len(response.content),
    "byte"
)


# =========================================================
# 10/e. GTFS-RT FELDOLGOZÁSA
# =========================================================

feed = gtfs_realtime_pb2.FeedMessage()

feed.ParseFromString(
    response.content
)


print(
    "Járművek száma:",
    len(feed.entity)
)


# =========================================================
# 10/f. AKTUÁLIS RT JÁRMŰVEK
# =========================================================

jarmuvek = []


for entity in feed.entity:

    if not entity.HasField("vehicle"):
        continue

    v = entity.vehicle

    jarmuvek.append({

        "rendszám": (
            str(v.vehicle.license_plate)
            .strip()
        ),

        "jármű_id": v.vehicle.id,

        "trip_id": v.trip.trip_id,

        "route_id": v.trip.route_id,

        "direction_id": v.trip.direction_id,

        "latitude": v.position.latitude,

        "longitude": v.position.longitude,

        "megálló": v.stop_id,

        "timestamp": v.timestamp

    })


jarmuvek = pd.DataFrame(
    jarmuvek
)


print(
    "RT járművek:",
    len(jarmuvek)
)

print(
    "Rendszámmal rendelkező járművek:",
    jarmuvek["rendszám"]
    .fillna("")
    .astype(str)
    .str.strip()
    .ne("")
    .sum()
)


# =========================================================
# 10/g. AKTUÁLIS IDŐ
# =========================================================

idopont = datetime.now(
    ZoneInfo("Europe/Budapest")
).strftime("%H:%M:%S")


print()
print(
    "RT feldolgozás időpontja:",
    idopont
)


# =========================================================
# 10/h. MAI SERVICE ID-K
# =========================================================

mai_service_ids = set(
    mai_calendar.loc[
        mai_calendar["exception_type"].astype(str) == "1",
        "service_id"
    ].astype(str)
)


# =========================================================
# 10/i. MINDEN FIGYELT FORDA FELDOLGOZÁSA
# =========================================================

sikeres_frissitesek = 0


for _, forda_sor in (
    figyelt_fordak.iterrows()
    if azonositas_idoszak
    else []
):

    viszonylat = str(
        forda_sor["viszonylat"]
    ).strip()

    forda = str(
        forda_sor["forda"]
    ).strip()

    forda_kulcs = (
        f"{viszonylat}|{forda}"
    )


    # -----------------------------------------------------
    # A forda mai blockjai
    # -----------------------------------------------------

    forda_trips = trips[
        (
            trips["service_id"]
            .astype(str)
            .isin(mai_service_ids)
        )
        &
        (
            trips["block_id"]
            .astype(str)
            .str.contains(
                f"_{viszonylat}_{forda}_",
                na=False
            )
        )
    ].copy()


    if len(forda_trips) == 0:
        continue


    # -----------------------------------------------------
    # Trip ID-k
    # -----------------------------------------------------

    forda_trip_ids = set(
        forda_trips["trip_id"]
        .astype(str)
    )


    # -----------------------------------------------------
    # Stop times
    # -----------------------------------------------------

    forda_stop_times = stop_times_fast[
        stop_times_fast["trip_id"]
        .astype(str)
        .isin(forda_trip_ids)
    ].copy()


    if len(forda_stop_times) == 0:
        continue


    # -----------------------------------------------------
    # Tripenként kezdő és végző idő
    # -----------------------------------------------------

    forda_idok = (
        forda_stop_times
        .groupby(
            "trip_id",
            sort=False
        )
        .agg(
            kezdet=("departure_time", "min"),
            vége=("arrival_time", "max")
        )
        .reset_index()
    )


    # -----------------------------------------------------
    # GTFS trip + időpontok
    # -----------------------------------------------------

    forda_idok = forda_trips.merge(
        forda_idok,
        on="trip_id",
        how="left"
    )


    # -----------------------------------------------------
    # Aktívan futó trip
    # -----------------------------------------------------

    aktiv_trip = forda_idok[
        (forda_idok["kezdet"] <= idopont)
        &
        (forda_idok["vége"] >= idopont)
    ].copy()


    if len(aktiv_trip) == 0:
        continue


    # -----------------------------------------------------
    # Aktív trip → RT jármű
    # -----------------------------------------------------

    keresett_trip_ids = set(
        aktiv_trip["trip_id"]
        .astype(str)
    )


    rt_talalatok = jarmuvek[
        jarmuvek["trip_id"]
        .astype(str)
        .isin(keresett_trip_ids)
    ].copy()


    if len(rt_talalatok) == 0:
        continue


    # -----------------------------------------------------
    # SIKERES TALÁLAT
    #
    # Csak sikeres találat esetén írjuk felül
    # a korábbi rendszámot.
    # -----------------------------------------------------

    for _, rt in rt_talalatok.iterrows():

        rendszam = str(
            rt["rendszám"]
        ).strip()


        if rendszam == "":
            continue


        # -------------------------------------------------
        # Sikeres rendszámmentés
        # -------------------------------------------------

        forda_rendszamok[forda_kulcs] = {

            "viszonylat": viszonylat,

            "forda": forda,

            "kezdés": (
                forda_sor["kezdés"].strftime("%H:%M:%S")
                if pd.notna(forda_sor["kezdés"])
                else None
            ),

            "végzés": (
                forda_sor["végzés"].strftime("%H:%M:%S")
                if pd.notna(forda_sor["végzés"])
                else None
            ),

            "hely": str(
                forda_sor["hely"]
            ),

            "helyszín": str(
                forda_sor["helyszín"]
            ),

            "rendszám": rendszam,

            "frissítve": idopont

        }


        sikeres_frissitesek += 1

        break


# =========================================================
# 10/j. NAPI ADATOK MENTÉSE
# =========================================================

napi_adatok["datum"] = MAI_NAP

napi_adatok["forda_rendszamok"] = (
    forda_rendszamok
)


with open(
    NAPI_ADATOK_FAJL,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        napi_adatok,
        f,
        ensure_ascii=False,
        indent=2
    )


# =========================================================
# 10/k. EREDMÉNY
# =========================================================

print()
print(
    "Sikeres új/megújított "
    "forda → rendszám találatok:",
    sikeres_frissitesek
)

print(
    "Összes mentett "
    "forda → rendszám kapcsolat:",
    len(forda_rendszamok)
)


if len(forda_rendszamok) > 0:

    rt_fordak = pd.DataFrame(
        list(forda_rendszamok.values())
    )

    rt_fordak = rt_fordak[
        [
            "viszonylat",
            "forda",
            "kezdés",
            "végzés",
            "hely",
            "helyszín",
            "rendszám",
            "frissítve"
        ]
    ]

    rt_fordak = rt_fordak.sort_values(
        by=[
            "viszonylat",
            "forda"
        ]
    ).reset_index(drop=True)


    print()
    print(
        "Mentett forda → rendszám párok:"
    )

    print(
        rt_fordak.to_string(
            index=False
        )
    )

else:

    rt_fordak = pd.DataFrame()

    print()
    print(
        "Még nincs sikeresen azonosított "
        "forda → rendszám kapcsolat."
    )

# ============================================================
# 10:00–14:00
# RENDSZÁM → AKTUÁLIS POZÍCIÓ
# MINDEN SIKERES LEKÉRDEZÉS KÜLÖN REKORD
# ============================================================

from datetime import datetime
from zoneinfo import ZoneInfo
import requests
import pandas as pd
import time as time_module


print("\n=== 10:00–14:00 pozíciólekérés ===")


# ============================================================
# 1. Aktuális budapesti idő
# ============================================================

most = datetime.now(
    ZoneInfo("Europe/Budapest")
)

idopont = most.strftime("%H:%M:%S")

print("Pozíciólekérdezés időpontja:", idopont)


# ============================================================
# 2. FRISS VehiclePositions.pb lekérése
#    Legfeljebb 3 próbálkozás
# ============================================================

url = (
    "https://go.bkk.hu/api/query/v1/ws/"
    "gtfs-rt/full/VehiclePositions.pb"
)

feed = None

for probalkozas in (
    range(1, 4)
    if pozicio_idoszak
    else []
):

    print(
        f"VehiclePositions lekérés "
        f"({probalkozas}/3)..."
    )

    try:

        response = requests.get(
            url,
            params={"key": API_KEY},
            timeout=30
        )

        print(
            "HTTP státusz:",
            response.status_code
        )

        print(
            "Kapott adatmennyiség:",
            len(response.content),
            "byte"
        )

        if response.status_code != 200:
            raise Exception(
                f"HTTP hiba: "
                f"{response.status_code}"
            )

        # ----------------------------------------------------
        # Protobuf feldolgozás
        # ----------------------------------------------------

        feed_teszt = (
            gtfs_realtime_pb2.FeedMessage()
        )

        feed_teszt.ParseFromString(
            response.content
        )

        # Ha idáig eljutottunk, az adat érvényes
        feed = feed_teszt

        print("Érvényes GTFS-RT adat érkezett.")

        break

    except Exception as e:

        print(
            f"VehiclePositions hiba: {e}"
        )

        if probalkozas < 3:

            print(
                "Újrapróbálkozás 2 másodperc múlva..."
            )

            time_module.sleep(2)

        else:

            print(
                "A 3 próbálkozás mind sikertelen."
            )


# ============================================================
# 3. Ha egyik lekérés sem sikerült
# ============================================================

if feed is None:

    print(
        "Nincs feldolgozható VehiclePositions adat."
    )

    # Nincs új pozíciórekord,
    # de a korábban mentett adatok megmaradnak.

    napi_adatok["pozicio_tortenet"] = (
        napi_adatok.get(
            "pozicio_tortenet",
            []
        )
    )

    with open(
        NAPI_ADATOK_FAJL,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            napi_adatok,
            f,
            ensure_ascii=False,
            indent=2
        )

    print(
        "A korábbi pozíciótörténet változatlanul mentve."
    )

else:

    # ========================================================
    # 4. Aktuális rendszámok és pozíciók
    # ========================================================

    jarmuvek = []

    for entity in feed.entity:

        if not entity.HasField("vehicle"):
            continue

        v = entity.vehicle

        rendszam = (
            str(v.vehicle.license_plate)
            .strip()
            .upper()
        )

        if not rendszam:
            continue

        # Csak olyan jármű kell,
        # amelyhez van pozícióadat.

        if not v.HasField("position"):
            continue

        jarmuvek.append({
            "rendszám": rendszam,
            "latitude": v.position.latitude,
            "longitude": v.position.longitude
        })


    jarmuvek = pd.DataFrame(
        jarmuvek
    )

    print(
        "Rendszámmal rendelkező "
        "RT-járművek:",
        len(jarmuvek)
    )


    # ========================================================
    # 5. Pozíciótörténet betöltése a napi JSON-ból
    # ========================================================

    pozicio_tortenet = (
        napi_adatok.get(
            "pozicio_tortenet",
            []
        )
    )


    # ========================================================
    # 6. A rögzített rendszámok keresése
    # ========================================================

    uj_poziciok = 0

    for forda_kulcs, adat in (
        forda_rendszamok.items()
    ):

        rendszam = (
            str(adat["rendszám"])
            .strip()
            .upper()
        )

        talalat = jarmuvek[
            jarmuvek["rendszám"] == rendszam
        ]


        # ----------------------------------------------------
        # Nincs aktuális RT találat
        #
        # → utolsó ismert pozíció használata
        # ----------------------------------------------------

        if len(talalat) == 0:

            elozo_pozicio = None

            # Visszafelé keresünk, így az első találat
            # automatikusan az utolsó ismert pozíció.
            for elozo in reversed(pozicio_tortenet):

                if (
                    str(
                        elozo.get(
                            "rendszám",
                            ""
                        )
                    ).strip().upper()
                    == rendszam
                ):
                    elozo_pozicio = elozo.get(
                        "pozíció"
                    )
                    break


            # Ha még soha nem volt pozíció ehhez a járműhöz
            if elozo_pozicio is None:

                print(
                    f"{forda_kulcs}: "
                    f"{rendszam} – nincs RT találat, "
                    f"korábbi pozíció sincs"
                )

                continue


            # Utolsó ismert pozíció használata
            pozicio = elozo_pozicio

            print(
                f"{forda_kulcs}: "
                f"{rendszam} – nincs RT találat, "
                f"utolsó ismert pozíció: {pozicio}"
            )


        # ----------------------------------------------------
        # Van aktuális RT találat
        # ----------------------------------------------------

        else:

            rt = talalat.iloc[0]

            pozicio = (
                f"{rt['latitude']}, "
                f"{rt['longitude']}"
            )

            print(
                f"{forda_kulcs}: "
                f"{rendszam} → "
                f"{pozicio}"
            )


        # ----------------------------------------------------
        # POZÍCIÓ ELLENŐRZÉSE
        # ----------------------------------------------------

        ellenorzes = "-"

        # Csak akkor ellenőrizzük a helyszínt,
        # ha a forda az adott időpontban aktív

        if not forda_aktiv_e(
            adat["kezdés"],
            adat["végzés"],
            idopont
        ):

            ellenorzes = "-"

        else:

            helyszin_kulcs = str(
                adat.get(
                    "helyszín",
                    ""
                )
            ).strip()


            if helyszin_kulcs in HELYSZINEK:

                try:

                    latitude_szoveg, longitude_szoveg = (
                        pozicio.split(",", 1)
                    )

                    latitude = float(
                        latitude_szoveg.strip()
                    )

                    longitude = float(
                        longitude_szoveg.strip()
                    )

                    helyszin = HELYSZINEK[
                        helyszin_kulcs
                    ]

                    lat_benne = (
                        helyszin["lat_min"]
                        <= latitude
                        <= helyszin["lat_max"]
                    )

                    lon_benne = (
                        helyszin["lon_min"]
                        <= longitude
                        <= helyszin["lon_max"]
                    )

                    if lat_benne and lon_benne:

                        ellenorzes = "OK"

                    else:

                        ellenorzes = "NEM"

                except (
                    ValueError,
                    TypeError
                ):

                    ellenorzes = "-"


        # ----------------------------------------------------
        # ÚJ történeti rekord
        #
        # Friss RT pozíció vagy utolsó ismert pozíció.
        # Az OK/NEM eredmény is mentésre kerül.
        # ----------------------------------------------------

        pozicio_tortenet.append({

            "viszonylat": adat["viszonylat"],

            "forda": adat["forda"],

            "kezdés": adat["kezdés"],

            "végzés": adat["végzés"],

            "hely": adat["hely"],

            "helyszín": adat["helyszín"],

            "rendszám": rendszam,

            "pozíció": pozicio,

            "ellenőrzés": ellenorzes,

            "frissítve": idopont
        })


        uj_poziciok += 1

        print(
            f"{forda_kulcs}: "
            f"{rendszam} → "
            f"{pozicio}"
        )


    # ========================================================
    # 7. JSON frissítése
    # ========================================================

    napi_adatok["datum"] = MAI_NAP

    napi_adatok["forda_rendszamok"] = (
        forda_rendszamok
    )

    napi_adatok["pozicio_tortenet"] = (
        pozicio_tortenet
    )


    with open(
        NAPI_ADATOK_FAJL,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            napi_adatok,
            f,
            ensure_ascii=False,
            indent=2
        )


    # ========================================================
    # 8. Összesítés
    # ========================================================

    print()

    print(
        "Új pozíciórekordok:",
        uj_poziciok
    )

    print(
        "Összes pozíciórekord:",
        len(pozicio_tortenet)
    )

    print(
        "napi_adatok.json frissítve."
    )

#---------------------------------------------------------------------------------------------------------------

# ============================================================
# HELYSZÍN ELLENŐRZÉS
# ============================================================

print()
print("=== HELYSZÍN ELLENŐRZÉS ===")

poziciok = napi_adatok.get(
    "pozicio_tortenet",
    []
)

print(
    "Vizsgált pozíciórekordok:",
    len(poziciok)
)

ellenorzesek = []


# ============================================================
# POZÍCIÓREKORDOK EGYENKÉNTI ELLENŐRZÉSE
# ============================================================

for rekord in poziciok:

    viszonylat = str(
        rekord.get("viszonylat", "")
    ).strip()

    forda = str(
        rekord.get("forda", "")
    ).strip()

    hely = str(
        rekord.get("hely", "")
    ).strip()

    rendszam = str(
        rekord.get("rendszám", "")
    ).strip()

    idopont = str(
        rekord.get("frissítve", "")
    ).strip()


    # --------------------------------------------------------
    # FORDA ADATOK KERESÉSE
    # --------------------------------------------------------

    forda_adat = forda_rendszamok.get(
        f"{viszonylat}|{forda}"
    )


    # Ha nincs fordaadat, nincs értékelhető eredmény

    if forda_adat is None:

        ellenorzesek.append({

            "viszonylat": viszonylat,

            "forda": forda,

            "hely": hely,

            "rendszám": rendszam,

            "időpont": idopont,

            "ellenőrzés": "-"

        })

        continue


    kezdés = str(
        forda_adat.get(
            "kezdés",
            ""
        )
    ).strip()

    végzés = str(
        forda_adat.get(
            "végzés",
            ""
        )
    ).strip()


    # --------------------------------------------------------
    # AKTUÁLIS-E A FORDA AZ ADOTT IDŐPONTBAN?
    # --------------------------------------------------------

    if not forda_aktiv_e(
        kezdés,
        végzés,
        idopont
    ):

        ellenorzesek.append({

            "viszonylat": viszonylat,

            "forda": forda,

            "hely": hely,

            "rendszám": rendszam,

            "időpont": idopont,

            "ellenőrzés": "-"

        })

        continue


    # --------------------------------------------------------
    # HELYSZÍN AZONOSÍTÁSA
    # --------------------------------------------------------

    helyszin_kulcs = str(
        rekord.get(
            "helyszín",
            ""
        )
    ).strip()


    if not helyszin_kulcs:

        ellenorzesek.append({

            "viszonylat": viszonylat,

            "forda": forda,

            "hely": hely,

            "rendszám": rendszam,

            "időpont": idopont,

            "ellenőrzés": "-"

        })

        continue


    if helyszin_kulcs not in HELYSZINEK:

        ellenorzesek.append({

            "viszonylat": viszonylat,

            "forda": forda,

            "hely": hely,

            "rendszám": rendszam,

            "időpont": idopont,

            "ellenőrzés": "-"

        })

        continue


    helyszin = HELYSZINEK[
        helyszin_kulcs
    ]


    # --------------------------------------------------------
    # GPS POZÍCIÓ KINYERÉSE
    # --------------------------------------------------------

    pozicio_szoveg = str(
        rekord.get(
            "pozíció",
            ""
        )
    ).strip()


    if not pozicio_szoveg:

        ellenorzesek.append({

            "viszonylat": viszonylat,

            "forda": forda,

            "hely": hely,

            "rendszám": rendszam,

            "időpont": idopont,

            "ellenőrzés": "-"

        })

        continue


    try:

        latitude_szoveg, longitude_szoveg = (
            pozicio_szoveg.split(",", 1)
        )

        latitude = float(
            latitude_szoveg.strip()
        )

        longitude = float(
            longitude_szoveg.strip()
        )

    except (ValueError, TypeError):

        ellenorzesek.append({

            "viszonylat": viszonylat,

            "forda": forda,

            "hely": hely,

            "rendszám": rendszam,

            "időpont": idopont,

            "ellenőrzés": "-"

        })

        continue


    # --------------------------------------------------------
    # GPS ELLENŐRZÉS
    # --------------------------------------------------------

    lat_benne = (
        helyszin["lat_min"]
        <= latitude
        <= helyszin["lat_max"]
    )

    lon_benne = (
        helyszin["lon_min"]
        <= longitude
        <= helyszin["lon_max"]
    )


    if lat_benne and lon_benne:

        eredmeny = "OK"

    else:

        eredmeny = "NEM"


    # --------------------------------------------------------
    # EREDMÉNY
    # --------------------------------------------------------

    ellenorzesek.append({

        "viszonylat": viszonylat,

        "forda": forda,

        "hely": hely,

        "rendszám": rendszam,

        "időpont": idopont,

        "ellenőrzés": eredmeny

    })


# ============================================================
# DATAFRAME
# ============================================================

helyszin_ellenorzes = pd.DataFrame(
    ellenorzesek,
    columns=[
        "viszonylat",
        "forda",
        "hely",
        "rendszám",
        "időpont",
        "ellenőrzés"
    ]
)


# ============================================================
# RENDEZÉS
# ============================================================

if len(helyszin_ellenorzes) > 0:

    helyszin_ellenorzes = (
        helyszin_ellenorzes
        .sort_values(
            by=[
                "viszonylat",
                "forda",
                "időpont"
            ]
        )
        .reset_index(drop=True)
    )


# ============================================================
# KIÍRÁS
# ============================================================

print()

if len(helyszin_ellenorzes) > 0:

    print(
        helyszin_ellenorzes.to_string(
            index=False
        )
    )

else:

    print(
        "Nincs ellenőrizhető pozíciórekord."
    )


# ============================================================
# ÖSSZESÍTÉS
# ============================================================

print()

print(
    "OK:",
    (
        helyszin_ellenorzes[
            helyszin_ellenorzes[
                "ellenőrzés"
            ] == "OK"
        ].shape[0]
    )
)

print(
    "NEM:",
    (
        helyszin_ellenorzes[
            helyszin_ellenorzes[
                "ellenőrzés"
            ] == "NEM"
        ].shape[0]
    )
)

print(
    "-:",
    (
        helyszin_ellenorzes[
            helyszin_ellenorzes[
                "ellenőrzés"
            ] == "-"
        ].shape[0]
    )
)


# ============================================================
# NAPI HIDEGTÁROLÁSI RIPORT
# 16:30 UTÁN EGYSZER NAPONTA
# ============================================================

RIport_XLSX = "data/hidegtarolas_export.xlsx"


def hidegtarolas_riport_eredmeny(forda_sor, pozicio_tortenet):
    """
    A hidegtárolási szabály:

    1. Megkeressük a forda kezdése után az első OK mérést.
    2. Az első OK-tól kezdődő folyamatos OK-szakasznak el kell érnie
       a teljes fordaidő 70%-át.
    3. NEM és - megszakítja a folyamatos OK-szakaszt.
    4. Adatkimaradás önmagában nem szakítja meg.
    5. Az első OK előtti NEM és - nem számít.
    """

    kezdés = forda_sor.get("kezdés")
    végzés = forda_sor.get("végzés")

    if pd.isna(kezdés) or pd.isna(végzés):
        return "ELTÉRÉS TÖRTÉNT"

    budapest_tz = ZoneInfo("Europe/Budapest")
    budapest_now = datetime.now(budapest_tz)
    mai_datum = budapest_now.date()

    kezdés_dt = datetime.combine(
        mai_datum,
        kezdés,
        tzinfo=budapest_tz
    )

    végzés_dt = datetime.combine(
        mai_datum,
        végzés,
        tzinfo=budapest_tz
    )

    # Éjfélen átnyúló forda
    if végzés_dt < kezdés_dt:
        végzés_dt += timedelta(days=1)

    teljes_idotartam = (
        végzés_dt - kezdés_dt
    ).total_seconds()

    if teljes_idotartam <= 0:
        return "ELTÉRÉS TÖRTÉNT"

    # A teljes fordaidő 70%-a.
    szukseges_ok_idotartam = (
        teljes_idotartam * 0.70
    )

    # A vizsgálat legfeljebb a forda végéig tart.
    vizsgalat_vege = min(
        budapest_now,
        végzés_dt
    )

    # Csak a forda kezdése után és a vizsgálat végéig
    # tartó rekordokat vesszük figyelembe.
    rekordok = []

    for rekord in pozicio_tortenet:

        try:
            if (
                str(rekord.get("viszonylat", "")).strip()
                != str(forda_sor.get("viszonylat", "")).strip()
            ):
                continue

            if (
                str(rekord.get("forda", "")).strip()
                != str(forda_sor.get("forda", "")).strip()
            ):
                continue

            idopont = str(
                rekord.get("frissítve", "")
            ).strip()

            if not idopont:
                continue

            ido = datetime.strptime(
                idopont,
                "%H:%M:%S"
            ).time()

            dt = datetime.combine(
                kezdés_dt.date(),
                ido,
                tzinfo=budapest_tz
            )

            if dt < kezdés_dt:
                dt += timedelta(days=1)

            if kezdés_dt < dt <= vizsgalat_vege:
                rekordok.append({
                    "idő": dt,
                    "állapot": str(
                        rekord.get("ellenőrzés", "-")
                    ).strip().upper()
                })

        except (ValueError, TypeError):
            continue

    if not rekordok:
        return "ELTÉRÉS TÖRTÉNT"

    # Azonos időpontból csak egy állapot maradjon.
    rekordok.sort(key=lambda x: x["idő"])

    idopont_allapot = {}

    for rekord in rekordok:
        idopont_allapot[rekord["idő"]] = rekord["állapot"]

    rekordok = [
        {"idő": dt, "állapot": allapot}
        for dt, allapot in sorted(
            idopont_allapot.items()
        )
    ]

    # ------------------------------------------------------------
    # Az első OK megkeresése.
    # Az előtte lévő NEM / - nem számít.
    # ------------------------------------------------------------
    elso_ok_index = None

    for index, rekord in enumerate(rekordok):
        if rekord["állapot"] == "OK":
            elso_ok_index = index
            break

    if elso_ok_index is None:
        return "ELTÉRÉS TÖRTÉNT"

    # ------------------------------------------------------------
    # Az első OK-tól folyamatos OK-szakasz.
    #
    # NEM vagy - azonnal megszakítja.
    # Adatkimaradás nem szakítja meg, ezért itt nincs
    # semmilyen 10 perces / időréses ellenőrzés.
    # ------------------------------------------------------------
    elso_ok_ido = rekordok[elso_ok_index]["idő"]

    for rekord in rekordok[elso_ok_index + 1:]:

        if rekord["állapot"] != "OK":
            return "ELTÉRÉS TÖRTÉNT"

    # ------------------------------------------------------------
    # A folyamatos OK-szakasz végét a vizsgálat vége jelenti.
    # Ez lehet a forda vége, vagy az aktuális időpont.
    # ------------------------------------------------------------
    folyamatos_ok_idotartam = (
        vizsgalat_vege - elso_ok_ido
    ).total_seconds()

    # ------------------------------------------------------------
    # A folyamatos OK-szakasznak kell elérnie a teljes
    # fordaidő 70%-át.
    # ------------------------------------------------------------
    if folyamatos_ok_idotartam < szukseges_ok_idotartam:
        return "ELTÉRÉS TÖRTÉNT"

    return "RENDBEN TÁROLT"

def keszit_hidegtarolas_riport():
    """
    16:30 után minden futáskor újraszámolja a napi riportot.

    A HTML mindig a legfrissebb eredményt kapja.
    Az Excelbe ugyanaz a nap csak egyszer kerül be.
    """

    budapesti_most = datetime.now(
        ZoneInfo("Europe/Budapest")
    )

    # 16:30 előtt még nincs hidegtárolási riport,
    # de a HTML exportnak ettől még le kell futnia.
    # Ilyenkor egy üres riportstruktúrát adunk vissza,
    # így a mai oldal elkészülhet a nap folyamán gyűjtött adatokból.
    if budapesti_most.time() < time(16, 30):
        return {
            "datum": MAI_NAP,
            "kesz": False,
            "excel_kesz": False,
            "keszult": "-",
            "utolso_futas": budapesti_most.strftime("%Y-%m-%d %H:%M:%S"),
            "vizsgalt_fordak": 0,
            "eredmenyek": []
        }

    korabbi_riport = napi_adatok.get(
        "hidegtarolas_riport"
    ) or {}

    # A napi pozíciótörténetet itt is be kell tölteni.
    # Ez a változó a korábbi pozíciólekérési blokkban lokális,
    # ezért ebben a függvényben külön ki kell venni a napi JSON-ból.
    pozicio_tortenet = napi_adatok.get(
        "pozicio_tortenet",
        []
    )

    eredmenyek = []

    for _, forda_sor in figyelt_fordak.iterrows():

        viszonylat = str(
            forda_sor["viszonylat"]
        ).strip()

        forda = str(
            forda_sor["forda"]
        ).strip()

        kulcs = f"{viszonylat}|{forda}"

        forda_adat = forda_rendszamok.get(
            kulcs,
            {}
        )

        rendszam = str(
            forda_adat.get(
                "rendszám",
                ""
            )
        ).strip()

        eredmeny = hidegtarolas_riport_eredmeny(
            forda_sor,
            pozicio_tortenet
        )

        eredmenyek.append({
            "dátum": MAI_NAP,
            "viszonylat": viszonylat,
            "forda": forda,
            "rendszám": rendszam,
            "eredmény": eredmeny
        })

    aktualis_futas_idopont = budapesti_most.strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    # Az "Utolsó futás" az előző riport készítési ideje.
    utolso_futas = korabbi_riport.get(
        "keszult",
        "-"
    )

    # --------------------------------------------------------
    # Excel: egy nap csak egyszer kerüljön bele.
    # --------------------------------------------------------

    excel_mar_mentve = (
        korabbi_riport.get("datum") == MAI_NAP
        and korabbi_riport.get("excel_kesz") is True
    )

    if not excel_mar_mentve:

        os.makedirs(
            "data",
            exist_ok=True
        )

        if os.path.exists(RIport_XLSX):

            export_wb = openpyxl.load_workbook(
                RIport_XLSX
            )

            if "Riport" in export_wb.sheetnames:
                export_ws = export_wb["Riport"]
            else:
                export_ws = export_wb.create_sheet(
                    "Riport"
                )

        else:

            export_wb = openpyxl.Workbook()

            export_ws = export_wb.active
            export_ws.title = "Riport"

            export_ws.append([
                "Dátum",
                "Viszonylat",
                "Forda",
                "Rendszám",
                "Eredmény"
            ])

        if export_ws.max_row == 1 and all(
            export_ws.cell(1, col).value is None
            for col in range(1, 6)
        ):
            export_ws.delete_rows(1)
            export_ws.append([
                "Dátum",
                "Viszonylat",
                "Forda",
                "Rendszám",
                "Eredmény"
            ])

        zold_toltes = openpyxl.styles.PatternFill(
            fill_type="solid",
            fgColor="00B050"
        )

        piros_toltes = openpyxl.styles.PatternFill(
            fill_type="solid",
            fgColor="FF0000"
        )

        fekete_toltes = openpyxl.styles.PatternFill(
            fill_type="solid",
            fgColor="000000"
        )

        feher_betu = openpyxl.styles.Font(
            color="FFFFFF",
            bold=True
        )

        for sor in eredmenyek:

            if not sor["rendszám"] and sor["forda"]:
                export_eredmeny = "???"
            elif sor["eredmény"] == "RENDBEN TÁROLT":
                export_eredmeny = "+++"
            else:
                export_eredmeny = "---"

            export_ws.append([
                sor["dátum"],
                sor["viszonylat"],
                sor["forda"],
                sor["rendszám"],
                export_eredmeny
            ])

            eredmeny_cella = export_ws.cell(
                export_ws.max_row,
                5
            )

            if not sor["rendszám"] and sor["forda"]:
                eredmeny_cella.fill = fekete_toltes
                eredmeny_cella.font = feher_betu
            elif sor["eredmény"] == "RENDBEN TÁROLT":
                eredmeny_cella.fill = zold_toltes
                eredmeny_cella.font = feher_betu
            else:
                eredmeny_cella.fill = piros_toltes
                eredmeny_cella.font = feher_betu

        for oszlop in range(1, 6):
            max_hossz = 0

            for cella in export_ws.iter_cols(
                min_col=oszlop,
                max_col=oszlop
            ):
                for cell in cella:
                    if cell.value is not None:
                        max_hossz = max(
                            max_hossz,
                            len(str(cell.value))
                        )

            export_ws.column_dimensions[
                openpyxl.utils.get_column_letter(oszlop)
            ].width = min(
                max_hossz + 2,
                35
            )

        export_wb.save(
            RIport_XLSX
        )

        # A "Riport készült" időpontja az XLS export befejezési ideje.
        riport_idopont = datetime.now(
            ZoneInfo("Europe/Budapest")
        ).strftime("%Y-%m-%d %H:%M:%S")

    if excel_mar_mentve:
        # Ha a mai XLS már korábban elkészült, annak ideje maradjon.
        riport_idopont = korabbi_riport.get(
            "keszult",
            aktualis_futas_idopont
        )

    riportok = {
        "datum": MAI_NAP,
        "kesz": True,
        "excel_kesz": True,
        "keszult": riport_idopont,
        "utolso_futas": utolso_futas,
        "vizsgalt_fordak": len(eredmenyek),
        "eredmenyek": eredmenyek
    }

    napi_adatok[
        "hidegtarolas_riport"
    ] = riportok

    with open(
        NAPI_ADATOK_FAJL,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            napi_adatok,
            f,
            ensure_ascii=False,
            indent=2
        )

    print()
    print("=== HIDEGTÁROLÁSI RIPORT ===")
    print(
        "Riport készült/frissítve:",
        riport_idopont
    )
    print(
        "Vizsgált fordák:",
        len(eredmenyek),
        "/",
        len(figyelt_fordak)
    )
    print(
        "Excel:",
        RIport_XLSX,
        "(mai nap már mentve)" if excel_mar_mentve else "(mai nap mentve)"
    )

    return riportok


# A riport 16:30 után készül el, de naponta csak egyszer.
hidegtarolas_riport = keszit_hidegtarolas_riport()


# ============================================================
# HTML EXPORT
# napi_adatok.json → index.html
# ============================================================

import json
from html import escape


def html_export():

    # --------------------------------------------------------
    # JSON betöltése
    # --------------------------------------------------------

    try:

        with open(
            "napi_adatok.json",
            "r",
            encoding="utf-8"
        ) as f:

            napi_adatok = json.load(f)

    except FileNotFoundError:

        print(
            "Nincs napi_adatok.json, HTML export nem készül."
        )

        return


    # --------------------------------------------------------
    # Pozíciótörténet
    # --------------------------------------------------------

    pozicio_tortenet = napi_adatok.get(
        "pozicio_tortenet",
        []
    )


    if not pozicio_tortenet:

        print(
            "Nincs pozíciótörténet, HTML export nem készül."
        )

        return


    # --------------------------------------------------------
    # Utolsó lekérdezés
    # --------------------------------------------------------

    lekkerdezesek = [

        rekord.get(
            "frissítve",
            ""
        )

        for rekord in pozicio_tortenet

        if rekord.get("frissítve")

    ]


    if lekkerdezesek:

        utolso_lekkerdezes = max(
            lekkerdezesek
        )

    else:

        utolso_lekkerdezes = "-"


    # --------------------------------------------------------
    # Futás dátuma és utolsó lekérdezés ideje
    # --------------------------------------------------------

    futas_datum = napi_adatok.get(
        "datum",
        "-"
    )


    if futas_datum != "-":

        futas_datum = (
            futas_datum
            .replace("-", ".")
            + "."
        )


    if utolso_lekkerdezes != "-":

        utolso_ido = utolso_lekkerdezes[:5]

    else:

        utolso_ido = "-"


    # --------------------------------------------------------
    # Összesítés a fejléc számára
    # --------------------------------------------------------

    excel_fordak_szama = len(figyelt_fordak)

    megtalalt_jarmuvek = len({
        str(rekord.get("rendszám", "")).strip().upper()
        for rekord in pozicio_tortenet
        if str(rekord.get("rendszám", "")).strip()
    })


    # --------------------------------------------------------
    # MINDEN időpont
    #
    # Fontos: itt NEM vágjuk le 18-ra.
    # Az összes időoszlop bekerül a második táblába.
    # A 18 oszlopos megjelenítést a HTML/CSS/JS kezeli.
    # --------------------------------------------------------

    idopontok = sorted(
        {
            rekord.get(
                "frissítve",
                ""
            )[:5]

            for rekord in pozicio_tortenet

            if rekord.get("frissítve")
        }
    )


    # --------------------------------------------------------
    # Sorok
    # --------------------------------------------------------

    sorok = {}


    for rekord in pozicio_tortenet:

        viszonylat = str(
            rekord.get(
                "viszonylat",
                ""
            )
        )


        forda = str(
            rekord.get(
                "forda",
                ""
            )
        )


        kezdes = str(
            rekord.get(
                "kezdés",
                ""
            )
        )[:5]


        vegzes = str(
            rekord.get(
                "végzés",
                ""
            )
        )[:5]


        hely = str(
            rekord.get(
                "hely",
                ""
            )
        )


        rendszam = str(
            rekord.get(
                "rendszám",
                ""
            )
        )


        kulcs = (
            viszonylat,
            forda
        )


        if kulcs not in sorok:

            sorok[kulcs] = {

                "viszonylat": viszonylat,

                "forda": forda,

                "kezdés": kezdes,

                "végzés": vegzes,

                "hely": hely,

                "rendszám": rendszam,

                "ellenőrzés": {}

            }


        idopont = rekord.get(
            "frissítve",
            ""
        )[:5]


        sorok[kulcs]["ellenőrzés"][idopont] = (

            rekord.get(
                "ellenőrzés",
                "-"
            )

        )


    # --------------------------------------------------------
    # TÉRKÉP ADATOK
    # --------------------------------------------------------

    terkep_jarmuvek = {}


    if utolso_lekkerdezes != "-":

        for rekord in pozicio_tortenet:

            rendszam = str(
                rekord.get("rendszám", "")
            ).strip().upper()


            if not rendszam:
                continue


            kezdés = str(
                rekord.get("kezdés", "")
            ).strip()


            végzés = str(
                rekord.get("végzés", "")
            ).strip()


            if not (
                kezdés
                and végzés
                and kezdés <= utolso_lekkerdezes <= végzés
            ):
                continue


            frissitve = str(
                rekord.get("frissítve", "")
            ).strip()


            pozicio = str(
                rekord.get("pozíció", "")
            ).strip()


            if not pozicio:
                continue


            try:

                latitude_szoveg, longitude_szoveg = (
                    pozicio.split(",", 1)
                )

                latitude = float(
                    latitude_szoveg.strip()
                )

                longitude = float(
                    longitude_szoveg.strip()
                )

            except (ValueError, TypeError):

                continue


            elozo = terkep_jarmuvek.get(
                rendszam
            )


            if (
                elozo is not None
                and str(
                    elozo.get(
                        "frissitve",
                        ""
                    )
                ) >= frissitve
            ):
                continue


            helyszin_kulcs = str(
                rekord.get(
                    "helyszín",
                    ""
                )
            ).strip()


            helyszin = HELYSZINEK.get(
                helyszin_kulcs
            )


            if helyszin is not None:

                benne_van = (

                    helyszin["lat_min"]
                    <= latitude
                    <= helyszin["lat_max"]

                    and

                    helyszin["lon_min"]
                    <= longitude
                    <= helyszin["lon_max"]

                )


                statusz = (
                    "OK"
                    if benne_van
                    else "NEM"
                )


                helyszin_nev = helyszin.get(
                    "kulcsszo",
                    helyszin_kulcs
                )

            else:

                statusz = "-"

                helyszin_nev = (
                    helyszin_kulcs
                    if helyszin_kulcs
                    else "Nincs kijelölt geozóna"
                )


            terkep_jarmuvek[rendszam] = {

                "rendszam": rendszam,

                "viszonylat": str(
                    rekord.get(
                        "viszonylat",
                        ""
                    )
                ),

                "forda": str(
                    rekord.get(
                        "forda",
                        ""
                    )
                ),

                "helyszin": helyszin_nev,

                "statusz": statusz,

                "latitude": latitude,

                "longitude": longitude,

                "frissitve": frissitve

            }


    terkep_jarmuvek_lista = list(
        terkep_jarmuvek.values()
    )


    terkep_zonak = []


    for kulcs, helyszin in HELYSZINEK.items():

        terkep_zonak.append({

            "kulcs": kulcs,

            "nev": helyszin.get(
                "kulcsszo",
                kulcs
            ),

            "lat_min": helyszin["lat_min"],

            "lat_max": helyszin["lat_max"],

            "lon_min": helyszin["lon_min"],

            "lon_max": helyszin["lon_max"]

        })


    # --------------------------------------------------------
    # HTML
    # --------------------------------------------------------

    html = []


    html.append("""
<!DOCTYPE html>

<html lang="hu">

<head>

<meta charset="UTF-8">

<title>ArrivaBus hidegtárolás</title>


<style>

body {

    font-family: Arial, sans-serif;

    margin: 15px;

    background: #f5f5f5;

    color: #222;

}


.fejlec {

    background: white;

    border: 1px solid #cccccc;

    padding: 10px 15px;

    margin-bottom: 12px;

}


.cim {

    font-size: 22px;

    font-weight: bold;

    margin-bottom: 6px;

}


.fejlec-adatok {

    display: flex;

    align-items: center;

    justify-content: space-between;

    width: 100%;

}


.fejlec-bal,
.fejlec-jobb {

    display: flex;

    align-items: center;

    gap: 28px;

    white-space: nowrap;

}


.fejlec-jobb {

    margin-left: auto;

}


.adat {

    font-size: 13px;

    white-space: nowrap;

}


/* =========================================================
   TÁBLÁZATI BLOKK
   6 fix oszlop + időtábla + riport egy sorban
   ========================================================= */

.tabla-egesz {

    display: flex;

    align-items: flex-start;

    width: max-content;

    max-width: 100%;

    background: white;

}


/* Bal oldali, fix 6 oszlop */

.alap-ablak {

    flex: 0 0 auto;

}


/* Jobb oldali időtábla */

.idopont-resz {

    flex: 0 0 auto;

    margin-left: 0;

}


/*
   Pontosan 18 időoszlopnyi látható terület.
   Egy időoszlop 34 px széles.
*/

.idopont-ablak {

    width: 612px;

    max-width: calc(100vw - 30px);

    overflow: hidden;

    background: white;

}


/* Az összes időoszlop széles belső táblázata */

.idopont-belső {

    width: max-content;

}


table {

    border-collapse: collapse;

    background: white;

    font-size: 12px;

}


th,
td {

    border: 1px solid #888;

    padding: 3px 5px;

    text-align: center;

    height: 24px;

    box-sizing: border-box;

}


th {

    background: #d9d9d9;

    font-weight: bold;

    white-space: nowrap;

}


td.alap {

    white-space: nowrap;

}


th.viszonylat,
td.viszonylat,
th.forda,
td.forda,
th.kezdés,
td.kezdés,
th.végzés,
td.végzés {

    text-align: center;

}


th.hely,
td.hely {

    text-align: left;

}


th.rendszam,
td.rendszam {

    text-align: right;

}


td.rendszam {

    font-weight: bold;

}


/* Időoszlopok */

th.idopont,
td.ellenorzes {

    width: 34px;

    min-width: 34px;

    max-width: 34px;

    height: 24px;

    padding: 1px;

}


td.ellenorzes {

    font-weight: bold;

}


/* =========================================================
   KÜLÖN VÍZSZINTES CSÚSZKA
   ========================================================= */

.idopont-csuszkasav {

    width: 612px;

    max-width: calc(100vw - 30px);

    background: white;

    border-left: 1px solid #888;

    border-right: 1px solid #888;

    border-bottom: 1px solid #888;

    box-sizing: border-box;

    padding: 2px 5px 4px 5px;

}


.idopont-csuszkasav input[type="range"] {

    display: block;

    width: 100%;

    margin: 0;

    cursor: pointer;

}


/* Színezett eredmények */

.ok {

    background: #00b050;

    color: white;

}


.nem {

    background: #ff0000;

    color: white;

}


.nincs {

    background: #000000;

    color: white;

}


/* =========================================================
   HIDEGTÁROLÁSI RIPORT
   ========================================================= */

.riport-fejlec-adatok {
    display: flex;
    justify-content: space-between;
    align-items: center;
    width: 100%;
    margin-bottom: 2px;
    font-size: 12px;
    line-height: 1.35;
    white-space: nowrap;
}

.riport-resz {
    flex: 0 0 auto;
    margin-left: 4px;
    align-self: flex-start;
}

.riport-tablazat {
    background: white;
}

.riport-tablazat th,
.riport-tablazat td {
    min-width: 145px;
    height: 24px;
    box-sizing: border-box;
}

.riport-tablazat th {
    text-align: center;
}

.riport-ok {
    background: #00b050;
    color: white;
    font-weight: bold;
}

.riport-eltérés {
    background: #ff0000;
    color: white;
    font-weight: bold;
}

/* =========================================================
   TÉRKÉP
   A teljes táblázati blokk alatt, külön sorban.
   ========================================================= */

#geozona-terkep {

    width: 100%;

    height: 50vh;

    max-height: 50vh;

    min-height: 320px;

    margin-top: 0;

    border: 1px solid #cccccc;

    background: white;

}


.vehicle-pin {

    width: 22px;

    height: 22px;

    border-radius: 50% 50% 50% 0;

    transform: rotate(-45deg);

    border: 2px solid white;

    box-shadow: 0 1px 5px rgba(0,0,0,0.45);

    box-sizing: border-box;

}


.vehicle-pin::after {

    content: "";

    display: block;

    width: 7px;

    height: 7px;

    margin: 5px auto 0;

    border-radius: 50%;

    background: white;

}


.vehicle-pin.green {

    background: #00b050;

}


.vehicle-pin.red {

    background: #ff0000;

}


.vehicle-pin.gray {

    background: #777777;

}


.leaflet-popup-content {

    line-height: 1.45;

}

</style>


<link
    rel="stylesheet"
    href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
    crossorigin=""
>

</head>


<body>


<div class="fejlec">

<div class="cim">

ArrivaBus hidegtárolás

</div>


<div class="fejlec-adatok riport-fejlec-adatok">

    <div class="fejlec-bal">
        <div class="adat">
            <b>Dátum:</b> """ + escape(futas_datum) + """
        </div>
        <div class="adat">
            <b>Naptípus:</b> """ + escape(str(talalt_munkalap)) + """
        </div>
        <div class="adat">
            <b>Utolsó lekérdezés:</b> """ + escape(utolso_ido) + """
        </div>
        <div class="adat">
            <b>Járművek száma:</b> """ + str(megtalalt_jarmuvek) + "/" + str(excel_fordak_szama) + """
        </div>
    </div>

    <div class="fejlec-jobb">
        <div class="adat">
            <b>Riport készült:</b> """ + escape(str(hidegtarolas_riport.get("keszult", "-"))) + """
        </div>
        <div class="adat">
            <b>Vizsgált fordák:</b> """ + str(hidegtarolas_riport.get("vizsgalt_fordak", 0)) + """
        </div>
        <div class="adat">
            <b>Utolsó futás:</b> """ + escape(str(hidegtarolas_riport.get("utolso_futas", "-"))) + """
        </div>
    </div>

</div>


<!-- =========================================================
     TÉRKÉP – KÖZVETLENÜL A FEJLÉC ALATT
     ========================================================= -->

<div id="geozona-terkep"></div>


<!-- =========================================================
     BAL: 6 FIX OSZLOP
     JOBB: ÖSSZES IDŐOSZLOP, 18 LÁTHATÓ
     ========================================================= -->

<div class="tabla-egesz">


<!-- =========================================================
     BAL OLDALI TÁBLÁZAT
     ========================================================= -->

<div class="alap-ablak">

<table>

<thead>

<tr>

<th class="viszonylat">Viszonylat</th>

<th class="forda">Forda</th>

<th class="kezdés">Kezdés</th>

<th class="végzés">Végzés</th>

<th class="hely">Hely</th>

<th class="rendszam">Rendszám</th>

</tr>

</thead>


<tbody>

""")

    # --------------------------------------------------------
    # Bal oldali sorok
    # --------------------------------------------------------

    rendezett_sorok = sorted(
        sorok.items(),
        key=lambda x: (
            x[1].get("kezdés", ""),
            x[1].get("viszonylat", ""),
            x[1].get("forda", "")
        )
    )


    for _, sor in rendezett_sorok:

        html.append("<tr>")

        html.append(
            f'<td class="alap viszonylat">'
            f'{escape(sor["viszonylat"])}'
            f'</td>'
        )

        html.append(
            f'<td class="alap forda">'
            f'{escape(sor["forda"])}'
            f'</td>'
        )

        html.append(
            f'<td class="alap kezdés">'
            f'{escape(sor["kezdés"])}'
            f'</td>'
        )

        html.append(
            f'<td class="alap végzés">'
            f'{escape(sor["végzés"])}'
            f'</td>'
        )

        html.append(
            f'<td class="alap hely">'
            f'{escape(sor["hely"])}'
            f'</td>'
        )

        html.append(
            f'<td class="alap rendszam">'
            f'{escape(sor["rendszám"])}'
            f'</td>'
        )

        html.append("</tr>")


    html.append("""
</tbody>

</table>

</div>


<!-- =========================================================
     JOBB OLDALI IDŐTÁBLA
     ========================================================= -->

<div class="idopont-resz">

<div
    class="idopont-ablak"
    id="idopont-ablak"
>

<div
    class="idopont-belső"
    id="idopont-belső"
>

<table>

<thead>

<tr>

""")

    # --------------------------------------------------------
    # MINDEN időoszlop
    # --------------------------------------------------------

    for idopont in idopontok:

        html.append(
            f'<th class="idopont">'
            f'{escape(idopont)}'
            f'</th>'
        )


    html.append("""
</tr>

</thead>


<tbody>

""")


    # --------------------------------------------------------
    # Időeredmények
    # --------------------------------------------------------

    for _, sor in rendezett_sorok:

        html.append("<tr>")

        for idopont in idopontok:

            eredmeny = sor["ellenőrzés"].get(
                idopont,
                "-"
            )


            if eredmeny == "OK":

                osztaly = "ok"


            elif eredmeny == "NEM":

                osztaly = "nem"


            else:

                osztaly = "nincs"

                eredmeny = "-"


            html.append(
                f'<td class="ellenorzes {osztaly}">'
                f'{escape(eredmeny)}'
                f'</td>'
            )


        html.append("</tr>")


    html.append("""
</tbody>

</table>

</div>

</div>


<!-- =========================================================
     KÜLÖN CSÚSZKA
     ========================================================= -->

<div class="idopont-csuszkasav">

<input
    type="range"
    id="idopont-csuszka"
    min="0"
    max="0"
    value="0"
    step="1"
>

</div>

</div>

""")

    # --------------------------------------------------------
    # HIDEGTÁROLÁSI RIPORT OSZLOP
    # --------------------------------------------------------

    if hidegtarolas_riport:

        riport_eredmenyek = {
            (
                str(sor.get("viszonylat", "")).strip(),
                str(sor.get("forda", "")).strip()
            ): sor.get("eredmény", "ELTÉRÉS TÖRTÉNT")
            for sor in hidegtarolas_riport.get(
                "eredmenyek",
                []
            )
        }

        html.append("""
<div class="riport-resz">

<table class="riport-tablazat">
<thead>
<tr>
    <th>Eredmény</th>
</tr>
</thead>
<tbody>
""")

        for _, sor in rendezett_sorok:

            kulcs = (
                str(sor["viszonylat"]).strip(),
                str(sor["forda"]).strip()
            )

            eredmeny = riport_eredmenyek.get(
                kulcs,
                "ELTÉRÉS TÖRTÉNT"
            )

            osztaly = (
                "riport-ok"
                if eredmeny == "RENDBEN TÁROLT"
                else "riport-eltérés"
            )

            html.append(
                f'<tr><td class="{osztaly}">'
                f'{escape(eredmeny)}'
                f'</td></tr>'
            )

        html.append("""
</tbody>
</table>

</div>

</div>

</div>


<script>

/*
   Az időtábla NEM használ böngészős vízszintes görgetősávot.

   A második táblázatban minden időoszlop benne van,
   de egyszerre csak 18 oszlopnyi terület látszik.

   A külön csúszka mozgatja az időtáblát.
*/

const idopontAblak =
    document.getElementById("idopont-ablak");

const idopontBelso =
    document.getElementById("idopont-belső");

const idopontCsuszka =
    document.getElementById("idopont-csuszka");


function frissitIdopontCsuszkat() {

    if (
        !idopontAblak
        || !idopontBelso
        || !idopontCsuszka
    ) {

        return;

    }


    const maxScroll =
        Math.max(
            0,
            idopontBelso.scrollWidth
            - idopontAblak.clientWidth
        );


    /*
       A csúszka értéke 0–1000 között mozog.
       Így független az időoszlopok számától.
    */

    idopontCsuszka.min = "0";

    idopontCsuszka.max = "1000";

    idopontCsuszka.value = "1000";


    idopontCsuszka.oninput = function() {

        const arany =
            Number(this.value) / 1000;

        idopontAblak.scrollLeft =
            maxScroll * arany;

    };


    /* Induláskor mindig a legutolsó 18 oszlop látszódjon. */

    idopontAblak.scrollLeft = maxScroll;

}


window.addEventListener(
    "load",
    frissitIdopontCsuszkat
);


window.addEventListener(
    "resize",
    frissitIdopontCsuszkat
);

</script>


<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>

<script>

const terkepJarmuvek = """ + json.dumps(terkep_jarmuvek_lista, ensure_ascii=False) + r""";

const terkepZonak = """ + json.dumps(terkep_zonak, ensure_ascii=False) + r""";


const map = L.map(
    "geozona-terkep"
).setView(
    [47.4979, 19.0402],
    11
);


L.tileLayer(
    "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    {
        maxZoom: 19,
        attribution: "&copy; OpenStreetMap"
    }
).addTo(map);


const terkepElemek = [];


function escapeHtml(value) {

    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");

}


function jarmuIkon(statusz) {

    let osztaly = "gray";

    if (statusz === "OK") {
        osztaly = "green";
    }
    else if (statusz === "NEM") {
        osztaly = "red";
    }

    return L.divIcon({

        className: "",

        html:
            '<div class="vehicle-pin '
            + osztaly
            + '"></div>',

        iconSize: [22, 30],

        iconAnchor: [11, 30],

        popupAnchor: [0, -28]

    });

}


// ---------------------------------------------------------
// GEOZÓNÁK
// ---------------------------------------------------------

terkepZonak.forEach(function(zona) {

    const rectangle = L.rectangle(

        [
            [zona.lat_min, zona.lon_min],
            [zona.lat_max, zona.lon_max]
        ],

        {
            color: "#3388ff",
            weight: 2,
            fillOpacity: 0.12
        }

    ).addTo(map);


    rectangle.bindPopup(
        "<b>Geozóna</b><br>"
        + escapeHtml(zona.nev)
    );


    terkepElemek.push(rectangle);

});


// ---------------------------------------------------------
// JÁRMŰVEK
// ---------------------------------------------------------

terkepJarmuvek.forEach(function(jarmu) {

    const marker = L.marker(

        [
            jarmu.latitude,
            jarmu.longitude
        ],

        {
            icon: jarmuIkon(
                jarmu.statusz
            )
        }

    ).addTo(map);


    let statuszSzoveg = "Nincs értékelés";

    if (jarmu.statusz === "OK") {
        statuszSzoveg =
            '<span style="color:#00a040;font-weight:bold;">OK</span>';
    }
    else if (jarmu.statusz === "NEM") {
        statuszSzoveg =
            '<span style="color:#e00000;font-weight:bold;">ELTÉRÉS</span>';
    }


    marker.bindPopup(

        "<b>"
        + escapeHtml(jarmu.rendszam)
        + "</b><br><br>"

        + "<b>Viszonylat:</b> "
        + escapeHtml(jarmu.viszonylat)
        + "<br>"

        + "<b>Forda:</b> "
        + escapeHtml(jarmu.forda)
        + "<br>"

        + "<b>Geozóna:</b> "
        + escapeHtml(jarmu.helyszin)
        + "<br>"

        + "<b>Állapot:</b> "
        + statuszSzoveg
        + "<br>"

        + "<b>Utolsó ismert pozíció:</b> "
        + escapeHtml(jarmu.frissitve)
        + "<br>"

        + "<b>GPS:</b> "
        + escapeHtml(
            jarmu.latitude.toFixed(6)
            + ", "
            + jarmu.longitude.toFixed(6)
        )

    );


    terkepElemek.push(marker);

});


// ---------------------------------------------------------
// TÉRKÉP NÉZET BEÁLLÍTÁSA
// ---------------------------------------------------------

if (terkepElemek.length > 0) {

    const bounds = L.featureGroup(
        terkepElemek
    ).getBounds();

    if (bounds.isValid()) {

        map.fitBounds(
            bounds.pad(0.08)
        );

    }

}

</script>

</body>

</html>

""")



    # --------------------------------------------------------
    # Mentés
    # --------------------------------------------------------

    with open(
        "index.html",
        "w",
        encoding="utf-8"
    ) as f:

        f.write(
            "".join(html)
        )


    print()

    print(
        "HTML export elkészült:"
    )

    print(
        "index.html"
    )



# ============================================================
# EXPORT FUTTATÁSA
# ============================================================

html_export()
