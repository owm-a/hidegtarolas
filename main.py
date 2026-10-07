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
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


_http_session = requests.Session()
_http_retry = Retry(
    total=3,
    connect=3,
    read=3,
    backoff_factor=1,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=frozenset(["GET"]),
    raise_on_status=False,
)
_http_session.mount("https://", HTTPAdapter(max_retries=_http_retry))
_http_session.mount("http://", HTTPAdapter(max_retries=_http_retry))


def http_get(*args, **kwargs):
    return _http_session.get(*args, **kwargs)


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
        "Új GTFS szükséges; a régi cache-t csak sikeres letöltés után cseréljük le."
    )


    # -----------------------------------------------------
    # Új GTFS letöltése
    # -----------------------------------------------------

    print(
        "Új GTFS letöltése..."
    )

    gtfs_response = http_get(
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
    # Új GTFS atomikus mentése
    # -----------------------------------------------------

    gtfs_tmp = GTFS_CACHE_FILE + ".tmp"
    with open(gtfs_tmp, "wb") as f:
        f.write(gtfs_response.content)
        f.flush()
        os.fsync(f.fileno())

    os.replace(gtfs_tmp, GTFS_CACHE_FILE)


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

def ido_masodpercben(ertek):
    """GTFS/Excel idő HH:MM[:SS] formában, 24 óra felett is."""
    if ertek is None or (isinstance(ertek, float) and pd.isna(ertek)):
        return None
    if isinstance(ertek, timedelta):
        return int(ertek.total_seconds())
    if isinstance(ertek, time):
        return ertek.hour * 3600 + ertek.minute * 60 + ertek.second
    if isinstance(ertek, datetime):
        return ertek.hour * 3600 + ertek.minute * 60 + ertek.second
    szoveg = str(ertek).strip()
    if not szoveg:
        return None
    try:
        reszek = szoveg.split(":")
        if len(reszek) not in (2, 3):
            return None
        ora = int(reszek[0])
        perc = int(reszek[1])
        masodperc = int(reszek[2]) if len(reszek) == 3 else 0
        if perc < 0 or perc >= 60 or masodperc < 0 or masodperc >= 60 or ora < 0:
            return None
        return ora * 3600 + perc * 60 + masodperc
    except (ValueError, TypeError):
        return None


def forda_aktiv_e(kezdés, végzés, időpont):
    kezdet = ido_masodpercben(kezdés)
    veg = ido_masodpercben(végzés)
    most = ido_masodpercben(időpont)
    if kezdet is None or veg is None or most is None:
        return False
    if veg < kezdet:
        veg += 24 * 3600
    if most < kezdet:
        most += 24 * 3600
    return kezdet - 15 * 60 <= most <= veg + 15 * 60


def atomikus_json_mentes(fajl, adat):
    """JSON atomikus írása: félbemaradt futás ne hagyjon csonka fájlt."""
    konyvtar = os.path.dirname(fajl) or "."
    os.makedirs(konyvtar, exist_ok=True)
    ideiglenes = fajl + ".tmp"
    with open(ideiglenes, "w", encoding="utf-8") as f:
        json.dump(adat, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(ideiglenes, fajl)


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

# Azonos viszonylat+forda több Excel-sorban: ne csendben írjuk felül.
_duplikalt_fordak = figyelt_fordak_biztor.assign(
    _kulcs=figyelt_fordak_biztor["viszonylat"].astype(str).str.strip() + "|" +
           figyelt_fordak_biztor["forda"].astype(str).str.strip()
).loc[lambda x: x["_kulcs"].duplicated(keep=False), "_kulcs"].unique()
if len(_duplikalt_fordak):
    print("FIGYELEM: többször szereplő BIZTOR forda-kulcs(ok):", ", ".join(_duplikalt_fordak))


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
    <= time(15, 0)
)

# A 70%-os döntés előtti "Pótlásban vesz részt" figyeléshez
# 15:00 után is szükség van az aktuális GTFS-RT tripre.
gtfs_rt_trip_figyeles_idoszak = (
    time(7, 30)
    <= fazis_ideje
    <= time(17, 30)
)

pozicio_idoszak = (
    time(6, 30)
    < fazis_ideje
    <= time(17, 30)
)

print()
print(
    "Budapesti aktuális idő:",
    fazis_ideje.strftime("%H:%M:%S")
)

if azonositas_idoszak:
    print(
        "Aktív fázis: 07:00–15:00 "
        "forda → rendszám + jármű ID"
    )
elif pozicio_idoszak:
    print(
        "Aktív fázis: 06:30–17:30 "
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
    try:
        with open(NAPI_ADATOK_FAJL, "r", encoding="utf-8") as f:
            napi_adatok = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"FIGYELEM: a napi adatfájl nem olvasható, üres adatokkal folytatjuk: {e}")
        napi_adatok = {}
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

if gtfs_rt_trip_figyeles_idoszak:

    url = (
        "https://go.bkk.hu/api/query/v1/ws/"
        "gtfs-rt/full/VehiclePositions.txt"
    )

    response = http_get(
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
    #
    # A GTFS-RT-ből csak az azonosításhoz szükséges adatokat
    # készítjük elő:
    #   - rendszám
    #   - jármű ID
    #   - trip ID
    #
    # A tényleges pozíciót később kizárólag a FUTÁR adja.
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

else:

    # A GTFS-RT tripfigyelésen kívül nincs aktuális feed.
    # A korábban elmentett rendszám + jármű ID marad érvényben.
    feed = gtfs_realtime_pb2.FeedMessage()

    print(
        "GTFS-RT lekérés kihagyva: nincs aktív 07:30–17:30-as figyelési fázis."
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

    # GTFS-idők másodpercben: így a 24:00–29:59 közötti
    # éjszakai trip-ek is kezelhetők. Éjfél után a jelenlegi
    # óraértéket egyszer 24 órával eltolva is megvizsgáljuk.
    forda_idok["kezdet_sec"] = forda_idok["kezdet"].apply(ido_masodpercben)
    forda_idok["vége_sec"] = forda_idok["vége"].apply(ido_masodpercben)
    aktualis_sec = ido_masodpercben(idopont)
    if aktualis_sec is None:
        continue
    aktualis_sec_24 = aktualis_sec + 24 * 3600

    aktiv_trip = forda_idok[
        (
            (forda_idok["kezdet_sec"] <= aktualis_sec)
            & (forda_idok["vége_sec"] >= aktualis_sec)
        )
        |
        (
            (forda_idok["kezdet_sec"] <= aktualis_sec_24)
            & (forda_idok["vége_sec"] >= aktualis_sec_24)
        )
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

atomikus_json_mentes(NAPI_ADATOK_FAJL, napi_adatok)


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
            response = http_get(
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
        f"garazs|{viszonylat}|{forda}"
        if str(rekord.get("forrás", "biztor")).strip() == "garazs"
        else f"{viszonylat}|{forda}"
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
# 16:30-TÓL, NAPONTA EGYSZER
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


def _gtfs_rt_potlasban_van(forda_sor, rendszam, most):
    """
    GTFS-RT alapján eldönti, hogy a forda saját 70%-os döntési pontja előtt
    a hozzá rendelt rendszám éppen egy, a saját fordán kívüli tripet teljesít-e.

    Fontos: nem a forrás Excel másik fordáit vizsgáljuk.
    A forrás Excel csak azt mondja meg, melyik forda rendszámát figyeljük.
    Az aktuális trip kizárólag a GTFS-RT-ből származhat.
    """
    rendszam = str(rendszam or "").strip().upper()
    if not rendszam or not isinstance(jarmuvek, pd.DataFrame) or jarmuvek.empty:
        return None

    kezdés = _ido_objektum(forda_sor.get("kezdés"))
    végzés = _ido_objektum(forda_sor.get("végzés"))
    if kezdés is None or végzés is None:
        return None

    budapest_tz = ZoneInfo("Europe/Budapest")
    mai_datum = most.date()
    kezdés_dt = datetime.combine(mai_datum, kezdés, tzinfo=budapest_tz)
    végzés_dt = datetime.combine(mai_datum, végzés, tzinfo=budapest_tz)
    if végzés_dt < kezdés_dt:
        végzés_dt += timedelta(days=1)

    if not (kezdés_dt <= most < végzés_dt):
        return None

    teljes_idotartam = (végzés_dt - kezdés_dt).total_seconds()
    if teljes_idotartam <= 0:
        return None

    döntés_dt = kezdés_dt + timedelta(seconds=teljes_idotartam * 0.70)

    # A 70%-os döntés után a pótlásfigyelés már irreleváns.
    if most >= döntés_dt:
        return None

    # A saját forda mai, tényleges tripjei.
    viszonylat = str(forda_sor.get("viszonylat", "")).strip()
    forda = str(forda_sor.get("forda", "")).strip()

    try:
        sajat_forda_trips = trips[
            trips["service_id"].astype(str).isin(mai_service_ids)
            & trips["block_id"].astype(str).str.contains(
                f"_{viszonylat}_{forda}_", na=False, regex=False
            )
        ]
    except Exception:
        return None

    sajat_trip_ids = set(sajat_forda_trips["trip_id"].astype(str))
    if not sajat_trip_ids:
        return None

    talalatok = jarmuvek[
        jarmuvek["rendszám"].astype(str).str.strip().str.upper() == rendszam
    ].copy()

    if talalatok.empty:
        return None

    # Ha a GTFS-RT-ben az adott rendszám aktuális tripje ismert,
    # és az nem tartozik a vizsgált forda mai tripjei közé,
    # akkor a jármű fordán kívüli tripet teljesít.
    for _, rt in talalatok.iterrows():
        aktualis_trip_id = str(rt.get("trip_id", "")).strip()
        if not aktualis_trip_id:
            continue
        if aktualis_trip_id not in sajat_trip_ids:
            return {
                "trip_id": aktualis_trip_id,
                "jármű_id": str(rt.get("jármű_id", "")).strip(),
                "route_id": str(rt.get("route_id", "")).strip(),
                "direction_id": str(rt.get("direction_id", "")).strip(),
            }

    return None


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
        if budapesti_most().time() >= time(17, 30):
            return {
                "eredmény": "NINCS ADAT",
                "tárolás helye": "Nincs adat",
                "döntés időpontja": budapesti_most().strftime("%H:%M:%S")
            }
        return None

    budapest_tz = ZoneInfo("Europe/Budapest")
    budapest_now = most or budapesti_most()
    mai_datum = budapest_now.date()

    kezdés_dt = datetime.combine(mai_datum, kezdés, tzinfo=budapest_tz)
    végzés_dt = datetime.combine(mai_datum, végzés, tzinfo=budapest_tz)

    if végzés_dt < kezdés_dt:
        végzés_dt += timedelta(days=1)

    # A forda saját kezdése után, de a 70%-os döntési pont előtt
    # GTFS-RT alapján figyeljük, hogy a hozzárendelt rendszám
    # fordán kívüli tripben vesz-e részt.
    # Ez a döntés végleges, a későbbi 70%-os döntés nem írhatja felül.
    if kezdés_dt <= budapest_now < végzés_dt:
        forda_kulcs = forda_kulcs_adat(forda_sor)
        forda_adat = forda_rendszamok.get(forda_kulcs, {})
        rendszam = str(forda_adat.get("rendszám", "")).strip()

        potlas = _gtfs_rt_potlasban_van(
            forda_sor,
            rendszam,
            budapest_now
        )

        if potlas is not None:
            return {
                "eredmény": "Pótlásban vesz részt",
                "tárolás helye": "---",
                "döntés időpontja": budapest_now.strftime("%H:%M:%S"),
                "pótlás_trip_id": potlas["trip_id"],
                "pótlás_jármű_id": potlas["jármű_id"],
                "pótlás_route_id": potlas["route_id"],
                "pótlás_direction_id": potlas["direction_id"],
            }

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
        if állapot == "OK":
            eredmény = "RENDBEN TÁROLT"
        elif állapot == "NEM":
            eredmény = "ELTÉRÉS TÖRTÉNT"
        else:
            eredmény = "NINCS ADAT"
        tárolás_helye = gps_geozona_vagy_koordinata(
            rekord.get("pozíció", "")
        )
    else:
        # A 70%-os pontig nem volt használható GPS-adat: ez nem NEM.
        eredmény = "NINCS ADAT"
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

    Az Excel-riport naponta egyszer, 16:30 után készül el az aktuális állapotról.
    Nem várjuk meg hozzá, hogy minden forda 70%-os döntése megszülessen;
    a még nem eldöntött sorok is bekerülnek az exportba.
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
                "döntés időpontja": dontes["döntés időpontja"],
                "pótlás_viszonylata": dontes.get("pótlás_viszonylata", ""),
                "pótlás_fordája": dontes.get("pótlás_fordája", ""),
                "pótlás_trip_id": dontes.get("pótlás_trip_id", ""),
                "pótlás_jármű_id": dontes.get("pótlás_jármű_id", ""),
                "pótlás_route_id": dontes.get("pótlás_route_id", ""),
                "pótlás_direction_id": dontes.get("pótlás_direction_id", "")
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
            "döntés időpontja": dontes.get("döntés időpontja", ""),
            "pótlás_viszonylata": dontes.get("pótlás_viszonylata", ""),
            "pótlás_fordája": dontes.get("pótlás_fordája", "")
        })

    # Excel 16:30 után mindenképpen készüljön el az aktuális állapotról.
    minden_döntött = (
        len(figyelt_forras) == 0
        or len(dontesek) >= len(figyelt_forras)
    )

    # A napi Excel-riport semmilyen körülmények között ne készüljön 16:30 előtt.
    # Ha egy korábbi hibás futás 16:30 előtt már excel_kesz=True értéket mentett,
    # azt is újra megnyitjuk, hogy a 16:30 utáni futás ténylegesen elkészíthesse.
    riport_indithato = most.time() >= time(16, 30)

    korabbi_keszult = str(korabbi_riport.get("keszult", "")).strip()
    korabbi_keszult_ido = None
    try:
        if " " in korabbi_keszult:
            korabbi_keszult_ido = datetime.strptime(korabbi_keszult, "%Y-%m-%d %H:%M:%S").time()
    except (ValueError, TypeError):
        korabbi_keszult_ido = None

    excel_mar_mentve = (
        korabbi_riport.get("datum") == MAI_NAP
        and korabbi_riport.get("excel_kesz") is True
        and korabbi_keszult_ido is not None
        and korabbi_keszult_ido >= time(16, 30)
    )

    riport_idopont = korabbi_riport.get("keszult", "-")

    if riport_indithato and not excel_mar_mentve:
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
            if sor["eredmény"] == "Pótlásban vesz részt":
                export_eredmeny = "P"
            elif sor["eredmény"] == "NINCS ADAT" or (not sor["rendszám"] and sor["forda"]):
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

            if sor["eredmény"] == "Pótlásban vesz részt":
                eredmeny_cella.fill = openpyxl.styles.PatternFill(fill_type="solid", fgColor="5B9BD5")
                eredmeny_cella.font = feher_betu
            elif sor["eredmény"] == "NINCS ADAT" or (not sor["rendszám"] and sor["forda"]):
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

            if sor["eredmény"] == "Pótlásban vesz részt":
                # A pótlás geolokációja szándékosan "---", és kék.
                tarolas_cella.font = openpyxl.styles.Font(color="4DA3FF", bold=True)
            elif van_tarolas_adat:
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

    atomikus_json_mentes(NAPI_ADATOK_FAJL, napi_adatok)

    print()
    print("=== HIDEGTÁROLÁSI RIPORT ===")
    print("Új 70%-os döntések:", uj_dontes)
    print("Meghozott döntések:", len(dontesek), "/", len(figyelt_forras))
    print("Excel:", "mentve" if excel_mar_mentve else "16:30-ra vár")

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
    # Online járművek száma a nézetekhez
    # --------------------------------------------------------
    # A kapcsolón látható X/Y jelentése:
    # X = ahány figyelt fordához már sikerült rendszám + jármű ID párost menteni.
    # Y = az adott forrás összes figyelt fordája.
    # A mentett azonosítás 13:30 után is érvényes marad; ilyenkor
    # nem szabad az aktuális GTFS-RT pillanatnyi listával újraszámolni.
    def online_jarmu_szamlalo(forras):
        forras_fordak = (
            figyelt_fordak_biztor
            if forras == "biztor"
            else figyelt_fordak_garazs
        )

        azonosított = 0
        for _, fs in forras_fordak.iterrows():
            adat = forda_rendszamok.get(forda_kulcs_adat(fs), {})
            rendszam = str(adat.get("rendszám", "")).strip()
            jarmu_id = str(adat.get("jármű_id", "")).strip()
            if rendszam and jarmu_id:
                azonosított += 1

        return azonosított, len(forras_fordak)

    biz_online, biz_osszes = online_jarmu_szamlalo("biztor")
    garazs_online, garazs_osszes = online_jarmu_szamlalo("garazs")
    osszes_online = biz_online + garazs_online
    osszes_osszes = biz_osszes + garazs_osszes

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

            kulcs_map = forda_kulcs_adat(forda_sor_map)

            forda_adat_map = forda_rendszamok.get(
                kulcs_map,
                {}
            )

            rendszam_map = str(
                forda_adat_map.get("rendszám", "")
            ).strip().upper()

            if rendszam_map:
                vizsgalt_rendszamok.add(rendszam_map)

        # A jarmuvek DataFrame itt NEM használható pozícióforrásként:
        # az csak GTFS-RT azonosítási adatokat tartalmaz
        # (rendszám + jármű ID + trip ID). A tényleges GPS-pozíció
        # kizárólag a FUTÁR vehicles-for-location adatából jön.
        for _, forda_sor_map in figyelt_fordak.iterrows():

            kulcs_map = forda_kulcs_adat(forda_sor_map)
            forda_adat_map = forda_rendszamok.get(kulcs_map, {})

            rendszam = str(
                forda_adat_map.get("rendszám", "")
            ).strip().upper()

            if not rendszam or rendszam not in vizsgalt_rendszamok:
                continue

            jarmu_id_map = str(
                forda_adat_map.get("jármű_id", "")
            ).strip()
            if not jarmu_id_map:
                continue

            futar_id_map = jarmu_id_map
            if not futar_id_map.upper().startswith("BKK_"):
                futar_id_map = f"BKK_{futar_id_map}"

            jarmu_map = futar_jarmuvek.get(futar_id_map)
            if not jarmu_map:
                continue

            location_map = jarmu_map.get("location") or {}

            try:
                latitude = float(location_map.get("lat"))
                longitude = float(location_map.get("lon"))
            except (ValueError, TypeError):
                continue

            if latitude == 0 or longitude == 0:
                continue

            viszonylat = str(forda_sor_map.get("viszonylat", "")).strip()
            forda = str(forda_sor_map.get("forda", "")).strip()
            helyszin_nev = str(forda_sor_map.get("hely", "")).strip()

            statusz = "-"
            for rekord in reversed(pozicio_tortenet):
                if (
                    str(rekord.get("rendszám", "")).strip().upper() == rendszam
                    and forda_kulcs_rekord(rekord) == kulcs_map
                ):
                    statusz = str(
                        rekord.get("ellenőrzés", "-")
                    ).strip().upper()
                    break

            pozicio_frissitve = futar_idopont(
                jarmu_map.get("lastUpdateTime")
            ) or ""

            terkep_jarmuvek[rendszam] = {
                "rendszam": rendszam,
                "viszonylat": viszonylat,
                "forda": forda,
                "forras": str(forda_sor_map.get("forrás", "biztor")).strip() or "biztor",
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

                # A pótlásos döntés a térképen is kék.
                if str(rekord.get("döntés", "")).strip() == "Pótlásban vesz részt":
                    statusz = "PÓTLÁS"

                # A végleges riportdöntés az irányadó a térképen is.
                rekord_forras = str(rekord.get("forrás", "biztor")).strip() or "biztor"
                rekord_kulcs = forda_kulcs_rekord(rekord)
                riport_adat = (
                    (garazstarolas_riport if rekord_forras == "garazs" else hidegtarolas_riport)
                    or {}
                ).get("dontesek", {}).get(rekord_kulcs, {})
                if str(riport_adat.get("eredmény", "")).strip() == "Pótlásban vesz részt":
                    statusz = "PÓTLÁS"

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

                    "forras": str(rekord.get("forrás", "biztor")).strip() or "biztor",

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
    # RIport eredmények – a megjelenítéshez közös táblába kerülnek
    # --------------------------------------------------------

    riport_eredmenyek = {
        (str(sor.get("viszonylat", "")).strip(), str(sor.get("forda", "")).strip()): sor
        for sor in hidegtarolas_riport.get("eredmenyek", [])
    } if hidegtarolas_riport else {}

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
            "viszonylat": visz_g, "forda": forda_g,
            "kezdés": str(forda_sor_g.get("kezdés", ""))[:5],
            "végzés": str(forda_sor_g.get("végzés", ""))[:5],
            "hely": str(forda_sor_g.get("hely", "")),
            "rendszám": str(forda_rendszamok.get(forda_kulcs_adat(forda_sor_g), {}).get("rendszám", "")),
            "forrás": "garazs", "ellenőrzés": {}
        }

    for rekord in pozicio_tortenet:
        if str(rekord.get("forrás", "biztor")).strip() != "garazs":
            continue
        kulcs_g = (str(rekord.get("viszonylat", "")).strip(), str(rekord.get("forda")).strip())
        if kulcs_g not in garazs_sorok:
            continue
        rendszam_g = str(rekord.get("rendszám", "")).strip()
        if rendszam_g:
            garazs_sorok[kulcs_g]["rendszám"] = rendszam_g
        idopont_g = str(rekord.get("frissítve", "")).strip()[:5]
        if idopont_g:
            garazs_sorok[kulcs_g]["ellenőrzés"][idopont_g] = rekord.get("ellenőrzés", "-")

    idopontok = sorted({
        str(rekord.get("frissítve", ""))[:5]
        for rekord in pozicio_tortenet
        if rekord.get("frissítve")
        and str(rekord.get("forrás", "biztor")).strip() in ("biztor", "garazs")
    })

    # --------------------------------------------------------
    # HTML – STABIL FIX / IDŐ / FIX TÁBLÁZATMOTOR
    # --------------------------------------------------------
    #
    # A megjelenítés három fizikailag külön táblából áll:
    #   1. bal oldali fix 6 oszlop
    #   2. középső, kizárólag vízszintesen görgethető időtábla
    #   3. jobb oldali fix Valós tárolás oszlop
    #
    # A három rész sorazonosító alapján együtt mozog. Így az időoszlopok
    # sem rétegzéssel, sem sticky pozicionálással nem kerülnek a fix
    # oszlopok fölé.
    # --------------------------------------------------------

    html = []

    html.append("""
<!DOCTYPE html>
<html lang="hu">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ArrivaBus hidegtárolás</title>
<style>
:root{
    --bg:#11151b;--surface:#181e26;--surface2:#202733;--surface3:#252d39;
    --border:#313b49;--text:#e8edf3;--muted:#9ca8b7;--accent:#6ea8fe;
    --accent2:#4f8ff7;--ok:#16a765;--bad:#e05252;--dark:#2c333d;
    --shadow:0 10px 30px rgba(0,0,0,.20);--radius:12px;
    --left-width:auto;--storage-width:auto;
}
html{background:var(--bg);width:100%;max-width:100%;overflow-x:hidden}
body{
    margin:0;padding:18px;width:100%;max-width:100%;box-sizing:border-box;
    overflow-x:hidden;background:radial-gradient(circle at 10% 0%,rgba(110,168,254,.07),transparent 28%),var(--bg);
    color:var(--text);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;
}
.fejlec,.tabla-szekcio{
    background:rgba(24,30,38,.96);border:1px solid var(--border);border-radius:var(--radius);
    box-shadow:var(--shadow);box-sizing:border-box;
}
.fejlec{padding:16px 18px;margin-bottom:14px}
.fejlec-top{display:flex;align-items:center;justify-content:space-between;gap:16px;width:100%;margin-bottom:9px}
.cim{color:#f3f6fa;font-size:23px;letter-spacing:-.02em;margin:0}\n#oldal-cim{cursor:pointer}
.fejlec-adatok{display:flex;align-items:center;justify-content:space-between;width:100%;gap:20px}
.fejlec-bal,.fejlec-jobb{display:flex;align-items:center;gap:20px;white-space:nowrap}
.fejlec-jobb{margin-left:auto}
.adat{font-size:12px;color:var(--muted);white-space:nowrap}.adat b{color:var(--text);font-weight:600}
.theme-toggle{border:1px solid var(--border);background:var(--surface2);color:var(--text);border-radius:8px;padding:7px 10px;font:inherit;font-size:12px;font-weight:650;cursor:pointer;white-space:nowrap;transition:.16s}
.theme-toggle:hover{background:var(--surface3);border-color:var(--accent)}
#geozona-terkep{width:100%;height:50vh;max-height:50vh;min-height:320px;margin:0 0 14px;border:1px solid var(--border);border-radius:var(--radius);overflow:hidden;box-shadow:var(--shadow);background:var(--surface)}
.nezet-valaszto{display:flex;align-items:center;gap:6px;margin:0 0 14px;padding:4px;width:fit-content;background:var(--surface);border:1px solid var(--border);border-radius:10px;box-shadow:0 6px 20px rgba(0,0,0,.16)}
.nezet-gomb{border:0;border-radius:7px;padding:8px 13px;background:transparent;color:var(--muted);font:inherit;font-size:13px;font-weight:650;cursor:pointer;transition:.16s}
.nezet-gomb:hover{color:var(--text);background:var(--surface3)}
.nezet-gomb.active{color:white;background:linear-gradient(135deg,var(--accent2),#6b7ff0);box-shadow:0 4px 12px rgba(79,143,247,.24)}
.nezet-gomb:active{transform:translateY(1px)}
.online-szam{display:inline-block;margin-left:5px;font-size:11px;font-weight:600;color:var(--muted);opacity:.9}.nezet-gomb.active .online-szam{color:rgba(255,255,255,.82)}
.nezet-panel{display:block}.nezet-panel.hidden{display:none!important}
.tabla-szekcio{width:100%;max-width:100%;margin:0;padding:12px;border-top:1px solid var(--border);overflow:hidden}
.idopont-csuszkasav{
    width:90%;height:38px;margin:0 auto;display:flex;align-items:center;justify-content:center;
    background:var(--surface2);border:1px solid var(--border);border-radius:8px;
    box-sizing:border-box;overflow:hidden;padding:0 12px;
}
.csuszka-info{color:var(--muted);font-size:12px;font-weight:650;white-space:nowrap;padding-left:8px}
.csuszka-info strong{color:var(--text)}
.idopont-csuszkasav input[type=range]{width:100%;margin:0;accent-color:var(--accent);cursor:pointer}
.tabla-egesz{display:grid;grid-template-columns:var(--left-width) minmax(0,1fr) var(--storage-width);width:100%;max-width:100%;min-width:0;overflow:hidden;background:var(--surface)}
.fix-ablak{min-width:0;overflow:hidden;background:var(--surface)}
.ido-ablak{min-width:0;overflow:hidden;background:var(--surface);border-left:1px solid var(--border);border-right:1px solid var(--border)}
.ido-belso{width:max-content;min-width:100%;overflow:visible}
.storage-ablak{min-width:0;overflow:hidden;background:var(--surface)}
table{border-collapse:collapse;background:var(--surface);color:var(--text);font-size:12px;table-layout:auto}
th,td{border:1px solid var(--border);padding:0 5px;text-align:center;height:24px;line-height:22px;box-sizing:border-box;white-space:nowrap}
th{background:var(--surface3);font-weight:600;color:#cbd5e1}
.fix-tabla,.storage-tabla{width:max-content;min-width:0}
.fix-tabla th.hely,.fix-tabla td.hely{text-align:left;width:max-content;min-width:0;max-width:none}
.fix-tabla th.rendszam,.fix-tabla td.rendszam{text-align:right}
.fix-tabla td.rendszam{font-weight:bold}
.fix-tabla th.viszonylat,.fix-tabla td.viszonylat,
.fix-tabla th.forda,.fix-tabla td.forda,
.fix-tabla th.rendszam,.fix-tabla td.rendszam{width:1%;white-space:nowrap}
.fix-tabla th.viszonylat,.fix-tabla th.forda,.fix-tabla th.rendszam{padding-left:5px;padding-right:5px}
.fix-tabla th.viszonylat .rendez-gomb,.fix-tabla th.forda .rendez-gomb,.fix-tabla th.rendszam .rendez-gomb{margin-left:4px}
/* A kezdés/végzés oszlop szélességét is a tartalom, elsősorban a fejléc határozza meg. */
.fix-tabla th.kezdés,.fix-tabla td.kezdés,
.fix-tabla th.végzés,.fix-tabla td.végzés{width:1%;white-space:nowrap;min-width:0}
.ido-tabla{width:max-content;min-width:100%}.ido-tabla th,.ido-tabla td{width:42px;min-width:42px;max-width:42px;padding:1px;text-align:left}
.fix-tabla tbody tr,.ido-tabla tbody tr,.storage-tabla tbody tr{height:24px;min-height:24px;max-height:24px}
.fix-tabla tbody td,.ido-tabla tbody td,.storage-tabla tbody td{height:24px;min-height:24px;max-height:24px;line-height:22px;padding-top:0;padding-bottom:0;box-sizing:border-box;overflow:hidden;vertical-align:middle}
/* A három különálló táblázat fejléc- és adatsorai azonos magasságúak,
   így a bal oldali 6 oszlop, az időoszlopok és a Valós tárolás mindig
   ugyanazon vízszintes sorvonalakra essen. */
.fix-tabla thead tr,.ido-tabla thead tr,.storage-tabla thead tr{height:31px;min-height:31px;max-height:31px}
.fix-tabla thead th,.ido-tabla thead th,.storage-tabla thead th{height:31px;min-height:31px;max-height:31px;box-sizing:border-box}
/* Nézetváltás: csak egy konténerosztály változik, a sorokat nem mérjük/írjuk át egyenként. */
#fo-tabla.view-biztor .fix-tabla tbody tr[data-forras="garazs"],
#fo-tabla.view-biztor .ido-tabla tbody tr[data-forras="garazs"],
#fo-tabla.view-biztor .storage-tabla tbody tr[data-forras="garazs"],
#fo-tabla.view-garazs .fix-tabla tbody tr[data-forras="biztor"],
#fo-tabla.view-garazs .ido-tabla tbody tr[data-forras="biztor"],
#fo-tabla.view-garazs .storage-tabla tbody tr[data-forras="biztor"]{display:none}
#fo-tabla tbody tr[data-filter-match="0"]{display:none}

/* Mobilon a teljes nagy táblázat vízszintesen görgethető legyen. */
@media (max-width:900px){
    /* Mobil: valódi Excel-szerű vízszintes táblázat.
       A táblázat egyetlen scrollfelület, így ujjal közvetlenül
       az időoszlopokon lehet jobbra-balra húzni. */
    .tabla-szekcio{
        overflow:visible;
        width:100%;
        max-width:100%;
    }
    .tabla-egesz{
        display:block;
        width:100%;
        max-width:100%;
        min-width:0;
        overflow-x:auto;
        overflow-y:hidden;
        -webkit-overflow-scrolling:touch;
        overscroll-behavior-x:contain;
        touch-action:pan-x pan-y;
    }
    .fo-kozos-tabla{
        width:max-content!important;
        min-width:max-content!important;
        max-width:none!important;
    }
    .idopont-csuszkasav{width:90%;min-width:0;}
}


@media (max-width:900px){
    .fo-kozos-tabla th,.fo-kozos-tabla td{
        white-space:nowrap;
    }
    .fo-kozos-tabla .sticky-bal{
        position:sticky!important;
    }
    .fo-kozos-tabla .sticky-jobb{
        position:sticky!important;
        right:0;
    }
}
.ido-tabla .fo-kozos-tabla{border-collapse:collapse;background:var(--surface);color:var(--text);font-size:12px;table-layout:auto;width:max-content;min-width:100%;}
 .fo-kozos-tabla .col-idopont{width:42px;min-width:42px;max-width:42px}
 .fo-kozos-tabla th,.fo-kozos-tabla td{border:1px solid var(--border);padding:0 5px;text-align:center;height:24px;line-height:22px;box-sizing:border-box;white-space:nowrap}
 .fo-kozos-tabla th{background:var(--surface3);font-weight:600;color:#cbd5e1}
 .fo-kozos-tabla tbody tr{height:24px}.fo-kozos-tabla thead tr{height:31px}.fo-kozos-tabla thead th{height:31px}
 .fo-kozos-tabla .sticky-bal,.fo-kozos-tabla .sticky-jobb{position:sticky;background:var(--surface);z-index:30}
 .fo-kozos-tabla thead .sticky-bal,.fo-kozos-tabla thead .sticky-jobb{background:var(--surface3);z-index:50}
 .fo-kozos-tabla .sticky-jobb{right:0;box-shadow:-2px 0 0 var(--border)}
 .fo-kozos-tabla .sticky-bal.bal-6{box-shadow:2px 0 0 var(--border)}
 .all-view .fo-kozos-tabla tr[data-forras="biztor"] > td{background:rgba(110,168,254,.055);color:#82b4ff;font-weight:700}.all-view .fo-kozos-tabla tr[data-forras="biztor"] > td .rendszam-link{color:#82b4ff;font-weight:800}
 #fo-tabla.view-biztor .fo-kozos-tabla tbody tr[data-forras="garazs"],#fo-tabla.view-garazs .fo-kozos-tabla tbody tr[data-forras="biztor"],#fo-tabla .fo-kozos-tabla tbody tr[data-filter-match="0"]{display:none}
 .status-pill{height:20px;line-height:1}
.ido-tabla th.idopont-fejlec{font-size:0;color:transparent;padding:0}
.ido-tabla .idopont-ertek{font-size:11px;font-weight:400;background:var(--surface2);padding:4px 1px;text-align:left}
.szuro-sor th{background:var(--surface2);height:31px;padding:3px 4px}
.szuro-sor th:empty{background:var(--surface2)}
.oszlop-kereso{display:block;width:100%;min-width:0;max-width:100%;box-sizing:border-box;border:1px solid var(--border);background:var(--surface);color:var(--text);border-radius:5px;padding:1px 4px;font:inherit;font-size:10px;outline:none}
.oszlop-kereso:focus{border-color:var(--accent);box-shadow:0 0 0 2px rgba(110,168,254,.12)}
.rendez-gomb{border:1px solid var(--border);background:var(--surface2);color:var(--muted);width:21px;min-width:21px;height:21px;padding:0;margin-left:5px;border-radius:5px;cursor:pointer;font-size:11px;line-height:18px;vertical-align:middle;display:inline-flex;align-items:center;justify-content:center}
.rendez-gomb:hover{color:var(--text);border-color:var(--accent);background:var(--surface3)}.rendez-gomb.active{color:#fff;background:var(--accent2);border-color:var(--accent2)}
.fejlec-sor th{vertical-align:middle;position:relative}.fejlec-sor th:not(.idopont-fejlec){white-space:nowrap}
.status-pill{display:inline-flex;align-items:center;justify-content:center;min-width:24px;height:20px;padding:0 7px;border-radius:999px;border:1px solid transparent;font-weight:750;font-size:11px;line-height:1;box-sizing:border-box}
.status-pill.ok{color:#6ee7a8;background:rgba(54,181,116,.16);border-color:rgba(92,220,150,.34)}
.status-pill.nem{color:#ff858d;background:rgba(218,75,84,.16);border-color:rgba(255,113,124,.34)}
.status-pill.neutral{color:var(--muted);background:rgba(148,163,184,.10);border-color:rgba(148,163,184,.20)}
.fix-tabla td.ellenorzes{background:var(--surface);padding:2px 3px}
.storage-tabla th{width:max-content;min-width:0;white-space:nowrap}.storage-tabla td.tarolas{width:max-content;min-width:0;white-space:nowrap;font-weight:750;padding:0 8px;line-height:22px;background:var(--surface);border-top:1px solid var(--border);border-bottom:1px solid var(--border)}
.storage-tabla td.tarolas-ok{color:#6ee7a8;border-top-color:var(--border);border-bottom-color:var(--border)}
.storage-tabla td.tarolas-eltérés{color:#ff858d;border-top-color:var(--border);border-bottom-color:var(--border)}
.storage-tabla td.tarolas-na{color:var(--text);border-top-color:var(--border);border-bottom-color:var(--border)}
.rendszam-link{border:0;background:transparent;color:var(--accent);font:inherit;font-weight:750;cursor:pointer;padding:2px 5px;border-radius:6px;text-decoration:underline;text-decoration-color:rgba(110,168,254,.35);text-underline-offset:2px}.rendszam-link:hover{background:rgba(110,168,254,.13);color:#fff;text-decoration-color:var(--accent)}
.biztor-sor .adat-fixed{}
.all-view .fix-tabla tr[data-forras="biztor"] > td,.all-view .storage-tabla tr[data-forras="biztor"] > td{background:rgba(110,168,254,.055)}
.all-view .fix-tabla tr[data-forras="biztor"] > td,.all-view .storage-tabla tr[data-forras="biztor"] > td{color:#82b4ff;font-weight:700}
.all-view .biztor-sor > td .rendszam-link{color:#82b4ff;font-weight:800}
.map-focus{animation:mapPulse .9s ease-out}.vehicle-pin{width:22px;height:22px;border-radius:50% 50% 50% 0;transform:rotate(-45deg);border:2px solid white;box-shadow:0 1px 5px rgba(0,0,0,.45);box-sizing:border-box}.vehicle-pin::after{content:"";display:block;width:7px;height:7px;margin:5px auto 0;border-radius:50%;background:white}.vehicle-pin.green{background:#00b050}.vehicle-pin.red{background:#ff0000}.vehicle-pin.yellow{background:#ffd966}.vehicle-pin.blue{background:#4da3ff}.vehicle-pin.gray{background:#687384}
@keyframes mapPulse{0%{filter:brightness(1.8)}100%{filter:brightness(1)}}
.leaflet-popup-content{line-height:1.45}
body.light-mode{--bg:#eef2f6;--surface:#fff;--surface2:#f4f6f8;--surface3:#e7ebf0;--border:#cbd3dc;--text:#1f2937;--muted:#667085;--accent:#2f6fed;--accent2:#4f7ff5;--ok:#16a765;--bad:#df4f4f;--dark:#4b5563;--shadow:0 8px 24px rgba(15,23,42,.10);background:var(--bg);color:var(--text)}
body.light-mode .fejlec,body.light-mode .tabla-szekcio{background:var(--surface);border-color:var(--border)}
body.light-mode .cim,body.light-mode .adat b{color:var(--text)}
body.light-mode .status-pill.ok{color:#198754;background:rgba(25,135,84,.10);border-color:rgba(25,135,84,.28)}
body.light-mode .status-pill.nem{color:#c93f49;background:rgba(201,63,73,.09);border-color:rgba(201,63,73,.26)}
body.light-mode .status-pill.neutral{color:#667085;background:rgba(102,112,133,.08);border-color:rgba(102,112,133,.20)}
body.light-mode .storage-tabla td.tarolas-ok{color:#198754;border-top-color:rgba(25,135,84,.34);border-bottom-color:rgba(25,135,84,.34)}
body.light-mode .storage-tabla td.tarolas-eltérés{color:#c93f49;border-top-color:rgba(201,63,73,.34);border-bottom-color:rgba(201,63,73,.34)}
body.light-mode .storage-tabla td.tarolas-na{color:var(--text);border-top-color:var(--border);border-bottom-color:var(--border)}
body:not(.light-mode) #geozona-terkep .leaflet-tile-pane{filter:invert(90%) hue-rotate(180deg) brightness(78%) contrast(88%) saturate(70%)}
body.light-mode #geozona-terkep .leaflet-tile-pane{filter:none}
@media(max-width:900px){body{padding:10px}.fejlec{padding:13px}.fejlec-adatok{display:block}.fejlec-bal,.fejlec-jobb{flex-wrap:wrap;gap:8px 16px;margin:0}.fejlec-jobb{margin-top:7px}.fejlec-top{margin-bottom:8px}#geozona-terkep{width:94%;margin-left:auto;margin-right:auto;height:42vh;min-height:280px}.nezet-valaszto{width:100%}.nezet-gomb{flex:1 1 0;padding:9px 6px}.tabla-szekcio{padding:8px}}
@media(max-width:600px){.cim{font-size:20px}.adat{font-size:11px}#geozona-terkep{width:94%;height:38vh;min-height:250px}.idopont-csuszkasav{height:44px}.csuszka-info{font-size:10px;padding-left:5px}.rendszam-link{padding:4px 6px}}

/* Mobil: valódi, egyszerűen görgethető táblázat.
   Nincs sticky/átfedés; a Valós tárolás az időoszlopok elé kerül. */
@media(max-width:600px){
  .idopont-csuszkasav{display:none!important}
  .fo-kozos-tabla .sticky-bal,
  .fo-kozos-tabla .sticky-jobb{
    position:static!important;
    left:auto!important;
    right:auto!important;
    z-index:auto!important;
    box-shadow:none!important;
    background-clip:padding-box;
  }
  .fo-kozos-tabla .sticky-bal,
  .fo-kozos-tabla .sticky-jobb,
  .fo-kozos-tabla .bal-1,
  .fo-kozos-tabla .bal-2,
  .fo-kozos-tabla .bal-3,
  .fo-kozos-tabla .bal-4,
  .fo-kozos-tabla .bal-5,
  .fo-kozos-tabla .bal-6{
    left:auto!important;
    right:auto!important;
  }
  .tabla-egesz{
    overflow-x:auto!important;
    overflow-y:hidden;
    -webkit-overflow-scrolling:touch;
    scrollbar-width:auto;
  }
  .tabla-egesz::-webkit-scrollbar{height:6px}
  .fo-kozos-tabla{width:max-content!important}
}

/* Közvetlen, egyetlen közös tábla – a böngésző nem épít új táblát. */
.tabla-egesz{display:block;width:100%;max-width:100%;min-width:0;overflow-x:auto;overflow-y:hidden;background:var(--surface);scrollbar-width:none}
.tabla-egesz::-webkit-scrollbar{height:0}
.fo-kozos-tabla{display:table;border-collapse:separate;border-spacing:0;background:var(--surface);color:var(--text);font-size:12px;table-layout:auto;width:max-content}
.fo-kozos-tabla th,.fo-kozos-tabla td{border:1px solid var(--border);padding:0 5px;text-align:center;height:24px;line-height:22px;box-sizing:border-box;white-space:nowrap;background:var(--surface)}
.fo-kozos-tabla th{background:var(--surface3);font-weight:600;color:#cbd5e1}
.fo-kozos-tabla thead tr{height:31px}.fo-kozos-tabla thead th{height:31px}
.fo-kozos-tabla tbody tr{height:24px;content-visibility:auto;contain-intrinsic-size:24px}.fo-kozos-tabla tbody td{height:24px;line-height:22px;padding-top:0;padding-bottom:0;overflow:hidden;vertical-align:middle}
/* A 6 bal oldali oszlop mindig csak a saját tartalmának helyét foglalja. */
.fo-kozos-tabla .viszonylat,.fo-kozos-tabla .forda,.fo-kozos-tabla .rendszam,.fo-kozos-tabla .kezdés,.fo-kozos-tabla .végzés,.fo-kozos-tabla .hely{width:1px;min-width:0;white-space:nowrap}
.fo-kozos-tabla .hely{text-align:left}.fo-kozos-tabla .rendszam{text-align:right;font-weight:bold}
/* Az időoszlopok fix 42 px-es oszlopok; a rendelkezésre álló helyet ők töltik ki. */
.fo-kozos-tabla .idopont-fejlec,.fo-kozos-tabla .idopont-ertek,.fo-kozos-tabla .idopont-cella{width:42px;min-width:42px;max-width:42px;padding:1px;text-align:center}
.fo-kozos-tabla .idopont-fejlec{font-size:0;color:transparent}.fo-kozos-tabla .idopont-ertek{font-size:11px;font-weight:400;background:var(--surface2);padding:4px 1px;text-align:center}
/* A jobb szélső oszlop csak a saját tartalmának szélességét kapja. */
.fo-kozos-tabla .sticky-jobb.storage{width:1px;min-width:0;max-width:max-content;white-space:nowrap}
.fo-kozos-tabla .sticky-bal{position:sticky;z-index:30;background:var(--surface);background-clip:padding-box}
.fo-kozos-tabla thead .sticky-bal{z-index:50;background:var(--surface3)}
.fo-kozos-tabla .sticky-jobb{position:sticky;right:0;z-index:30;background:var(--surface);background-clip:padding-box;box-shadow:-2px 0 0 var(--border)}
.fo-kozos-tabla thead .sticky-jobb{z-index:50;background:var(--surface3)}
.fo-kozos-tabla .bal-1{left:0}.fo-kozos-tabla .bal-2{left:var(--bal-2,0px)}.fo-kozos-tabla .bal-3{left:var(--bal-3,0px)}.fo-kozos-tabla .bal-4{left:var(--bal-4,0px)}.fo-kozos-tabla .bal-5{left:var(--bal-5,0px)}.fo-kozos-tabla .bal-6{left:var(--bal-6,0px)}
/* Ízléses, folytonos elválasztó a hat fix oszlop között. */
/* A bal oldali cellák saját, opák háttere takarja az időcellákat.
   Nincs külön rárajzolt fekete fedőréteg: a normál cellaszegélyek maradnak láthatók. */
.fo-kozos-tabla .sticky-bal{isolation:auto;background:var(--surface);}
.fo-kozos-tabla thead .sticky-bal{background:var(--surface3);}
.fo-kozos-tabla .szuro-sor .sticky-bal{background:var(--surface2);}
/* Valós tárolás formázása a közös táblában is. */
.fo-kozos-tabla td.tarolas{font-weight:750;padding:0 8px;line-height:22px;background:var(--surface);white-space:nowrap}
.fo-kozos-tabla td.tarolas-ok{color:#6ee7a8}
.fo-kozos-tabla td.tarolas-eltérés{color:#ff858d}
.fo-kozos-tabla td.tarolas-na{color:var(--text)}
.fo-kozos-tabla td.tarolas-potlas{color:#4da3ff !important;font-weight:800}
.all-view .fo-kozos-tabla tr[data-forras="biztor"]>td{background:rgba(110,168,254,.055);color:#82b4ff;font-weight:700}
.all-view .fo-kozos-tabla tr[data-forras="biztor"]>td .rendszam-link{color:var(--accent);font-weight:800}
/* A tárolási eredmény színe minden nézetben elsőbbséget kap. */
.all-view .fo-kozos-tabla tr[data-forras="biztor"]>td.tarolas-ok{color:#6ee7a8}
.all-view .fo-kozos-tabla tr[data-forras="biztor"]>td.tarolas-eltérés{color:#ff858d}
.all-view .fo-kozos-tabla tr[data-forras="biztor"]>td.tarolas-na{color:var(--text)}
.all-view .fo-kozos-tabla tr[data-forras="biztor"]>td.tarolas-potlas{color:#4da3ff !important}
#fo-tabla.view-biztor .fo-kozos-tabla tbody tr[data-forras="garazs"],#fo-tabla.view-garazs .fo-kozos-tabla tbody tr[data-forras="biztor"],#fo-tabla .fo-kozos-tabla tbody tr[data-filter-match="0"]{display:none}
/* =========================================================
   VÉGLEGES KÖZÖS TÁBLA MÉRETEZÉS / STICKY RÉTEG
   ========================================================= */
.fo-kozos-tabla{
  width:max-content;
  table-layout:auto;
}
/* A fix oszlopok szélességét nem rögzítjük. A böngésző természetes
   táblázati méretezése dönti el: fejléc + rendezőikon + tartalom. */
.fo-kozos-tabla .viszonylat,
.fo-kozos-tabla .forda,
.fo-kozos-tabla .kezdés,
.fo-kozos-tabla .végzés,
.fo-kozos-tabla .hely,
.fo-kozos-tabla .rendszam,
.fo-kozos-tabla .sticky-jobb.storage{
  width:auto;
  min-width:0;
  max-width:none;
  white-space:nowrap;
}
.fo-kozos-tabla .sticky-bal{
  position:sticky;
  z-index:100;
  background-color:var(--surface) !important;
  background-image:none !important;
  background-clip:border-box;
}
.fo-kozos-tabla thead .sticky-bal{
  z-index:110;
  background-color:var(--surface3) !important;
}
.fo-kozos-tabla .sticky-jobb{
  position:sticky;
  right:0;
  z-index:100;
  background-color:var(--surface) !important;
  background-image:none !important;
  background-clip:border-box;
  box-shadow:-2px 0 0 var(--border);
}
.fo-kozos-tabla thead .sticky-jobb{
  z-index:110;
  background-color:var(--surface3) !important;
}
/* Az Összes nézet kék kiemelése csak a szöveget érintse;
   ne legyen áttetsző háttér, mert azon át az időcellák látszanának. */
.all-view .fo-kozos-tabla tr[data-forras="biztor"]>td{
  background-color:var(--surface) !important;
  background-image:none !important;
  color:#82b4ff;
  font-weight:700;
}
.all-view .fo-kozos-tabla tr[data-forras="biztor"]>td.sticky-bal,
.all-view .fo-kozos-tabla tr[data-forras="biztor"]>td.sticky-jobb{
  background-color:var(--surface) !important;
}
.all-view .fo-kozos-tabla tr[data-forras="biztor"]>td.tarolas-ok{color:#6ee7a8}
.all-view .fo-kozos-tabla tr[data-forras="biztor"]>td.tarolas-eltérés{color:#ff858d}
.all-view .fo-kozos-tabla tr[data-forras="biztor"]>td.tarolas-na{color:var(--text)}
.all-view .fo-kozos-tabla tr[data-forras="biztor"]>td.tarolas-potlas{color:#4da3ff !important}
.fo-kozos-tabla td.tarolas{
  font-weight:750;
  white-space:nowrap;
}
.fo-kozos-tabla td.tarolas-na{color:var(--text)}
.fo-kozos-tabla td.tarolas-potlas{color:#4da3ff !important;font-weight:800}
/* A sticky cellák szélei között a border-collapse miatt maradhat 1px-es
   festési rés. Ezt egy enyhén túlnyúló, teljesen opák háttérréteg takarja,
   így az időcellák sem a cellaközben, sem a szegélynél nem látszanak át. */
/* =========================================================
   V6 – természetes fix oszlopok + mobil jobb oldali tárolás
   ========================================================= */
/* A keresőmezők ne növeljék meg a fejlécoszlop természetes szélességét.
   A cellán belül lebegnek, ezért a fejléc + tartalom határozza meg az oszlopot. */
.fo-kozos-tabla .szuro-sor th{position:relative;overflow:visible}
.fo-kozos-tabla .szuro-sor .oszlop-kereso{
  position:absolute;
  left:3px;right:3px;top:2px;height:18px;
  width:auto;min-width:0;max-width:none;
  box-sizing:border-box;
}
/* A hat bal oldali és a jobb oldali oszlopnak nincs mesterséges szélessége. */
.fo-kozos-tabla .viszonylat,
.fo-kozos-tabla .forda,
.fo-kozos-tabla .kezdés,
.fo-kozos-tabla .végzés,
.fo-kozos-tabla .hely,
.fo-kozos-tabla .rendszam,
.fo-kozos-tabla .sticky-jobb.storage{
  width:max-content!important;
  min-width:max-content!important;
  max-width:max-content!important;
}
/* A rendszám jobb oldalán legyen egy jól látható függőleges elválasztó. */
.fo-kozos-tabla .rendszam.sticky-bal{
  box-shadow:inset -1px 0 var(--border),2px 0 0 var(--border)!important;
}
/* A bal 6 oszlop sorai között is legyen ugyanaz a finom vízszintes szegély,
   mint a többi táblaterületen. */
.fo-kozos-tabla .sticky-bal{
  border-bottom:1px solid var(--border)!important;
}
/* =========================================================
   V6 – természetes fix oszlopok + mobil jobb oldali tárolás
   ========================================================= */
.fo-kozos-tabla .szuro-sor th{position:relative;overflow:visible}
.fo-kozos-tabla .szuro-sor .oszlop-kereso{
  position:absolute;
  left:3px;right:3px;top:2px;height:18px;
  width:auto;min-width:0;max-width:none;
  box-sizing:border-box;
}
.fo-kozos-tabla .viszonylat,
.fo-kozos-tabla .forda,
.fo-kozos-tabla .kezdés,
.fo-kozos-tabla .végzés,
.fo-kozos-tabla .hely,
.fo-kozos-tabla .rendszam,
.fo-kozos-tabla .sticky-jobb.storage{
  width:max-content!important;
  min-width:max-content!important;
  max-width:max-content!important;
}
.fo-kozos-tabla .rendszam.sticky-bal{
  box-shadow:inset -1px 0 rgba(255,255,255,.16),2px 0 0 var(--border)!important;
}
.fo-kozos-tabla .sticky-bal{
  border-bottom:1px solid var(--border)!important;
}
/* A szűrősor is ugyanúgy sticky, mint a fejléc és az adatcellák.
   A korábbi position:relative felülírta a sticky-bal működését, ezért
   a keresősáv a 2. idősort együtt követte. */
.fo-kozos-tabla .szuro-sor th.sticky-bal{
  position:sticky!important;
  z-index:40!important;
  background:var(--surface2)!important;
  background-clip:padding-box;
}
.fo-kozos-tabla .szuro-sor th.sticky-jobb{
  position:sticky!important;
  right:0;
  z-index:40!important;
  background:var(--surface2)!important;
  background-clip:padding-box;
}
/* Mobilon is a bal 6 oszlop maradjon fix; a Valós tárolás a jobb oldalon
   továbbra is a táblával együtt görgethető. */

/* Végső sticky-javítás: a collapse táblamodell néhány böngészőben
   1–2 px-rel elmozdíthatja a sticky cellákat vízszintes scrollnál.
   Separate + 0 spacing mellett a hat bal oszlop stabilan a helyén marad. */
.fo-kozos-tabla{
  border-collapse:separate!important;
  border-spacing:0!important;
}
.fo-kozos-tabla .sticky-bal{
  left:var(--sticky-left,0px);
}
.fo-kozos-tabla .bal-1{left:0!important}
.fo-kozos-tabla .bal-2{left:var(--bal-2,0px)!important}
.fo-kozos-tabla .bal-3{left:var(--bal-3,0px)!important}
.fo-kozos-tabla .bal-4{left:var(--bal-4,0px)!important}
.fo-kozos-tabla .bal-5{left:var(--bal-5,0px)!important}
.fo-kozos-tabla .bal-6{left:var(--bal-6,0px)!important}

/* Világos módban a tárolási színek legyenek kevésbé harsányak, de jól
   olvashatók a világos háttéren. */
body.light-mode .fo-kozos-tabla td.tarolas-ok{color:#167347!important}
body.light-mode .fo-kozos-tabla td.tarolas-eltérés{color:#ad3540!important}
body.light-mode .all-view .fo-kozos-tabla tr[data-forras="biztor"]>td.tarolas-ok{color:#167347!important}
body.light-mode .all-view .fo-kozos-tabla tr[data-forras="biztor"]>td.tarolas-eltérés{color:#ad3540!important}

/* Összes nézetben a sor kékre emelése ne színezze át a kattintható
   rendszámot; annak saját link-színe maradjon. */
.all-view .fo-kozos-tabla tr[data-forras="biztor"]>td .rendszam-link{
  color:var(--accent)!important;
}


/* Végső mobil felülírás: a teljes táblázat normálisan, vízszintesen görgethető.
   A fejléc- és szűrősor sem marad sticky mobilon. */
@media(max-width:600px){
  .fo-kozos-tabla .sticky-bal,
  .fo-kozos-tabla .sticky-jobb,
  .fo-kozos-tabla .szuro-sor th,
  .fo-kozos-tabla .szuro-sor th.sticky-bal,
  .fo-kozos-tabla .szuro-sor th.sticky-jobb{
    position:static!important;
    left:auto!important;
    right:auto!important;
    z-index:auto!important;
    box-shadow:none!important;
  }
}
</style>
<style>
/* Easter egg – normál állapotban láthatatlan, kijelölve előjön. */
.rejtett-poen{
  position:fixed;
  top:2px;
  left:50%;
  transform:translateX(-50%);
  z-index:9999;
  color:transparent;
  background:transparent;
  font-size:10px;
  line-height:12px;
  white-space:nowrap;
  user-select:text;
  -webkit-user-select:text;
  cursor:text;
}
.rejtett-poen::selection{
  color:#fff;
  background:#3b82f6;
}
.rejtett-poen::-moz-selection{
  color:#fff;
  background:#3b82f6;
}

/* V10 – finomhangolás */
/* A keresősáv pontosan kitölti a szűrőcellát, de nem lóg ki belőle. */
.fo-kozos-tabla .szuro-sor .oszlop-kereso{
  top:3px;
  bottom:3px;
  height:auto;
  padding-top:0;
  padding-bottom:0;
}
/* A rendszám gombja nem növelheti meg a sor magasságát. */
.fo-kozos-tabla .rendszam-link{
  display:inline-flex;
  align-items:center;
  justify-content:center;
  height:20px;
  min-height:20px;
  max-height:20px;
  line-height:18px;
  box-sizing:border-box;
  vertical-align:middle;
  margin:0;
  padding:0 5px;
}
/* A Viszonylat és Forda oszlop szélességét a fejléc + rendezőikon
   határozza meg. A tényleges szélességet a JS a kész fejlécből méri,
   így a hosszabb adatcellák nem tudják széthúzni ezeket az oszlopokat. */
.fo-kozos-tabla th.viszonylat,
.fo-kozos-tabla th.forda,
.fo-kozos-tabla td.viszonylat,
.fo-kozos-tabla td.forda{
  white-space:nowrap;
}
.fo-kozos-tabla td.viszonylat,
.fo-kozos-tabla td.forda{
  overflow:hidden;
  text-overflow:clip;
}
/* Minden bal oldali fix oszlopon legyen saját, folytonos jobb oldali
   elválasztószegély. A box-shadow azért kell, hogy a sticky rétegben
   se takarja el a szomszédos cella. */
.fo-kozos-tabla .sticky-bal{
  box-shadow:inset -1px 0 var(--border);
}
/* A Kezdés és Végzés között legyen határozott, de finom függőleges szegély. */
.fo-kozos-tabla th.kezdés,
.fo-kozos-tabla td.kezdés{
  border-right:1px solid var(--border)!important;
}
.fo-kozos-tabla th.végzés,
.fo-kozos-tabla td.végzés{
  border-left:1px solid var(--border)!important;
}
</style>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" crossorigin="">
</head>
<body>
<span class="rejtett-poen">de ki az a Korporéjsön?</span>
<div class="fejlec">
  <div class="fejlec-top">
    <div class="cim" id="oldal-cim" role="button" tabindex="0" title="Oldal frissítése"><b>ArrivaBus hidegtárolás</b></div>
    <button id="theme-toggle" class="theme-toggle" type="button" title="Sötét / világos mód">☀ Sötét mód</button>
  </div>
  <div class="fejlec-adatok riport-fejlec-adatok">
    <div class="fejlec-bal">
      <div class="adat"><b>Dátum:</b> """ + escape(futas_datum) + """</div>
      <div class="adat"><b>Naptípus:</b> """ + (
          escape(str(talalt_munkalap))
          if str(talalt_munkalap).strip() == str(garazs_talalt_munkalap).strip()
          else escape(str(talalt_munkalap)) + " / " + escape(str(garazs_talalt_munkalap))
      ) + """</div>
      <div class="adat"><b>Utolsó lekérdezés:</b> """ + escape(str(idopontok[-1] if idopontok else "-")) + """</div>
    </div>
    <div class="fejlec-jobb">
      <div class="adat"><b>Riport készült:</b> """ + escape(str(hidegtarolas_riport.get("keszult", "-"))) + """</div>
      <div class="adat"><b>Exportált fordák:</b> """ + str(hidegtarolas_riport.get("vizsgalt_fordak", 0) if hidegtarolas_riport.get("kesz", False) else 0) + """</div>
    </div>
  </div>
</div>
<div id="geozona-terkep"></div>
<div class="nezet-valaszto" role="tablist" aria-label="Megjelenítés">
  <button class="nezet-gomb" data-nezet="mindketto" type="button">Összes <span class="online-szam">""" + str(osszes_online) + "/" + str(osszes_osszes) + """</span></button>
  <button class="nezet-gomb" data-nezet="biztor" type="button">Végállomás <span class="online-szam">""" + str(biz_online) + "/" + str(biz_osszes) + """</span></button>
  <button class="nezet-gomb" data-nezet="garazs" type="button">Garázs <span class="online-szam">""" + str(garazs_online) + "/" + str(garazs_osszes) + """</span></button>
</div>
<div id="panel-adatok" class="nezet-panel">
<div class="tabla-szekcio">
  <div class="idopont-csuszkasav" id="fo-csuszkasav">
    <div class="csuszka-info"><strong id="aktiv-sorok-szoveg">Idővonal&nbsp;</strong></div>
    <input type="range" id="fo-idopont-csuszka" min="0" max="0" value="0" step="1" aria-label="Időpont görgetése">
    <div></div>
  </div>
  <div class="tabla-egesz" id="fo-tabla">
    <table class="fo-kozos-tabla">
      <thead>
        <tr class="fejlec-sor">
          <th class="viszonylat sticky-bal bal-1">Viszonylat <button class="rendez-gomb" type="button" data-sort-col="0">↕</button></th>
          <th class="forda sticky-bal bal-2">Forda <button class="rendez-gomb" type="button" data-sort-col="1">↕</button></th>
          <th class="kezdés sticky-bal bal-3">Kezdés <button class="rendez-gomb" type="button" data-sort-col="2" data-sort-type="time">↕</button></th>
          <th class="végzés sticky-bal bal-4">Végzés <button class="rendez-gomb" type="button" data-sort-col="3" data-sort-type="time">↕</button></th>
          <th class="hely sticky-bal bal-5">Hely <button class="rendez-gomb" type="button" data-sort-col="4">↕</button></th>
          <th class="rendszam sticky-bal bal-6">Rendszám <button class="rendez-gomb" type="button" data-sort-col="5">↕</button></th>
""")
        
    for time_index, idopont in enumerate(idopontok):
        html.append(f'<th class="idopont-fejlec" data-time-index="{time_index}"></th>')
    html.append('<th class="sticky-jobb storage">Valós tárolás <button class="rendez-gomb" type="button" data-sort-col="storage">↕</button></th></tr>')
    html.append('<tr class="szuro-sor">')
    html.append('<th class="sticky-bal bal-1"><input class="oszlop-kereso" data-col="0" placeholder="Keresés…" aria-label="Viszonylat keresése"></th>')
    html.append('<th class="sticky-bal bal-2"><input class="oszlop-kereso" data-col="1" placeholder="Keresés…" aria-label="Forda keresése"></th>')
    html.append('<th class="sticky-bal bal-3"></th><th class="sticky-bal bal-4"></th>')
    html.append('<th class="sticky-bal bal-5"><input class="oszlop-kereso" data-col="4" placeholder="Keresés…" aria-label="Hely keresése"></th>')
    html.append('<th class="sticky-bal bal-6"><input class="oszlop-kereso" data-col="5" placeholder="Keresés…" aria-label="Rendszám keresése"></th>')
    for time_index, idopont in enumerate(idopontok):
        html.append(f'<th class="idopont-ertek" data-time-index="{time_index}">{escape(idopont)}</th>')
    html.append('<th class="sticky-jobb storage"><input class="oszlop-kereso" data-col="storage" placeholder="Keresés…" aria-label="Valós tárolás keresése"></th></tr></thead><tbody id="fix-tbody-common">')

    osszes_sor = []
    osszes_sor.extend({**v, "forrás": "biztor", "kulcs": k} for k, v in sorok.items())
    osszes_sor.extend({**v, "forrás": "garazs", "kulcs": k} for k, v in garazs_sorok.items())
    osszes_sor.sort(key=lambda x: (x.get("kezdés", ""), 0 if x.get("forrás") == "biztor" else 1, x.get("viszonylat", ""), x.get("forda", "")))

    for row_id, sor in enumerate(osszes_sor):
        forras = sor.get("forrás", "biztor")
        sor_class = "biztor-sor" if forras == "biztor" else "garazs-sor"
        html.append(f'<tr class="{sor_class}" data-row-id="{row_id}" data-forras="{forras}">')
        html.append(f'<td class="viszonylat sticky-bal bal-1">{escape(sor["viszonylat"])}</td>')
        html.append(f'<td class="forda sticky-bal bal-2">{escape(sor["forda"])}</td>')
        html.append(f'<td class="kezdés sticky-bal bal-3">{escape(sor["kezdés"])}</td>')
        html.append(f'<td class="végzés sticky-bal bal-4">{escape(sor["végzés"])}</td>')
        html.append(f'<td class="hely sticky-bal bal-5">{escape(sor["hely"])}</td>')
        rs = str(sor.get("rendszám", "")).strip()
        rs_html = f'<button type="button" class="rendszam-link" data-rendszam="{escape(rs)}" title="Jármű megjelenítése a térképen">{escape(rs)}</button>' if rs else ""
        html.append(f'<td class="rendszam sticky-bal bal-6">{rs_html}</td>')

        for time_index, idopont in enumerate(idopontok):
            eredmeny = sor.get("ellenőrzés", {}).get(idopont, "-")
            megj = {"OK":"I","NEM":"N","NINCS ADAT":"?"}.get(eredmeny,"-")
            osztaly = "neutral"
            try:
                t=datetime.strptime(idopont,"%H:%M"); k=datetime.strptime(sor["kezdés"],"%H:%M"); v=datetime.strptime(sor["végzés"],"%H:%M")
                if k <= t <= v:
                    osztaly = "ok" if eredmeny == "OK" else "nem" if eredmeny == "NEM" else "neutral"
                elif k - timedelta(minutes=15) <= t < k or v < t <= v + timedelta(minutes=15):
                    osztaly = "neutral"; megj = "-" if eredmeny not in ("OK","NEM") else megj
                else:
                    megj = "-"
            except (ValueError,TypeError):
                osztaly = "ok" if eredmeny == "OK" else "nem" if eredmeny == "NEM" else "neutral"
            html.append(f'<td class="idopont-cella" data-time-index="{time_index}"><span class="status-pill {osztaly}">{escape(megj)}</span></td>')

        riport_map = riport_eredmenyek if forras == "biztor" else garazs_riport_eredmenyek
        rr = riport_map.get(sor["kulcs"], {})
        eredmeny_riport = str(rr.get("eredmény", "")).strip()
        tarolas = str(rr.get("tárolás helye", "")).strip()
        if not rr or not eredmeny_riport:
            tarolas = "n.a"
            rcls = "tarolas-na"
        elif eredmeny_riport == "Pótlásban vesz részt":
            tarolas = "---"
            rcls = "tarolas-potlas"
        elif tarolas in ("Nincs adat", "-"):
            # Az ELTÉRÉS lehet valódi ellenőrzési eredmény, de ha
            # nincs hozzá tényleges tárolási hely, az n.a nem lehet
            # piros: nincs megjeleníthető helyadat.
            tarolas = "n.a"
            rcls = "tarolas-na"
        elif eredmeny_riport == "RENDBEN TÁROLT":
            rcls = "tarolas-ok"
        elif eredmeny_riport == "ELTÉRÉS TÖRTÉNT":
            rcls = "tarolas-eltérés"
        else:
            rcls = "tarolas-na"
        html.append(f'<td class="sticky-jobb storage tarolas {rcls}">{escape(tarolas)}</td></tr>')

    html.append('</tbody></table></div></div></div>')

    html.append("""
<script>
(function(){
  const fo=document.getElementById('fo-tabla');
  const slider=document.getElementById('fo-idopont-csuszka');
  const sliderBar=document.getElementById('fo-csuszkasav');
  const table=fo?.querySelector('.fo-kozos-tabla');
  const tbody=table?.querySelector('tbody');
  const buttons=document.querySelectorAll('.nezet-gomb');
  if(!fo||!slider||!table||!tbody)return;
  let currentView='biztor',sortState={col:null,dir:1};


  function mobilTablaSorrend(){
    const mobil=window.matchMedia('(max-width:600px)').matches;
    const sorok=Array.from(table.querySelectorAll('tr'));
    sorok.forEach(tr=>{
      const storage=tr.querySelector('.storage');
      if(!storage)return;
      if(mobil){
        const firstTime=tr.querySelector('.idopont-fejlec,.idopont-ertek,.idopont-cella');
        if(firstTime && storage.nextElementSibling!==firstTime){
          tr.insertBefore(storage,firstTime);
        }
      }else{
        if(storage.parentElement && storage !== tr.lastElementChild){
          tr.appendChild(storage);
        }
      }
    });
  }
  mobilTablaSorrend();
  const rowList=Array.from(tbody.children);
  const filterInputs=Array.from(document.querySelectorAll('.oszlop-kereso[data-col]'));
  const sortButtons=Array.from(document.querySelectorAll('.rendez-gomb'));
  function rows(){return rowList;}

  // A táblázat természetes szélességét a böngésző számolja ki.
  // Nem írjuk végig minden sor celláinak width/left értékeit, mert ez
  // több ezer DOM-műveletet és felesleges újratördelést okozott.
  function sticky(){
    const head=table.querySelector('thead tr:first-child');
    if(!head)return;
    const heads=head.children;
    let left=0;
    for(let i=0;i<6;i++){
      const w=heads[i]?.getBoundingClientRect().width||0;
      const px=left.toFixed(3)+'px';
      document.documentElement.style.setProperty('--bal-'+(i+1),px);
      left+=w;
    }
  }
  function layoutScroll(){
    const max=Math.max(0,fo.scrollWidth-fo.clientWidth);
    slider.max=String(max);
    if (fo.scrollLeft > max) fo.scrollLeft=max;
  }
  function layout(){
    const mobil=window.matchMedia('(max-width:600px)').matches;
    const current=Math.max(0,fo.scrollLeft||0);
    sticky();
    const max=Math.max(0,fo.scrollWidth-fo.clientWidth);
    slider.max=String(max);
    if(mobil){
      fo.scrollLeft=Math.min(max,current);
      slider.value=String(fo.scrollLeft);
    }else{
      slider.value=String(max);
      fo.scrollLeft=max;
    }
  }
  function view(v){
    currentView=v;
    buttons.forEach(b=>b.classList.toggle('active',b.dataset.nezet===v));
    fo.classList.remove('view-biztor','view-garazs','view-mindketto');
    fo.classList.add('view-'+v);fo.classList.toggle('all-view',v==='mindketto');
    requestAnimationFrame(()=>{sticky();layoutScroll();});
  }
  function applyFilters(){
    rowList.forEach(r=>{
      let ok=true;
      for(const i of filterInputs){
        const q=i.value.trim().toLocaleLowerCase('hu-HU');
        if(!q) continue;
        const c=i.dataset.col==='storage'?r.querySelector('.sticky-jobb'):r.children[+i.dataset.col];
        if(!(c?.textContent||'').toLocaleLowerCase('hu-HU').includes(q)){ok=false;break;}
      }
      r.dataset.filterMatch=ok?'1':'0';
    });
    requestAnimationFrame(()=>{sticky();layoutScroll();});
  }
  function filters(){
    applyFilters();
  }
  function val(r,c){const x=c==='storage'?r.querySelector('.sticky-jobb'):r.children[+c];return x?.textContent.trim()||'';}
  function cmp(a,b,t){
    if(t==='time'){
      const ma=/^(\\d{1,2}):(\\d{2})$/.exec(a),mb=/^(\\d{1,2}):(\\d{2})$/.exec(b);
      if(ma&&mb)return(+ma[1]*60+ +ma[2])-(+mb[1]*60+ +mb[2]);
    }
    return a.localeCompare(b,'hu',{numeric:true,sensitivity:'base'});
  }
  function sort(btn){
    const c=btn.dataset.sortCol,t=btn.dataset.sortType||'';
    if(sortState.col===c)sortState.dir*=-1;else{sortState.col=c;sortState.dir=1;}
    sortButtons.forEach(b=>{b.classList.remove('active');b.textContent='↕'});
    btn.classList.add('active');btn.textContent=sortState.dir===1?'↑':'↓';
    const frag=document.createDocumentFragment();
    rowList.sort((a,b)=>cmp(val(a,c),val(b,c),t)*sortState.dir).forEach(r=>frag.appendChild(r));
    tbody.appendChild(frag);
    requestAnimationFrame(()=>{sticky();layoutScroll();});
  }
  let scrollFrame=0;
  slider.addEventListener('input',()=>{
    fo.scrollLeft=Math.min(fo.scrollWidth-fo.clientWidth,Math.max(0,+slider.value||0));
  });
  fo.addEventListener('scroll',()=>{
    if(scrollFrame)return;
    scrollFrame=requestAnimationFrame(()=>{
      slider.value=String(Math.round(fo.scrollLeft));
      scrollFrame=0;
    });
  },{passive:true});
  buttons.forEach(b=>b.addEventListener('click',()=>view(b.dataset.nezet)));
  sortButtons.forEach(b=>b.addEventListener('click',()=>sort(b)));
  filterInputs.forEach(i=>i.addEventListener('input',filters));
  window.addEventListener('resize',()=>{
    const oldScroll=fo.scrollLeft;
    requestAnimationFrame(()=>{
      mobilTablaSorrend();
      layout();
      if(window.matchMedia('(max-width:600px)').matches){
        const max=Math.max(0,fo.scrollWidth-fo.clientWidth);
        fo.scrollLeft=Math.min(max,Math.max(0,oldScroll||0));
        slider.value=String(fo.scrollLeft);
      }
    });
  });
  rowList.forEach(r=>r.dataset.filterMatch='1');
  view('biztor');layout();
})();
(function(){
  const btn=document.getElementById('theme-toggle');
  if(!btn) return;
  function applyTheme(light, save=true){
    document.body.classList.toggle('light-mode',light);
    btn.textContent=light?'☾ Sötét mód':'☀ Normál mód';
    if(save){
      try{localStorage.setItem('futar-theme', light ? 'light' : 'dark');}catch(e){}
    }
    window.dispatchEvent(new Event('resize'));
  }
  let savedTheme=null;
  try{savedTheme=localStorage.getItem('futar-theme');}catch(e){}
  applyTheme(savedTheme==='light', false);
  btn.addEventListener('click',()=>applyTheme(!document.body.classList.contains('light-mode'), true));
})();

// Az oldal címe kattintható: kézzel is azonnal frissíthető.
(function(){
  const cim=document.getElementById('oldal-cim');
  if(!cim) return;
  const frissit=()=>window.location.reload();
  cim.addEventListener('click',frissit);
  cim.addEventListener('keydown',e=>{
    if(e.key==='Enter'||e.key===' '){
      e.preventDefault();
      frissit();
    }
  });
})();

// Automatikus oldalfrissítés 5 percenként.
setInterval(()=>window.location.reload(),5*60*1000);
</script>

""")
    html.append(r'''
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>

<script>

const terkepJarmuvek = __JARMUVEK__;

const terkepZonak = __ZONAK__;



const map = L.map(
    "geozona-terkep"
).setView(
    [47.4979, 19.0402],
    11
);

// OSM Standard, a sötét/világos megjelenítést a dashboard CSS kapcsolja.

L.tileLayer(
    "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    {
        maxZoom: 20,
        attribution: "&copy; OpenStreetMap contributors"
    }
).addTo(map);


const terkepElemek = [];
const jarmuMarkerek = {};
const TERKEP_MAX_ZOOM = 14;


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
    else if (statusz === "PÓTLÁS") {
        osztaly = "blue";
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

    );

    marker.__forras = String(jarmu.forras || "biztor").trim() || "biztor";


    let statuszSzoveg = "Nincs értékelés";

    if (jarmu.statusz === "OK") {
        statuszSzoveg =
            '<span style="color:#00a040;font-weight:bold;">OK</span>';
    }
    else if (jarmu.statusz === "NEM") {
        statuszSzoveg =
            '<span style="color:#e00000;font-weight:bold;">ELTÉRÉS</span>';
    }
    else if (jarmu.statusz === "PÓTLÁS") {
        statuszSzoveg =
            '<span style="color:#4da3ff;font-weight:bold;">Pótlásban vesz részt</span>';
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


    const rendszamKulcs = String(jarmu.rendszam || "").trim().toUpperCase();
    if (rendszamKulcs) {
        jarmuMarkerek[rendszamKulcs] = marker;
    }

    jarmuMarkerek["__lista__"] = jarmuMarkerek["__lista__"] || [];
    jarmuMarkerek["__lista__"].push(marker);

});

function frissitTerkepNezet(view) {
    const lista = jarmuMarkerek["__lista__"] || [];
    lista.forEach(function(marker){
        if (map.hasLayer(marker)) map.removeLayer(marker);
    });
    const latszo = lista.filter(function(marker){
        return view === "mindketto" || marker.__forras === view;
    });
    latszo.forEach(function(marker){ marker.addTo(map); });
    if (latszo.length) {
        const bounds = L.featureGroup(latszo).getBounds();
        if (bounds.isValid()) map.fitBounds(bounds.pad(0.08), {maxZoom: TERKEP_MAX_ZOOM});
    }
}

document.querySelectorAll(".nezet-gomb").forEach(function(btn){
    btn.addEventListener("click", function(){
        frissitTerkepNezet(this.dataset.nezet);
    });
});

function fokuszJarmure(rendszam) {
    const kulcs = String(rendszam || "").trim().toUpperCase();
    const marker = jarmuMarkerek[kulcs];
    if (!marker) return;
    const pos = marker.getLatLng();
    map.flyTo(pos, Math.min(TERKEP_MAX_ZOOM, Math.max(map.getZoom(), 11)), {duration: 0.7});
    setTimeout(function(){
        marker.openPopup();
        const el = marker.getElement();
        if (el) {
            el.classList.remove("map-focus");
            void el.offsetWidth;
            el.classList.add("map-focus");
        }
    }, 700);
}

document.querySelectorAll(".rendszam-link").forEach(function(btn){
    btn.addEventListener("click", function(){
        window.scrollTo({top: 0, behavior: "smooth"});
        fokuszJarmure(this.dataset.rendszam);
    });
});


// ---------------------------------------------------------
// TÉRKÉP NÉZET BEÁLLÍTÁSA
// ---------------------------------------------------------

frissitTerkepNezet("biztor");

const garazsAblak = document.getElementById("garazs-idopont-ablak");
const garazsBelso = document.getElementById("garazs-idopont-belső");
const garazsCsuszka = document.getElementById("garazs-idopont-csuszka");
function frissitGarazsCsuszkat() {
    if (!garazsAblak || !garazsBelso || !garazsCsuszka) return;
    const w = window.innerWidth;
    let timeWidth;
    if (w <= 600) timeWidth = Math.max(360, Math.round(w * 0.88));
    else if (w <= 900) timeWidth = Math.max(480, Math.round(w * 0.70));
    else timeWidth = Math.min(1200, Math.max(560, Math.round(w * 0.62)));
    document.documentElement.style.setProperty("--time-window-width", timeWidth + "px");
    const maxScroll = Math.max(0, garazsBelso.scrollWidth - garazsAblak.clientWidth);
    garazsCsuszka.value = "1000";
    garazsCsuszka.oninput = function() { garazsAblak.scrollLeft = maxScroll * (Number(this.value) / 1000); };
    garazsAblak.scrollLeft = maxScroll;
}
window.addEventListener("resize", frissitGarazsCsuszkat);
window.addEventListener("load", frissitGarazsCsuszkat);

</script>

</body>

</html>





'''.replace("__JARMUVEK__", json.dumps(terkep_jarmuvek_lista, ensure_ascii=False)).replace("__ZONAK__", json.dumps(terkep_zonak, ensure_ascii=False)))


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

