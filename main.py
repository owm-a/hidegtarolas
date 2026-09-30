# ============================================================
# HELYSZÍN ELLENŐRZÉS
# GPS + IDŐ → OTT VAN-E A FORDA A HELYSZÍNEN?
# ============================================================

print()
print("=== HELYSZÍN ELLENŐRZÉS ===")


# ============================================================
# 1. Aktuális budapesti idő
# ============================================================

ellenorzes_idopont = datetime.now(
    ZoneInfo("Europe/Budapest")
).strftime("%H:%M:%S")

print(
    "Helyszínellenőrzés időpontja:",
    ellenorzes_idopont
)


# ============================================================
# 2. Eddigi pozíciótörténet
# ============================================================

poziciok = napi_adatok.get(
    "pozicio_tortenet",
    []
)


# ============================================================
# 3. Minden forda ellenőrzése
# ============================================================

ellenorzesek = []


for forda_kulcs, adat in forda_rendszamok.items():

    viszonylat = adat.get(
        "viszonylat",
        ""
    )

    forda = adat.get(
        "forda",
        ""
    )

    rendszam = adat.get(
        "rendszám",
        ""
    )

    hely = adat.get(
        "hely",
        ""
    )

    helyszin_kulcs = adat.get(
        "helyszín",
        ""
    )

    kezdés = str(
        adat.get(
            "kezdés",
            ""
        )
    ).strip()

    végzés = str(
        adat.get(
            "végzés",
            ""
        )
    ).strip()


    # ========================================================
    # Helyszín-konfiguráció ellenőrzése
    # ========================================================

    if not helyszin_kulcs:

        ellenorzesek.append({
            "viszonylat": viszonylat,
            "forda": forda,
            "rendszám": rendszam,
            "hely": hely,
            "helyszín": "",
            "ellenőrzés": "NINCS HELYSZÍN"
        })

        continue


    if helyszin_kulcs not in HELYSZINEK:

        ellenorzesek.append({
            "viszonylat": viszonylat,
            "forda": forda,
            "rendszám": rendszam,
            "hely": hely,
            "helyszín": helyszin_kulcs,
            "ellenőrzés": "HIBÁS HELYSZÍN"
        })

        continue


    helyszin = HELYSZINEK[
        helyszin_kulcs
    ]


    # ========================================================
    # Időellenőrzés
    # ========================================================

    idoben_ott_kell_lennie = (
        kezdés
        <= ellenorzes_idopont
        <= végzés
    )


    if not idoben_ott_kell_lennie:

        ellenorzesek.append({
            "viszonylat": viszonylat,
            "forda": forda,
            "rendszám": rendszam,
            "hely": hely,
            "helyszín": helyszin_kulcs,
            "ellenőrzés": "NEM AKTUÁLIS"
        })

        continue


    # ========================================================
    # Az adott forda legutóbbi pozíciója
    # ========================================================

    forda_poziciok = [
        p
        for p in poziciok
        if str(p.get("viszonylat", "")).strip()
        == viszonylat
        and
        str(p.get("forda", "")).strip()
        == forda
    ]


    if not forda_poziciok:

        ellenorzesek.append({
            "viszonylat": viszonylat,
            "forda": forda,
            "rendszám": rendszam,
            "hely": hely,
            "helyszín": helyszin_kulcs,
            "ellenőrzés": "NINCS POZÍCIÓ"
        })

        continue


    # Legutóbbi pozíció használata
    utolso = forda_poziciok[-1]


    latitude = utolso.get(
        "latitude"
    )

    longitude = utolso.get(
        "longitude"
    )


    if latitude is None or longitude is None:

        ellenorzesek.append({
            "viszonylat": viszonylat,
            "forda": forda,
            "rendszám": rendszam,
            "hely": hely,
            "helyszín": helyszin_kulcs,
            "ellenőrzés": "NINCS POZÍCIÓ"
        })

        continue


    # ========================================================
    # GPS → TÉGLALAP ELLENŐRZÉS
    # ========================================================

    lat_benne = (
        helyszin["lat_min"]
        <= float(latitude)
        <= helyszin["lat_max"]
    )

    lon_benne = (
        helyszin["lon_min"]
        <= float(longitude)
        <= helyszin["lon_max"]
    )


    ott_van = (
        lat_benne
        and lon_benne
    )


    if ott_van:

        eredmeny = "OK"

    else:

        eredmeny = "NEM"


    ellenorzesek.append({
        "viszonylat": viszonylat,
        "forda": forda,
        "rendszám": rendszam,
        "hely": hely,
        "helyszín": helyszin_kulcs,
        "latitude": float(latitude),
        "longitude": float(longitude),
        "pozíció_időpont": utolso.get(
            "időpont",
            ""
        ),
        "ellenőrzés": eredmeny
    })


# ============================================================
# 4. Eredmény
# ============================================================

helyszin_ellenorzes = pd.DataFrame(
    ellenorzesek
)


if len(helyszin_ellenorzes) > 0:

    helyszin_ellenorzes = (
        helyszin_ellenorzes
        .sort_values(
            by=[
                "viszonylat",
                "forda"
            ]
        )
        .reset_index(drop=True)
    )


print()
print(
    "Ellenőrzött fordák:",
    len(helyszin_ellenorzes)
)


if len(helyszin_ellenorzes) > 0:

    print(
        helyszin_ellenorzes.to_string(
            index=False
        )
    )

else:

    print(
        "Nincs ellenőrizhető forda."
    )
