# -*- coding: utf-8 -*-

# Adatok forrása: BKK Zrt., CC BY 4.0

# =========================================================
# BKK FORDA → RENDSZÁM → POZÍCIÓ
# VehiclePositions forrás: TXT (GTFS-RT text formátum)
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

# -*- coding: utf-8 -*-

# Adatok forrása: BKK Zrt., CC BY 4.0

# =========================================================
# BKK FORDA → RENDSZÁM → POZÍCIÓ
# VehiclePositions forrás: TXT (GTFS-RT text formátum)
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
import re
import pandas as pd
import zipfile
import io

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from google.transit import gtfs_realtime_pb2
from google.protobuf import text_format


def torol_nem_regisztralt_bkk_extensionok(szoveg):
    """
    A BKK VehiclePositions.txt tartalmazhat olyan egyedi protobuf
    extension mezőket (pl. [realcity.vehicle]), amelyeket a standard
    gtfs_realtime_pb2 modul nem regisztrál. Ezeket a downstream
    feldolgozás nem használja, ezért csak a text-format parse előtt
    eltávolítjuk őket.
    """

    extension = "[realcity.vehicle]"

    while True:

        kezdet = szoveg.find(extension)

        if kezdet == -1:
            break

        kapocs = szoveg.find("{", kezdet)

        if kapocs == -1:
            szoveg = szoveg[:kezdet] + szoveg[kezdet + len(extension):]
            continue

        melyseg = 0
        vege = None

        for i in range(kapocs, len(szoveg)):

            if szoveg[i] == "{":
                melyseg += 1

            elif szoveg[i] == "}":
                melyseg -= 1

                if melyseg == 0:
                    vege = i + 1
                    break

        if vege is None:
            # Hibás/csonka extension esetén a maradékot is eldobjuk.
            szoveg = szoveg[:kezdet]
            break

        szoveg = szoveg[:kezdet] + szoveg[vege:]

    return szoveg

# =========================================================
# TESZTIDŐ
# =========================================================
# True esetén a program aktuális ideje a megadott óraszámmal
# eltolva kerül felhasználásra.
# A BKK-ból érkező valódi GPS timestamp-eket NEM módosítjuk.

TESZT_MOD = False
TESZT_IDO_ELTOLAS_ORA = -2


def budapesti_most():
    """A program által használt aktuális budapesti idő."""
    valos_ido = datetime.now(ZoneInfo("Europe/Budapest"))

    if TESZT_MOD:
        return valos_ido + timedelta(hours=TESZT_IDO_ELTOLAS_ORA)

    return valos_ido


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

budapesti_datum = budapesti_most().strftime("%Y-%m-%d")


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

mai_datum = budapesti_most().strftime("%Y%m%d")


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
        "lat_min": 47.430462715266955,
        "lat_max": 47.431423515348,
        "lon_min": 19.07051806889125,
        "lon_max": 19.07169262649567
    },

    "andor": {
        "kulcsszo": "ArrivaBus Andor telephely",
        "lat_min": 47.45703696628262,
        "lat_max": 47.45974359947361,
        "lon_min": 19.025296690497736,
        "lon_max": 19.02988619533237
    },

    "bogancs": {
        "kulcsszo": "ArrivaBus Bogáncs telephely",
        "lat_min": 47.569747494207284,
        "lat_max": 47.5731577937613,
        "lon_min": 19.131368356259316,
        "lon_max": 19.137645363043006
    },

    "csepel": {
        "kulcsszo": "ArrivaBus Szállító telephely",
        "lat_min": 47.441927955392465,
        "lat_max": 47.4437481894374,
        "lon_min": 19.081122238879782,
        "lon_max": 19.084841859297306
    },

    "kobanya_also": {
        "kulcsszo": "Kőbánya alsó",
        "lat_min": 47.48261593267198,
        "lat_max": 47.48462411413879,
        "lon_min": 19.12645422616769,
        "lon_max": 19.128730058590182
    },   

    "kobanya_kispest": {
        "kulcsszo": "Kőbánya-Kispest",
        "lat_min": 47.461787898640296,
        "lat_max": 47.462689191826485,
        "lon_min": 19.15019439393539,
        "lon_max": 19.151124752353716
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

    ellenőrzési_kezdés = kezdés_dt - timedelta(minutes=15)
    ellenőrzési_végzés = végzés_dt + timedelta(minutes=15)

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

most = budapesti_most()

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

# SZ-VV munkalapon nincs aznapi feldolgozás.
if str(talalt_munkalap).strip().upper() == "SZ-VV":
    print("Az aktuális munkalap SZ-VV, a program leáll.")
    raise SystemExit(0)


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

        "helyszín": helyszin,

        "forrás": "biztor"

    })


# =========================================================
# 9/l. MÁSODIK EXCEL FORRÁS – GARÁZSMENET / JBK
# =========================================================

GARAZS_EXCEL_FAJL = f"data/garazs_{ev}-{honap}.xlsx"

if not os.path.exists(GARAZS_EXCEL_FAJL):
    raise FileNotFoundError(f"Nem található a második Excel fájl:\n{GARAZS_EXCEL_FAJL}")

wb_garazs = openpyxl.load_workbook(GARAZS_EXCEL_FAJL, read_only=True, data_only=True)
garazs_talalt_munkalap = None

for nev in wb_garazs.sheetnames:
    ws = wb_garazs[nev]
    c1 = "" if ws["C1"].value is None else str(ws["C1"].value).strip()
    d1 = "" if ws["D1"].value is None else str(ws["D1"].value).strip()
    if ev_honap not in c1:
        continue
    napok = [x.strip() for x in d1.replace(",", " ").split()]
    if nap_keresett in napok:
        garazs_talalt_munkalap = nev
        break

if garazs_talalt_munkalap is None:
    raise ValueError(f"Nem található a második Excelben az aktuális naphoz tartozó munkalap.\nKeresett C1: {ev_honap}\nKeresett D1 nap: {nap_keresett}")

print("Második Excel munkalap:", garazs_talalt_munkalap)

excel_garazs = pd.read_excel(GARAZS_EXCEL_FAJL, sheet_name=garazs_talalt_munkalap, header=None)
figyelt_fordak_garazs = []

for i in range(5, len(excel_garazs)):
    a_ertek = excel_garazs.iloc[i, 0]
    if pd.isna(a_ertek) or not str(a_ertek).strip():
        break

    viszonylat = excel_garazs.iloc[i, 0]
    forda = excel_garazs.iloc[i, 4]
    kezdes = excel_garazs.iloc[i, 9]
    vegzes = excel_garazs.iloc[i, 10]
    hely = excel_garazs.iloc[i, 12]

    if pd.isna(viszonylat) or pd.isna(forda):
        continue

    viszonylat = str(viszonylat).strip()
    forda = str(forda).strip()
    if viszonylat.endswith(".0"): viszonylat = viszonylat[:-2]
    if forda.endswith(".0"): forda = forda[:-2]

    kezdes = ido_konvertalasa(kezdes)
    vegzes = ido_konvertalasa(vegzes)
    hely = str(hely).strip() if pd.notna(hely) else ""

    helyszin_talalatok = []
    for helyszin_kulcs, adat in HELYSZINEK.items():
        if hely.casefold().startswith(adat["kulcsszo"].casefold()):
            helyszin_talalatok.append(helyszin_kulcs)

    if len(helyszin_talalatok) > 1:
        raise ValueError(f"Több helyszín illeszkedik ehhez: {hely}\nTalálatok: {helyszin_talalatok}")

    figyelt_fordak_garazs.append({
        "viszonylat": viszonylat,
        "forda": forda,
        "kezdés": kezdes,
        "végzés": vegzes,
        "hely": hely,
        "helyszín": helyszin_talalatok[0] if helyszin_talalatok else "",
        "forrás": "garazs"
    })

