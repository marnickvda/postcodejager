# Postcodejager 🧡

Een lokale tool om de **PostNL Postcode Challenge** efficiënt af te vinken op de
racefiets. Hij leidt uit je Strava-ritten af welke van de ~4.000 PC4-postcode­
gebieden je al hebt gehad, toont ze op een kaart, helpt een route over verharde
fietspaden/wegen (geen gravel) te plannen die veel nieuwe postcodes pakt, en
exporteert een neutrale GPX voor je fietscomputer.

Alles draait lokaal op `localhost`; je Strava-tokens blijven op je eigen machine.

## Installatie

Vereist Python 3.11+.

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## Strava-app aanmaken

1. Ga naar <https://www.strava.com/settings/api> en maak een API-applicatie.
2. Zet **Authorization Callback Domain** op `localhost`.
3. Kopieer `.env.example` naar `.env` en vul in:

```bash
cp .env.example .env
# vul STRAVA_CLIENT_ID en STRAVA_CLIENT_SECRET in
```

## Postcodedata ophalen

```bash
.venv/bin/python scripts/fetch_pc4.py
```

Dit downloadt de CBS PC4-grenzen (CC BY 4.0) naar `data/pc4.geojson`
(~4.000 gebieden).

## Starten

```bash
.venv/bin/python -m postcodejager
```

Open <http://localhost:8000>:

1. **Verbind met Strava** — daarna synchroniseert de tool je ritten automatisch
   op de achtergrond en berekent welke PC4-gebieden je al hebt gehad (groen) en
   welke nog open zijn (grijs). Het ↻-knopje ververst handmatig.
2. **Klik postcodes** op de kaart om ze mee te nemen in je route (oranje + ✓).
   Nog eens klikken haalt ze weg; de selectie blijft bewaard tussen sessies.
3. **Bereken route** — de tool kiest zelf een volgorde langs alle geselecteerde
   postcodes en routeert er via BRouter doorheen over verharde wegen/fietspaden;
   het toont de afstand plus het aantal nieuwe postcodes dat de route raakt.
4. **Exporteer GPX**.

## GPX op je fietscomputer

De GPX is neutraal en werkt voor beide routes:

- **Komoot**: importeren is gratis (wordt een navigeerbare route), maar sinds
  2025 is het *syncen naar een Garmin/Wahoo* via Komoot betaald.
- **Direct (gratis)**: zet het GPX-bestand rechtstreeks op je Garmin/Wahoo
  (USB of via Garmin Connect / de Wahoo-app).

## Tests

```bash
.venv/bin/pytest
```

## Routing-engine

Standaard gebruikt de tool de publieke [BRouter](https://brouter.de)-server met
het `trekking`-profiel. Voor intensief gebruik of een racefiets-specifiek
profiel (verhard, gravel vermijden) kun je BRouter zelf hosten en
`BROUTER_BASE_URL` / `BROUTER_PROFILE` in `.env` aanpassen.

## Databronnen & attributie

- Postcodegrenzen: **CBS PC4** via PDOK/Opendatasoft — CC BY 4.0
- Routing: **BRouter** op **OpenStreetMap**-data
- Activiteiten: **Strava** (scope `activity:read_all`, alleen je eigen data)

## Status

Fase 1 (MVP). De automatische **suggestie-engine** (cluster van open postcodes
voorstellen) volgt in fase 2 — zie `docs/superpowers/plans/`.