figyelt_fordak_garazs = pd.DataFrame(figyelt_fordak_garazs)
figyelt_fordak_biztor = pd.DataFrame(figyelt_fordak)
figyelt_fordak = pd.concat([figyelt_fordak_biztor, figyelt_fordak_garazs], ignore_index=True)

def forda_kulcs_adat(forda_sor):
    viszonylat = str(forda_sor.get("viszonylat", "")).strip()
    forda = str(forda_sor.get("forda", "")).strip()
    forrás = str(forda_sor.get("forrás", "biztor")).strip() or "biztor"
    return f"garazs|{viszonylat}|{forda}" if forrás == "garazs" else f"{viszonylat}|{forda}"

def forda_kulcs_rekord(rekord):
    forrás = str(rekord.get("forrás", "biztor")).strip() or "biztor"
    viszonylat = str(rekord.get("viszonylat", "")).strip()
    forda = str(rekord.get("forda", "")).strip()
    return f"garazs|{viszonylat}|{forda}" if forrás == "garazs" else f"{viszonylat}|{forda}"

# =========================================================
# 9/m. ELLENŐRZÉS
# =========================================================

figyelt_fordak = figyelt_fordak.reset_index(drop=True)


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
# =========================================================
# 10. FORDA → RENDSZÁM + JÁRMŰ ID
# 07:00–13:30 AZONOSÍTÁSI FÁZIS
# =========================================================

import json

# =========================================================
# 10/a. AKTUÁLIS FÁZIS
# =========================================================

fazis_ideje = budapesti_most().time()

azonositas_idoszak = (
    time(7, 0)
    <= fazis_ideje
    <= time(13, 30)
)

pozicio_idoszak = (
    time(8, 0)
    < fazis_ideje
    <= time(17, 0)
)

print()
print(
    "Budapesti aktuális idő:",
    fazis_ideje.strftime("%H:%M:%S")
)

if azonositas_idoszak:
    print(
        "Aktív fázis: 07:00–13:30 "
        "forda → rendszám + jármű ID"
    )
elif pozicio_idoszak:
    print(
        "Aktív fázis: 08:00–17:00 "
        "jármű ID → FUTÁR pozíció"
    )
else:
    print(
        "Jelenleg nincs aktív adatgyűjtési fázis."
    )


# =========================================================
# 10/b. NAPI ADATFÁJL
# =========================================================

NAPI_ADATOK_FAJL = "napi_adatok.json"

MAI_NAP = budapesti_most().strftime("%Y-%m-%d")


# =========================================================
# 10/c. KORÁBBI NAPI ADATOK BETÖLTÉSE
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


if napi_adatok.get("datum") != MAI_NAP:
    napi_adatok = {
        "datum": MAI_NAP,
        "forda_rendszamok": {},
        "pozicio_tortenet": []
    }


# =========================================================
# 10/d. FORDA → RENDSZÁM + JÁRMŰ ID ADATOK
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
    "Korábban mentett forda → rendszám + ID kapcsolatok:",
    len(forda_rendszamok)
)


# =========================================================
# 10/e. GTFS-RT AZONOSÍTÁSI ADAT LEKÉRÉSE
#
# Fontos:
# A GTFS-RT itt NEM pozícióforrásként szolgál.
# Csak az aktív trip alapján azonosítjuk a járművet,
# és elmentjük a rendszám + jármű ID párost.
# =========================================================

url = (
    "https://go.bkk.hu/api/query/v1/ws/"
    "gtfs-rt/full/VehiclePositions.txt"
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


feed = gtfs_realtime_pb2.FeedMessage()

text_format.Parse(
    torol_nem_regisztralt_bkk_extensionok(response.text),
    feed
)

print(
    "GTFS-RT entitások száma:",
    len(feed.entity)
)


# =========================================================
# 10/f. GTFS-RT JÁRMŰVEK
# =========================================================

jarmuvek = []

for entity in feed.entity:

    if not entity.HasField("vehicle"):
        continue

    v = entity.vehicle

    rendszam = str(
        v.vehicle.license_plate
    ).strip().upper()

    jarmu_id = str(
        v.vehicle.id
    ).strip()

    trip_id = str(
        v.trip.trip_id
    ).strip()

    if not jarmu_id or not trip_id:
        continue

    jarmuvek.append({
        "rendszám": rendszam,
        "jármű_id": jarmu_id,
        "trip_id": trip_id,
        "route_id": v.trip.route_id,
        "direction_id": v.trip.direction_id
    })


jarmuvek = pd.DataFrame(jarmuvek)

print(
    "GTFS-RT trip + jármű ID kapcsolatok:",
    len(jarmuvek)
)


# =========================================================
# 10/g. AKTUÁLIS IDŐ
# =========================================================

idopont = budapesti_most().strftime("%H:%M:%S")

print()
print(
    "GTFS-RT azonosítás időpontja:",
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

    forda_kulcs = forda_kulcs_adat(forda_sor)


    # -----------------------------------------------------
    # GTFS-RT azonosítás csak a táblázatos kezdési időig
    #
    # Ha a forda kezdési ideje már eltelt, az adott fordát
    # nem azonosítjuk tovább GTFS-RT alapján. A korábban
    # elmentett rendszám + jármű ID változatlan marad, és
    # innentől kizárólag a FUTÁR pozícióforrást használjuk.
    # -----------------------------------------------------

    forda_kezdese = forda_sor["kezdés"]

    if pd.isna(forda_kezdese):
        continue

    if fazis_ideje >= forda_kezdese:

        elozo = forda_rendszamok.get(
            forda_kulcs,
            {}
        )

        if elozo:
            print(
                f"{forda_kulcs}: kezdési idő ({forda_kezdese.strftime('%H:%M:%S')}) "
                f"már eltelt → GTFS-RT azonosítás lezárva, "
                f"mentett jármű marad: "
                f"{elozo.get('rendszám', '')} / "
                f"BKK_{elozo.get('jármű_id', '')}"
            )
        else:
            print(
                f"{forda_kulcs}: kezdési idő ({forda_kezdese.strftime('%H:%M:%S')}) "
                f"már eltelt, de nincs korábban mentett GTFS-RT azonosítás."
            )

        continue


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
        forda_trips["trip_id"].astype(str)
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
        .groupby("trip_id", sort=False)
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
    # Aktív trip → GTFS-RT jármű
    # -----------------------------------------------------

    keresett_trip_ids = set(
        aktiv_trip["trip_id"].astype(str)
    )

    rt_talalatok = jarmuvek[
        jarmuvek["trip_id"].astype(str)
        .isin(keresett_trip_ids)
    ].copy()

    if len(rt_talalatok) == 0:
        print(
            f"{forda_kulcs}: nincs GTFS-RT találat, "
            f"korábbi rendszám + ID megmarad."
        )
        continue


    # -----------------------------------------------------
    # SIKERES TALÁLAT
    #
    # A GTFS-RT adja a rendszámot ÉS a jármű ID-t.
    # Csak érvényes páros esetén írjuk felül a mentett adatot.
    # -----------------------------------------------------

    for _, rt in rt_talalatok.iterrows():

        rendszam = str(
            rt["rendszám"]
        ).strip().upper()

        jarmu_id = str(
            rt["jármű_id"]
        ).strip()

        if not rendszam or not jarmu_id:
            continue

        elozo = forda_rendszamok.get(
            forda_kulcs,
            {}
        )

        if (
            str(elozo.get("rendszám", "")).strip().upper()
            == rendszam
            and
            str(elozo.get("jármű_id", "")).strip()
            == jarmu_id
        ):
            print(
                f"{forda_kulcs}: változatlan azonosítás → "
                f"{rendszam} / BKK_{jarmu_id}"
            )
        else:
            print(
                f"{forda_kulcs}: új azonosítás → "
                f"{rendszam} / BKK_{jarmu_id}"
            )

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
            "hely": str(forda_sor["hely"]),
            "helyszín": str(forda_sor["helyszín"]),
            "rendszám": rendszam,
            "jármű_id": jarmu_id,
            "frissítve": idopont
        }

        sikeres_frissitesek += 1
        break


# =========================================================
# 10/j. NAPI ADATOK MENTÉSE
# =========================================================

napi_adatok["datum"] = MAI_NAP
napi_adatok["forda_rendszamok"] = forda_rendszamok

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
    "forda → rendszám + jármű ID találatok:",
    sikeres_frissitesek
)
print(
    "Összes mentett "
    "forda → rendszám + jármű ID kapcsolat:",
    len(forda_rendszamok)
)

if len(forda_rendszamok) > 0:

    rt_fordak = pd.DataFrame(
        list(forda_rendszamok.values())
    )

    oszlopok = [
        "viszonylat",
        "forda",
        "kezdés",
        "végzés",
        "hely",
        "helyszín",
        "rendszám",
        "jármű_id",
        "frissítve"
    ]

    rt_fordak = rt_fordak[
        [x for x in oszlopok if x in rt_fordak.columns]
    ]

    rt_fordak = rt_fordak.sort_values(
        by=["viszonylat", "forda"]
    ).reset_index(drop=True)

    print()
    print(
        "Mentett forda → rendszám + jármű ID kapcsolatok:"
    )
    print(
        rt_fordak.to_string(index=False)
    )

else:
    rt_fordak = pd.DataFrame()
    print()
    print(
        "Még nincs sikeresen azonosított "
        "forda → rendszám + jármű ID kapcsolat."
    )
# ============================================================
# 08:00–17:00
# JÁRMŰ ID → FUTÁR AKTUÁLIS POZÍCIÓ
#
# Azonosítás: GTFS-RT
# Pozíció: FUTÁR vehicles-for-location
# Megjelenített adat: rendszám
# ============================================================

from datetime import datetime
from zoneinfo import ZoneInfo
import requests


print("\n=== FUTÁR pozíciólekérés ===")

most = budapesti_most()
idopont = most.strftime("%H:%M:%S")

print(
    "Pozíciólekérdezés időpontja:",
    idopont
)


# ============================================================
# 1. POZÍCIÓTÖRTÉNET BETÖLTÉSE
# ============================================================

pozicio_tortenet = napi_adatok.get(
    "pozicio_tortenet",
    []
)

uj_poziciok = 0


# ============================================================
# 2. FUTÁR vehicles-for-location LEKÉRÉSE
#
# Egyetlen lekérésből megkapjuk a körzetben lévő járműveket.
# A routeId / tripId hiánya nem probléma: nekünk a
# vehicleId + location kell.
# ============================================================

FUTAR_URL = (
    "https://go.bkk.hu/api/query/v1/ws/otp/api/where/"
    "vehicles-for-location.json"
)

FUTAR_LAT = 47.4979
FUTAR_LON = 19.0402
FUTAR_RADIUS = 25000

futar_jarmuvek = {}
futar_sikeres = False

if pozicio_idoszak:

    for probalkozas in range(1, 4):

        print(
            f"FUTÁR vehicles-for-location lekérés "
            f"({probalkozas}/3)..."
        )

        try:
            response = requests.get(
                FUTAR_URL,
                params={
                    "key": API_KEY,
                    "lat": FUTAR_LAT,
                    "lon": FUTAR_LON,
                    "radius": FUTAR_RADIUS
                },
                timeout=30
            )

            print(
                "HTTP státusz:",
                response.status_code
            )

            if response.status_code != 200:
                raise Exception(
                    f"HTTP hiba: {response.status_code}"
                )

            adat = response.json()

            lista = (
                adat.get("data", {})
                .get("list", [])
            )

            for jarmu in lista:

                vehicle_id = str(
                    jarmu.get("vehicleId", "")
                ).strip()

                if not vehicle_id:
                    continue

                futar_jarmuvek[vehicle_id] = jarmu

            futar_sikeres = True

            print(
                "FUTÁR járművek száma:",
                len(futar_jarmuvek)
            )

            break

        except Exception as e:

            print(
                "FUTÁR lekérési hiba:",
                e
            )

else:
    print(
        "A pozíciólekérési időszak jelenleg nem aktív."
    )


# ============================================================
# 3. SEGÉDFÜGGVÉNY: FUTÁR FRISSÍTÉSI IDŐ
# ============================================================

def futar_idopont(last_update):

    if last_update in (None, "", 0):
        return None

    try:
        ertek = int(float(last_update))

        # Másodperc vagy milliszekundum kezelése.
        if ertek > 100_000_000_000:
            ertek //= 1000

        return datetime.fromtimestamp(
            ertek,
            tz=ZoneInfo("Europe/Budapest")
        ).strftime("%H:%M")

    except (
        ValueError,
        TypeError,
        OverflowError,
        OSError
    ):
        return None


# ============================================================
# 4. MENTETT FORDÁK POZÍCIÓJÁNAK FRISSÍTÉSE
# ============================================================

if pozicio_idoszak:

    for forda_kulcs, adat in forda_rendszamok.items():

        rendszam = str(
            adat.get("rendszám", "")
        ).strip().upper()

        jarmu_id = str(
            adat.get("jármű_id", "")
        ).strip()

        if not rendszam or not jarmu_id:
            print(
                f"{forda_kulcs}: nincs mentett rendszám + jármű ID, "
                f"pozíció nem kérhető."
            )
            continue

        # A GTFS-RT-ben kapott ID-t a FUTÁR BKK_<id> formában használja.
        futar_id = jarmu_id
        if not futar_id.upper().startswith("BKK_"):
            futar_id = f"BKK_{futar_id}"

        jarmu = futar_jarmuvek.get(
            futar_id
        )

        pozicio = None
        pozicio_frissitve = None

        # ----------------------------------------------------
        # Aktuális FUTÁR pozíció
        # ----------------------------------------------------

        if jarmu is not None:

            location = jarmu.get(
                "location"
            ) or {}

            try:
                latitude = float(
                    location.get("lat")
                )
                longitude = float(
                    location.get("lon")
                )

                pozicio = (
                    f"{latitude}, {longitude}"
                )

                pozicio_frissitve = futar_idopont(
                    jarmu.get("lastUpdateTime")
                )

                if not pozicio_frissitve:
                    pozicio_frissitve = idopont[:5]

                futar_rendszam = str(
                    jarmu.get("licensePlate", "")
                ).strip().upper()

                if (
                    futar_rendszam
                    and futar_rendszam != rendszam
                ):
                    print(
                        f"FIGYELEM {forda_kulcs}: mentett rendszám "
                        f"{rendszam}, FUTÁR rendszám {futar_rendszam}"
                    )

                print(
                    f"{forda_kulcs}: {rendszam} / {futar_id} → "
                    f"{pozicio}"
                )

            except (
                ValueError,
                TypeError
            ):
                pozicio = None


        # ----------------------------------------------------
        # Nincs aktuális FUTÁR találat → utolsó ismert pozíció
        # ----------------------------------------------------

        if pozicio is None:

            elozo_pozicio = None
            elozo_pozicio_frissitve = None

            # Elsődlegesen jármű ID alapján keresünk.
            for elozo in reversed(pozicio_tortenet):

                elozo_id = str(
                    elozo.get("jármű_id", "")
                ).strip()

                if elozo_id and elozo_id == jarmu_id:
                    elozo_pozicio = elozo.get(
                        "pozíció"
                    )
                    elozo_pozicio_frissitve = elozo.get(
                        "pozicio_frissitve"
                    )
                    break

            # Régi, jármű ID nélküli rekordokhoz rendszám alapján
            # visszafelé keresünk kompatibilitás miatt.
            if elozo_pozicio is None:

                for elozo in reversed(pozicio_tortenet):

                    elozo_rendszam = str(
                        elozo.get("rendszám", "")
                    ).strip().upper()

                    if elozo_rendszam == rendszam:
                        elozo_pozicio = elozo.get(
                            "pozíció"
                        )
                        elozo_pozicio_frissitve = elozo.get(
                            "pozicio_frissitve"
                        )
                        break

            if elozo_pozicio is None:

                print(
                    f"{forda_kulcs}: {rendszam} / {futar_id} – "
                    f"nincs FUTÁR találat, korábbi pozíció sincs"
                )

                continue

            pozicio = elozo_pozicio
            pozicio_frissitve = elozo_pozicio_frissitve

            print(
                f"{forda_kulcs}: {rendszam} / {futar_id} – "
                f"nincs aktuális FUTÁR adat, utolsó ismert pozíció: "
                f"{pozicio}"
            )


        # ----------------------------------------------------
        # POZÍCIÓ ELLENŐRZÉSE
        # ----------------------------------------------------

        ellenorzes = "-"

        if forda_aktiv_e(
            adat["kezdés"],
            adat["végzés"],
            idopont
        ):

            helyszin_kulcs = str(
                adat.get("helyszín", "")
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

                    ellenorzes = (
                        "OK"
                        if lat_benne and lon_benne
                        else "NEM"
                    )

                except (
                    ValueError,
                    TypeError
                ):
                    ellenorzes = "-"


        # ----------------------------------------------------
        # ÚJ történeti rekord
        # ----------------------------------------------------

        pozicio_tortenet.append({
            "viszonylat": adat["viszonylat"],
            "forda": adat["forda"],
            "kezdés": adat["kezdés"],
            "végzés": adat["végzés"],
            "hely": adat["hely"],
            "helyszín": adat["helyszín"],
            "forrás": adat.get("forrás", "biztor"),
            "rendszám": rendszam,
            "jármű_id": jarmu_id,
            "pozíció": pozicio,
            "pozicio_frissitve": pozicio_frissitve,
            "ellenőrzés": ellenorzes,
            "frissítve": idopont
        })

        uj_poziciok += 1


# ============================================================
# 5. NAPI ADATOK MENTÉSE
# ============================================================

napi_adatok["datum"] = MAI_NAP
napi_adatok["forda_rendszamok"] = forda_rendszamok
napi_adatok["pozicio_tortenet"] = pozicio_tortenet

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


def _ido_objektum(ertek):
    """Idő mező kezelése Excel time vagy HH:MM[:SS] formában."""
    if pd.isna(ertek):
        return None

    if isinstance(ertek, time):
        return ertek

    if isinstance(ertek, datetime):
        return ertek.time()

    szoveg = str(ertek).strip()

    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(szoveg[:8], fmt).time()
        except ValueError:
            continue

    return None


def gps_geozona_vagy_koordinata(pozicio):
    """A GPS-koordinátából geozóna-nevet ad vissza, vagy ha nincs találat, a GPS-t."""
    eredeti = str(pozicio or "").strip()

    try:
        latitude_s, longitude_s = eredeti.split(",", 1)
        latitude = float(latitude_s.strip())
        longitude = float(longitude_s.strip())
    except (ValueError, TypeError):
        return eredeti or "Nincs adat"

    for helyszin in HELYSZINEK.values():
        if (
            helyszin["lat_min"] <= latitude <= helyszin["lat_max"]
            and helyszin["lon_min"] <= longitude <= helyszin["lon_max"]
        ):
            return str(helyszin.get("kulcsszo", "")).strip() or eredeti

    return f"{latitude}, {longitude}"


def hidegtarolas_70_dontes(forda_sor, pozicio_tortenet, most=None):
    """
    A hidegtárolási döntés a forda saját idejének 70%-os pontján születik.

    Fontos:
    - Nem a forda későbbi állapotát nézzük.
    - A 70%-os időponthoz tartozó, utolsó ismert GPS-rekordot használjuk.
    - Ettől a pillanattól az eredmény végleges az adott napra.
    - A döntéshez használt GPS-koordinátát is elmentjük.
    """

    kezdés = _ido_objektum(forda_sor.get("kezdés"))
    végzés = _ido_objektum(forda_sor.get("végzés"))

    if kezdés is None or végzés is None:
        return None

    budapest_tz = ZoneInfo("Europe/Budapest")
    budapest_now = most or budapesti_most()
    mai_datum = budapest_now.date()

    kezdés_dt = datetime.combine(mai_datum, kezdés, tzinfo=budapest_tz)
    végzés_dt = datetime.combine(mai_datum, végzés, tzinfo=budapest_tz)

    if végzés_dt < kezdés_dt:
        végzés_dt += timedelta(days=1)

    teljes_idotartam = (végzés_dt - kezdés_dt).total_seconds()
    if teljes_idotartam <= 0:
        return None

    döntés_dt = kezdés_dt + timedelta(seconds=teljes_idotartam * 0.70)

    # A 70%-os pont előtt még nincs döntés.
    if budapest_now < döntés_dt:
        return None

    rekordok = []

    for rekord in pozicio_tortenet:
        if str(rekord.get("viszonylat", "")).strip() != str(forda_sor.get("viszonylat", "")).strip():
            continue
        if str(rekord.get("forda", "")).strip() != str(forda_sor.get("forda", "")).strip():
            continue
        if str(rekord.get("forrás", "biztor")).strip() != str(forda_sor.get("forrás", "biztor")).strip():
            continue

        idopont = str(rekord.get("frissítve", "")).strip()
        if not idopont:
            continue

        try:
            ido = datetime.strptime(idopont, "%H:%M:%S").time()
            rekord_dt = datetime.combine(mai_datum, ido, tzinfo=budapest_tz)
            if rekord_dt < kezdés_dt:
                rekord_dt += timedelta(days=1)
        except (ValueError, TypeError):
            continue

        if kezdés_dt <= rekord_dt <= döntés_dt:
            rekordok.append((rekord_dt, rekord))

    rekordok.sort(key=lambda x: x[0])

    if rekordok:
        _, rekord = rekordok[-1]
        állapot = str(rekord.get("ellenőrzés", "-")).strip().upper()
        eredmény = "RENDBEN TÁROLT" if állapot == "OK" else "ELTÉRÉS TÖRTÉNT"
        tárolás_helye = gps_geozona_vagy_koordinata(
            rekord.get("pozíció", "")
        )
    else:
        eredmény = "ELTÉRÉS TÖRTÉNT"
        tárolás_helye = "Nincs adat"

    return {
        "eredmény": eredmény,
        "tárolás helye": tárolás_helye,
        "döntés időpontja": döntés_dt.strftime("%H:%M:%S")
    }


def hidegtarolas_riport_eredmeny(forda_sor, pozicio_tortenet):
    """Kompatibilitási segédfüggvény: csak az eredményt adja vissza."""
    döntés = hidegtarolas_70_dontes(forda_sor, pozicio_tortenet)
    if döntés is None:
        return ""
    return döntés["eredmény"]


def keszit_hidegtarolas_riport(forrás="biztor", export_fajl=RIport_XLSX, napi_kulcs="hidegtarolas_riport"):
    """
    A 70%-os döntéseket minden futáskor ellenőrzi és véglegesen elmenti.

    Az Excel-riport naponta egyszer készül el, amikor minden figyelt forda
    elérte a saját 70%-os döntési pontját. Így az Excel is már a végleges,
    70%-nál rögzített eredményt és tárolási helyet kapja.
    """

    most = budapesti_most()

    korabbi_riport = napi_adatok.get(
        napi_kulcs
    ) or {}

    # A döntést nem számoljuk újra, de a korábban elmentett koordinátát
    # utólag geozónára oldjuk fel, ha valamelyik zónába esik.
    dontesek = korabbi_riport.get("dontesek", {})

    if not isinstance(dontesek, dict):
        dontesek = {}

    for dontes in dontesek.values():
        if not isinstance(dontes, dict):
            continue
        hely = str(dontes.get("tárolás helye", "")).strip()
        if hely and hely not in ("Nincs adat", "-"):
            dontes["tárolás helye"] = gps_geozona_vagy_koordinata(hely)

    pozicio_tortenet = napi_adatok.get(
        "pozicio_tortenet",
        []
    )

    figyelt_forras = figyelt_fordak_garazs if forrás == "garazs" else figyelt_fordak_biztor

    uj_dontes = 0

    for _, forda_sor in figyelt_forras.iterrows():
        viszonylat = str(forda_sor["viszonylat"]).strip()
        forda = str(forda_sor["forda"]).strip()
        kulcs = forda_kulcs_adat(forda_sor)

        # Ha már döntöttünk róla, az eredmény és a hely végleges.
        if kulcs in dontesek:
            continue

        dontes = hidegtarolas_70_dontes(
            forda_sor,
            pozicio_tortenet,
            most=most
        )

        if dontes is not None:
            dontesek[kulcs] = {
                "viszonylat": viszonylat,
                "forda": forda,
                "eredmény": dontes["eredmény"],
                "tárolás helye": dontes["tárolás helye"],
                "döntés időpontja": dontes["döntés időpontja"]
            }
            uj_dontes += 1

    eredmenyek = []

    for _, forda_sor in figyelt_forras.iterrows():
        viszonylat = str(forda_sor["viszonylat"]).strip()
        forda = str(forda_sor["forda"]).strip()
        kulcs = forda_kulcs_adat(forda_sor)

        forda_adat = forda_rendszamok.get(kulcs, {})
        rendszam = str(forda_adat.get("rendszám", "")).strip()
        dontes = dontesek.get(kulcs, {})

        eredmenyek.append({
            "dátum": MAI_NAP,
            "viszonylat": viszonylat,
            "forda": forda,
            "rendszám": rendszam,
            "eredmény": dontes.get("eredmény", ""),
            "tárolás helye": dontes.get("tárolás helye", ""),
            "döntés időpontja": dontes.get("döntés időpontja", "")
        })

    # Excel csak akkor készüljön el, amikor minden forda döntése megvan.
    minden_döntött = (
        len(figyelt_forras) == 0
        or len(dontesek) >= len(figyelt_forras)
    )

    excel_mar_mentve = (
        korabbi_riport.get("datum") == MAI_NAP
        and korabbi_riport.get("excel_kesz") is True
    )

    riport_idopont = korabbi_riport.get("keszult", "-")

    if minden_döntött and not excel_mar_mentve:
        os.makedirs("data", exist_ok=True)

        if os.path.exists(export_fajl):
            export_wb = openpyxl.load_workbook(export_fajl)
            if "Riport" in export_wb.sheetnames:
                export_ws = export_wb["Riport"]
            else:
                export_ws = export_wb.create_sheet("Riport")
        else:
            export_wb = openpyxl.Workbook()
            export_ws = export_wb.active
            export_ws.title = "Riport"

        # A riport fejlécét a 6. oszloppal bővítjük.
        export_ws.cell(1, 1).value = "Dátum"
        export_ws.cell(1, 2).value = "Viszonylat"
        export_ws.cell(1, 3).value = "Forda"
        export_ws.cell(1, 4).value = "Rendszám"
        export_ws.cell(1, 5).value = "Eredmény"
        export_ws.cell(1, 6).value = "Tárolás helye"

        zold_toltes = openpyxl.styles.PatternFill(fill_type="solid", fgColor="00B050")
        piros_toltes = openpyxl.styles.PatternFill(fill_type="solid", fgColor="FF0000")
        fekete_toltes = openpyxl.styles.PatternFill(fill_type="solid", fgColor="000000")
        feher_betu = openpyxl.styles.Font(color="FFFFFF", bold=True)

        for sor in eredmenyek:
            if not sor["rendszám"] and sor["forda"]:
                export_eredmeny = "?"
            elif sor["eredmény"] == "RENDBEN TÁROLT":
                export_eredmeny = "I"
            else:
                export_eredmeny = "N"

            export_tarolas_helye = str(
                sor.get("tárolás helye", "")
            ).strip()

            if not export_tarolas_helye:
                export_tarolas_helye = "Nincs adat"

            export_ws.append([
                sor["dátum"],
                sor["viszonylat"],
                sor["forda"],
                sor["rendszám"],
                export_eredmeny,
                export_tarolas_helye
            ])

            eredmeny_cella = export_ws.cell(export_ws.max_row, 5)
            tarolas_cella = export_ws.cell(export_ws.max_row, 6)

            if not sor["rendszám"] and sor["forda"]:
                eredmeny_cella.fill = fekete_toltes
                eredmeny_cella.font = feher_betu
            elif sor["eredmény"] == "RENDBEN TÁROLT":
                eredmeny_cella.fill = zold_toltes
                eredmeny_cella.font = feher_betu
            else:
                eredmeny_cella.fill = piros_toltes
                eredmeny_cella.font = feher_betu

            # A napi riportban a Tárolás helye is az eredmény szerint
            # színeződik. Ha nincs tényleges tárolási adat, nincs szín.
            tarolas_helye = str(sor.get("tárolás helye", "")).strip()
            van_tarolas_adat = (
                tarolas_helye
                and tarolas_helye not in ("Nincs adat", "-")
            )

            if van_tarolas_adat:
                if sor["eredmény"] == "RENDBEN TÁROLT":
                    tarolas_cella.fill = zold_toltes
                    tarolas_cella.font = feher_betu
                elif sor["eredmény"] == "ELTÉRÉS TÖRTÉNT":
                    tarolas_cella.fill = piros_toltes
                    tarolas_cella.font = feher_betu

        for oszlop in range(1, 7):
            max_hossz = 0
            for cella_oszlop in export_ws.iter_cols(min_col=oszlop, max_col=oszlop):
                for cell in cella_oszlop:
                    if cell.value is not None:
                        max_hossz = max(max_hossz, len(str(cell.value)))
            export_ws.column_dimensions[
                openpyxl.utils.get_column_letter(oszlop)
            ].width = min(max_hossz + 2, 35)

        export_wb.save(export_fajl)
        riport_idopont = most.strftime("%Y-%m-%d %H:%M:%S")
        excel_mar_mentve = True

    riportok = {
        "datum": MAI_NAP,
        "kesz": minden_döntött,
        "excel_kesz": excel_mar_mentve,
        "keszult": riport_idopont,
        "utolso_futas": most.strftime("%Y-%m-%d %H:%M:%S"),
        "vizsgalt_fordak": len(eredmenyek),
        "forrás": forrás,
        "dontesek": dontesek,
        "eredmenyek": eredmenyek
    }

    napi_adatok[napi_kulcs] = riportok

    with open(NAPI_ADATOK_FAJL, "w", encoding="utf-8") as f:
        json.dump(napi_adatok, f, ensure_ascii=False, indent=2)

    print()
    print("=== HIDEGTÁROLÁSI RIPORT ===")
    print("Új 70%-os döntések:", uj_dontes)
    print("Meghozott döntések:", len(dontesek), "/", len(figyelt_fordak))
    print("Excel:", "mentve" if excel_mar_mentve else "még vár a teljes döntésre")

    return riportok


# A 70%-os döntések minden futáskor ellenőrzésre kerülnek.
hidegtarolas_riport = keszit_hidegtarolas_riport("biztor", RIport_XLSX, "hidegtarolas_riport")
GARAZS_RIPORT_XLSX = "data/garazstarolas_export.xlsx"
garazstarolas_riport = keszit_hidegtarolas_riport("garazs", GARAZS_RIPORT_XLSX, "garazstarolas_riport")


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
            "Nincs pozíciótörténet, a HTML export az Excel-listát "
            "adat nélkül is elkészíti."
        )


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

    excel_fordak_szama = len(figyelt_fordak_biztor)
    garazs_fordak_szama = len(figyelt_fordak_garazs)

    megtalalt_jarmuvek = len({
        str(rekord.get("rendszám", "")).strip().upper()
        for rekord in pozicio_tortenet
        if str(rekord.get("forrás", "biztor")).strip() == "biztor"
        and str(rekord.get("rendszám", "")).strip()
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

            if str(rekord.get("forrás", "biztor")).strip() == "biztor"
            and rekord.get("frissítve")
        }
    )


    # --------------------------------------------------------
    # Sorok
    # --------------------------------------------------------
    # MINDEN, az első Excelben szereplő forda előre bekerül.
    # A pozíciótörténet ezeket a sorokat csak kiegészíti/frissíti.
    # Így GTFS-RT / FUTÁR adat nélkül is látszik az Excel-sor.

    sorok = {}

    for _, forda_sor in figyelt_fordak_biztor.iterrows():

        viszonylat = str(forda_sor.get("viszonylat", "")).strip()
        forda = str(forda_sor.get("forda", "")).strip()
        kulcs = (viszonylat, forda)

        forda_adat = forda_rendszamok.get(
            forda_kulcs_adat(forda_sor),
            {}
        )

        sorok[kulcs] = {
            "viszonylat": viszonylat,
            "forda": forda,
            "kezdés": str(forda_sor.get("kezdés", ""))[:5],
            "végzés": str(forda_sor.get("végzés", ""))[:5],
            "hely": str(forda_sor.get("hely", "")),
            "rendszám": str(forda_adat.get("rendszám", "")).strip(),
            "forrás": "biztor",
            "ellenőrzés": {}
        }

    # A történeti rekordok rákerülnek az előre létrehozott Excel-sorokra.
    for rekord in pozicio_tortenet:

        if str(rekord.get("forrás", "biztor")).strip() != "biztor":
            continue

        viszonylat = str(rekord.get("viszonylat", "")).strip()
        forda = str(rekord.get("forda", "")).strip()
        kulcs = (viszonylat, forda)

        # Árva történeti rekordot nem hozunk létre az Excel-listán kívül.
        if kulcs not in sorok:
            continue

        rendszam = str(rekord.get("rendszám", "")).strip()

        if rendszam:
            sorok[kulcs]["rendszám"] = rendszam

        idopont = str(rekord.get("frissítve", "")).strip()[:5]

        if idopont:
            sorok[kulcs]["ellenőrzés"][idopont] = (
                rekord.get("ellenőrzés", "-")
            )


    # --------------------------------------------------------
    # TÉRKÉP ADATOK
    # --------------------------------------------------------

    terkep_jarmuvek = {}


    # --------------------------------------------------------
    # TESZT MÓD – A VIZSGÁLT FORDÁK JÁRMŰVEI
    # --------------------------------------------------------
    # Tesztben sem az összes BKK-járművet rajzoljuk ki.
    # Csak azok a rendszámok jelenjenek meg, amelyek a
    # figyelt_fordak valamelyikéhez vannak hozzárendelve.
    # A pozíció viszont mindig az aktuális BKK VehiclePositions.

    if TESZT_MOD:

        vizsgalt_rendszamok = set()

        for _, forda_sor_map in figyelt_fordak.iterrows():

            viszonylat_map = str(
                forda_sor_map.get("viszonylat", "")
            ).strip()

            forda_map = str(
                forda_sor_map.get("forda", "")
            ).strip()

            kulcs_map = f"{viszonylat_map}|{forda_map}"

            forda_adat_map = forda_rendszamok.get(
                kulcs_map,
                {}
            )

            rendszam_map = str(
                forda_adat_map.get("rendszám", "")
            ).strip().upper()

            if rendszam_map:
                vizsgalt_rendszamok.add(rendszam_map)

        for _, jarmu in jarmuvek.iterrows():

            rendszam = str(
                jarmu.get("rendszám", "")
            ).strip().upper()

            if not rendszam:
                continue

            # Tesztben csak a vizsgált fordákhoz tartozó
            # rendszámok jelenjenek meg a térképen.
            if rendszam not in vizsgalt_rendszamok:
                continue

            try:
                latitude = float(jarmu["latitude"])
                longitude = float(jarmu["longitude"])
            except (ValueError, TypeError, KeyError):
                continue

            if latitude == 0 or longitude == 0:
                continue

            elozo_rekord = None

            for rekord in reversed(pozicio_tortenet):
                if (
                    str(rekord.get("rendszám", ""))
                    .strip()
                    .upper()
                    == rendszam
                ):
                    elozo_rekord = rekord
                    break

            if elozo_rekord is not None:
                statusz = str(
                    elozo_rekord.get("ellenőrzés", "-")
                ).strip().upper()
                viszonylat = str(
                    elozo_rekord.get("viszonylat", "")
                )
                forda = str(
                    elozo_rekord.get("forda", "")
                )
                helyszin_nev = str(
                    elozo_rekord.get("helyszín", "")
                )
            else:
                statusz = "-"
                viszonylat = ""
                forda = ""
                helyszin_nev = ""

            try:
                timestamp = int(jarmu.get("timestamp", 0))
                pozicio_frissitve = datetime.fromtimestamp(
                    timestamp,
                    tz=ZoneInfo("Europe/Budapest")
                ).strftime("%H:%M:%S")
            except (ValueError, TypeError, OverflowError):
                pozicio_frissitve = ""

            terkep_jarmuvek[rendszam] = {
                "rendszam": rendszam,
                "viszonylat": viszonylat,
                "forda": forda,
                "helyszin": helyszin_nev,
                "statusz": statusz,
                "latitude": latitude,
                "longitude": longitude,
                "frissitve": utolso_lekkerdezes,
                "pozicio_frissitve": pozicio_frissitve
            }

    else:

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
                ):
                    continue

                # A térképen a forda kezdése előtti 15 percben is
                # jelenjen meg a jármű, sárga PIN-nel.
                try:
                    kezdés_dt_map = datetime.strptime(
                        kezdés,
                        "%H:%M:%S"
                    )
                    végzés_dt_map = datetime.strptime(
                        végzés,
                        "%H:%M:%S"
                    )
                    lekérdezés_dt_map = datetime.strptime(
                        utolso_lekkerdezes,
                        "%H:%M:%S"
                    )

                    ellenőrzési_kezdés_map = (
                        kezdés_dt_map - timedelta(minutes=15)
                    )

                    ellenőrzési_végzés_map = (
                        végzés_dt_map + timedelta(minutes=15)
                    )

                    if not (
                        ellenőrzési_kezdés_map
                        <= lekérdezés_dt_map
                        <= ellenőrzési_végzés_map
                    ):
                        continue

                except (ValueError, TypeError):
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


                # A térkép ugyanazt az ellenőrzési eredményt használja,
                # amely az aktuális GPS-rekordból keletkezett.
                statusz = str(
                    rekord.get(
                        "ellenőrzés",
                        "-"
                    )
                ).strip().upper()

                # A tényleges kezdés előtti 15 percben a PIN sárga,
                # függetlenül attól, hogy az ellenőrzés OK vagy NEM.
                try:
                    kezdés_dt_map = datetime.strptime(
                        kezdés,
                        "%H:%M:%S"
                    )
                    lekérdezés_dt_map = datetime.strptime(
                        utolso_lekkerdezes,
                        "%H:%M:%S"
                    )

                    prestart_sarga = (
                        kezdés_dt_map - timedelta(minutes=15)
                        <= lekérdezés_dt_map
                        < kezdés_dt_map
                    )

                    if (
                        prestart_sarga
                        and statusz in ("OK", "NEM")
                    ):
                        statusz = "SÁRGA"

                except (ValueError, TypeError):
                    pass

                if helyszin is not None:
                    helyszin_nev = helyszin.get(
                        "kulcsszo",
                        helyszin_kulcs
                    )
                else:
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

                    "frissitve": frissitve,

                    "pozicio_frissitve": str(
                        rekord.get(
                            "pozicio_frissitve",
                            ""
                        )
                    ).strip()

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

.tabla-szekcio {

    display: block;

    margin-top: 12px;

    padding-top: 10px;

    border-top: 1px solid #cccccc;

    background: white;

}


.garazs-matrix-cim {
    margin-top: 18px;
    padding: 8px 10px 4px 10px;
    font-size: 14px;
    font-weight: bold;
}

.tabla-szekcio-cim {

    padding: 0 10px 8px 10px;

    font-size: 14px;

    font-weight: bold;

}

.garazs-szekcio-cim {

    margin-top: 14px;

}


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
    width: 200px;
    min-width: 200px;
    max-width: 200px;

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

    height: 31px;

    background: white;

    border: 1px solid #888;

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

.tabla-fejlec-hely {
    height: 31px;
    box-sizing: border-box;
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

.riport-ures {
    background: white;
    color: #000000;
}

.ellenorzes.sarga {
    background: #ffd966 !important;
    color: #000000 !important;
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


.vehicle-pin.yellow {

    background: #ffd966;

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
            <b>Naptípus:</b> """ + (
                escape(str(talalt_munkalap))
                if str(talalt_munkalap).strip() == str(garazs_talalt_munkalap).strip()
                else escape(str(talalt_munkalap)) + " / " + escape(str(garazs_talalt_munkalap))
            ) + """
        </div>
        <div class="adat">
            <b>Utolsó lekérdezés:</b> """ + escape(utolso_ido) + """
        </div>
    </div>

    <div class="fejlec-jobb">
        <div class="adat">
            <b>Riport készült:</b> """ + escape(str(hidegtarolas_riport.get("keszult", "-"))) + """
        </div>
        <div class="adat">
            <b>Exportált fordák:</b> """ + str(hidegtarolas_riport.get("vizsgalt_fordak", 0)) + """
        </div>
    </div>

</div>


<!-- =========================================================
     TÉRKÉP – KÖZVETLENÜL A FEJLÉC ALATT
     ========================================================= -->

<div id="geozona-terkep"></div>


<div class="tabla-szekcio">

<div class="tabla-szekcio-cim">
Végállomáson tároló online járművek: """ + str(megtalalt_jarmuvek) + "/" + str(excel_fordak_szama) + """
</div>


<!-- =========================================================
     BAL: 6 FIX OSZLOP
     JOBB: ÖSSZES IDŐOSZLOP, 18 LÁTHATÓ
     ========================================================= -->

<div class="tabla-egesz">


<!-- =========================================================
     BAL OLDALI TÁBLÁZAT
     ========================================================= -->

<div class="alap-ablak">

<div class="tabla-fejlec-hely"></div>

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


            # A kezdés előtti 15 percben és a végzés utáni 15 percben
            # az I/N mindig fekete legyen. A tényleges kezdéstől a
            # végzésig marad a zöld/piros színezés.
            #
            # Ez itt szándékosan felülírja az OK/NEM alapú osztályozást,
            # mert különben egy későbbi általános .ok/.nem szabály újra
            # zöldre/pirosra színezné a 15 perces ablakot.
            osztaly = "nincs"

            try:
                idopont_dt = datetime.strptime(idopont, "%H:%M")
                kezdes_dt = datetime.strptime(
                    str(sor.get("kezdés", "")),
                    "%H:%M:%S"
                )
                vegzes_dt = datetime.strptime(
                    str(sor.get("végzés", "")),
                    "%H:%M:%S"
                )

                ellenorzes_kezdete = kezdes_dt - timedelta(minutes=15)
                ellenorzes_vege = vegzes_dt + timedelta(minutes=15)

                # A megjelenítés sorrendje szándékosan:
                # 1. ±15 perces ellenőrzési ablak = mindig fekete I/N
                # 2. tényleges kezdés–végzés = OK zöld / NEM piros
                # A számítási/logikai eredmény ettől nem változik.
                if (
                    ellenorzes_kezdete <= idopont_dt < kezdes_dt
                    or vegzes_dt < idopont_dt <= ellenorzes_vege
                ):
                    osztaly = "nincs"

                elif kezdes_dt <= idopont_dt <= vegzes_dt:
                    if eredmeny == "OK":
                        osztaly = "ok"
                    elif eredmeny == "NEM":
                        osztaly = "nem"
                    else:
                        eredmeny = "-"

                else:
                    eredmeny = "-"

            except (ValueError, TypeError):
                if eredmeny == "OK":
                    osztaly = "ok"
                elif eredmeny == "NEM":
                    osztaly = "nem"
                else:
                    osztaly = "nincs"
                    eredmeny = "-"


            megjelenitett_eredmeny = {
                "OK": "I",
                "NEM": "N"
            }.get(
                eredmeny,
                eredmeny
            )

            html.append(
                f'<td class="ellenorzes {osztaly}"'
                + (' style="background:#000000;color:white;"' if osztaly == "nincs" else '')
                + f'>{escape(megjelenitett_eredmeny)}</td>'
            )


        html.append("</tr>")


    html.append("""
</tbody>

</table>

</div>

</div>

</div>

""")

    # --------------------------------------------------------
    # HIDEGTÁROLÁSI RIPORT OSZLOP – HTML
    # A döntés a 70%-os ponton véglegesen elmentett adatból jön.
    # --------------------------------------------------------

    riport_eredmenyek = {
        (
            str(sor.get("viszonylat", "")).strip(),
            str(sor.get("forda", "")).strip()
        ): sor
        for sor in hidegtarolas_riport.get("eredmenyek", [])
    } if hidegtarolas_riport else {}

    html.append("""
<div class="riport-resz">

<div class="tabla-fejlec-hely"></div>

<table class="riport-tablazat">
<thead>
<tr>
    <th>Tárolás helye</th>
</tr>
</thead>
<tbody>
""")

    for _, sor in rendezett_sorok:
        kulcs = (
            str(sor["viszonylat"]).strip(),
            str(sor["forda"]).strip()
        )

        riport_sor = riport_eredmenyek.get(kulcs, {})
        eredmeny = str(riport_sor.get("eredmény", "")).strip()
        tarolas_helye = str(riport_sor.get("tárolás helye", "")).strip()

        # HTML-ben nincs "Nincs adat": adat hiányában maradjon üres.
        if tarolas_helye in ("Nincs adat", "-"):
            tarolas_helye = ""

        if (
            tarolas_helye
            and eredmeny == "RENDBEN TÁROLT"
        ):
            osztaly = "riport-ok"
        elif (
            tarolas_helye
            and eredmeny == "ELTÉRÉS TÖRTÉNT"
        ):
            osztaly = "riport-eltérés"
        else:
            osztaly = "riport-ures"

        html.append(
            f'<tr>'
            f'<td class="{osztaly}">{escape(tarolas_helye)}</td>'
            f'</tr>'
        )

    html.append("""
</tbody>
</table>

</div>

</div>

</div>
""")

    # --------------------------------------------------------
    # MÁSODIK (GARÁZSMENET / JBK) MÁTRIX
    # --------------------------------------------------------

    garazs_riport_eredmenyek = {
        (str(sor.get("viszonylat", "")).strip(), str(sor.get("forda", "")).strip()): sor
        for sor in garazstarolas_riport.get("eredmenyek", [])
    } if garazstarolas_riport else {}

    garazs_sorok = {}
    for _, forda_sor_g in figyelt_fordak_garazs.iterrows():
        visz_g = str(forda_sor_g.get("viszonylat", "")).strip()
        forda_g = str(forda_sor_g.get("forda", "")).strip()
        kulcs_g = (visz_g, forda_g)
        garazs_sorok[kulcs_g] = {
            "viszonylat": visz_g,
            "forda": forda_g,
            "kezdés": str(forda_sor_g.get("kezdés", ""))[:5],
            "végzés": str(forda_sor_g.get("végzés", ""))[:5],
            "hely": str(forda_sor_g.get("hely", "")),
            "rendszám": str(forda_rendszamok.get(forda_kulcs_adat(forda_sor_g), {}).get("rendszám", "")),
            "ellenőrzés": {}
        }

    for rekord in pozicio_tortenet:
        if str(rekord.get("forrás", "biztor")).strip() != "garazs":
            continue
        kulcs_g = (str(rekord.get("viszonylat", "")).strip(), str(rekord.get("forda", "")).strip())
        if kulcs_g not in garazs_sorok:
            continue
        idopont_g = str(rekord.get("frissítve", ""))[:5]
        if idopont_g:
            garazs_sorok[kulcs_g]["ellenőrzés"][idopont_g] = rekord.get("ellenőrzés", "-")

    # A garázsos mátrix ugyanazt a közös időtengelyt használja, mint a BIZTOR.
    # Így akkor is megjelennek az időoszlopok, ha a garázsos fordáknál
    # még nincs saját RT/pozíció rekord.
    garazs_sajat_idopontok = {
        str(rekord.get("frissítve", ""))[:5]
        for rekord in pozicio_tortenet
        if str(rekord.get("forrás", "biztor")).strip() == "garazs" and rekord.get("frissítve")
    }
    garazs_idopontok = sorted(set(idopontok) | garazs_sajat_idopontok)

    html.append("""
<div class="tabla-szekcio-cim garazs-szekcio-cim">
  Garázsban tároló online járművek: """ + str(sum(1 for k in garazs_sorok if garazs_sorok[k]["rendszám"])) + "/" + str(len(figyelt_fordak_garazs)) + """
</div>
<div class="tabla-egesz">
<div class="alap-ablak">
<div class="tabla-fejlec-hely"></div>
<table><thead><tr>
<th class="viszonylat">Viszonylat</th><th class="forda">Forda</th><th class="kezdés">Kezdés</th><th class="végzés">Végzés</th><th class="hely">Hely</th><th class="rendszam">Rendszám</th>
</tr></thead><tbody>
""")

    garazs_rendezett = sorted(garazs_sorok.items(), key=lambda x: (x[1].get("kezdés", ""), x[1].get("viszonylat", ""), x[1].get("forda", "")))
    for _, sor_g in garazs_rendezett:
        html.append(
            f'<tr><td class="alap viszonylat">{escape(sor_g["viszonylat"])}</td>'
            f'<td class="alap forda">{escape(sor_g["forda"])}</td>'
            f'<td class="alap kezdés">{escape(sor_g["kezdés"])}</td>'
            f'<td class="alap végzés">{escape(sor_g["végzés"])}</td>'
            f'<td class="alap hely">{escape(sor_g["hely"])}</td>'
            f'<td class="alap rendszam">{escape(sor_g["rendszám"])}</td></tr>'
        )

    html.append("""
</tbody></table></div>
<div class="idopont-resz">
<div class="idopont-csuszkasav">
<input type="range" id="garazs-idopont-csuszka" min="0" max="1000" value="1000" step="1">
</div>
<div class="idopont-ablak" id="garazs-idopont-ablak">
<div class="idopont-belső" id="garazs-idopont-belső">
<table><thead><tr>
""")

    for idopont_g in garazs_idopontok:
        html.append(f'<th class="idopont">{escape(idopont_g)}</th>')

    html.append("</tr></thead><tbody>")

    for _, sor_g in garazs_rendezett:
        html.append("<tr>")
        for idopont_g in garazs_idopontok:
            eredmeny_g = sor_g["ellenőrzés"].get(idopont_g, "-")
            osztaly_g = "nincs"
            megj_g = {"OK": "I", "NEM": "N"}.get(eredmeny_g, "-")

            # A garázs mátrix időszínezése pontosan ugyanaz, mint
            # a fő (BIZTOR) mátrixé:
            # - kezdés előtt 15 perc: fekete I/N
            # - kezdéstől végzésig: OK = zöld, NEM = piros
            # - végzés után 15 perc: fekete I/N
            try:
                t = datetime.strptime(idopont_g, "%H:%M")
                k = datetime.strptime(sor_g["kezdés"], "%H:%M")
                v = datetime.strptime(sor_g["végzés"], "%H:%M")
                ellenorzes_kezdete = k - timedelta(minutes=15)
                ellenorzes_vege = v + timedelta(minutes=15)

                # A garázs mátrixban is elsőbbséget kap a ±15 perces
                # ellenőrzési ablak: ott mindig fekete I/N.
                if (
                    ellenorzes_kezdete <= t < k
                    or v < t <= ellenorzes_vege
                ):
                    osztaly_g = "nincs"

                elif k <= t <= v:
                    if eredmeny_g == "OK":
                        osztaly_g = "ok"
                    elif eredmeny_g == "NEM":
                        osztaly_g = "nem"
                    else:
                        megj_g = "-"

                else:
                    megj_g = "-"
            except (ValueError, TypeError):
                if eredmeny_g == "OK":
                    osztaly_g = "ok"
                elif eredmeny_g == "NEM":
                    osztaly_g = "nem"
                else:
                    osztaly_g = "nincs"
                    megj_g = "-"

            html.append(
                f'<td class="ellenorzes {osztaly_g}"'
                + (' style="background:#000000;color:white;"' if osztaly_g == "nincs" else '')
                + f'>{escape(megj_g)}</td>'
            )
        html.append("</tr>")

    html.append("""
</tbody></table></div>
</div>
</div>
<div class="riport-resz">
<div class="tabla-fejlec-hely"></div>
<table class="riport-tablazat"><thead><tr><th>Tárolás helye</th></tr></thead><tbody>
""")

    for _, sor_g in garazs_rendezett:
        rs = garazs_riport_eredmenyek.get((sor_g["viszonylat"], sor_g["forda"]), {})
        e = str(rs.get("eredmény", "")).strip()
        h = str(rs.get("tárolás helye", "")).strip()

        van_tarolas_adat = (
            h
            and h not in ("Nincs adat", "-")
        )

        if van_tarolas_adat and e == "RENDBEN TÁROLT":
            cls = "riport-ok"
        elif van_tarolas_adat and e == "ELTÉRÉS TÖRTÉNT":
            cls = "riport-eltérés"
        else:
            cls = "riport-ures"

        html.append(
            f'<tr><td class="{cls}">{escape(h)}</td></tr>'
        )

    html.append("""
</tbody></table>
</div>
</div>

""")

    html.append("""
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

""")

    html.append("""
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
    else if (statusz === "SÁRGA") {
        osztaly = "yellow";
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
            color: (
                zona.nev === "ArrivaBus Andor telephely"
                || zona.nev === "ArrivaBus Bogáncs telephely"
                || zona.nev === "ArrivaBus Szállító telephely"
            ) ? "#00a651" : "#3388ff",
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

        + "<b>Utolsó friss GPS-pozíció:</b> "
        + escapeHtml(
            jarmu.pozicio_frissitve
            || jarmu.frissitve
        )
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

const garazsAblak = document.getElementById("garazs-idopont-ablak");
const garazsBelso = document.getElementById("garazs-idopont-belső");
const garazsCsuszka = document.getElementById("garazs-idopont-csuszka");
function frissitGarazsCsuszkat() {
    if (!garazsAblak || !garazsBelso || !garazsCsuszka) return;
    const maxScroll = Math.max(0, garazsBelso.scrollWidth - garazsAblak.clientWidth);
    garazsCsuszka.value = "1000";
    garazsCsuszka.oninput = function() { garazsAblak.scrollLeft = maxScroll * (Number(this.value) / 1000); };
    garazsAblak.scrollLeft = maxScroll;
}
window.addEventListener("load", frissitGarazsCsuszkat);

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

