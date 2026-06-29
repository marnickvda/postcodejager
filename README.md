# Postcodejager 🚴

Een tool om de **PostNL Postcode Challenge** efficiënt af te vinken op de
racefiets. Hij leidt uit je Strava-ritten af welke van de ~4.000 PC4-postcode­
gebieden je al hebt gehad, toont ze op een kaart, helpt een route over verharde
fietspaden/wegen (geen gravel) te plannen die veel nieuwe postcodes pakt, en
exporteert een neutrale GPX voor je fietscomputer.

**Local-first:** al je data — je Strava-token, afgevinkte postcodes en je
selectie — leeft in **localStorage in je browser**. De backend is **stateless**:
hij doet alleen het rekenwerk dat Python/kaartdata/het Strava-secret nodig heeft
(token-uitwisseling, ritten ophalen, matchen, routeren, GPX). Hij slaat niets op,
dus er is geen database en geen login nodig.

## Wat het doet

- **Voortgang** uit Strava: afgevinkt (groen) vs. open (grijs), met percentage en
  een uitklapbare **per-provincie**-stand.
- **Selecteren**: klik postcodes, of houd **Shift** ingedrukt en sleep een kader
  om een heel gebied in één keer te pakken. Selectie blijft bewaard tussen sessies.
- **Impact**: zie live hoeveel procent je selectie zou opleveren (totaal + per
  provincie).
- **Route**: de tool ordent de selectie (nearest-neighbour + 2-opt) en routeert er
  via BRouter doorheen over verharde wegen/fietspaden, als rondrit of punt-naar-punt.
  Optioneel klik je een **startpunt** op de kaart (en bij punt-naar-punt ook een
  **eindpunt**); de rondrit vertrekt en eindigt dan thuis.
- **GPX**: exporteer de route, of **importeer** een GPX om meteen te zien hoeveel
  nieuwe postcodes hij pakt.

## Lokaal draaien

Vereist Python 3.11+.

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

**Strava-app:** maak er een aan op <https://www.strava.com/settings/api>, zet de
**Authorization Callback Domain** op `localhost`, kopieer `.env.example` naar
`.env` en vul `STRAVA_CLIENT_ID` + `STRAVA_CLIENT_SECRET` in.

**Postcodedata** (CBS PC4-grenzen, CC BY 4.0 → `data/pc4.geojson`):

```bash
.venv/bin/python scripts/fetch_pc4.py
```

**Starten:**

```bash
.venv/bin/python -m postcodejager   # -> http://localhost:8000
```

## GPX op je fietscomputer

De GPX is neutraal en werkt voor beide routes:

- **Komoot**: importeren is gratis (wordt een navigeerbare route), maar sinds
  2025 is het *syncen naar een Garmin/Wahoo* via Komoot betaald.
- **Direct (gratis)**: zet het GPX-bestand rechtstreeks op je Garmin/Wahoo
  (USB of via Garmin Connect / de Wahoo-app).

De track krijgt standaard een `<type>cycling</type>`-hint, zodat import-apps
(Strava/Komoot) de rit meteen als fietsroute herkennen. Pas dit aan met
`GPX_TRACK_TYPE` in `.env` (bijv. `Road cycling`), of zet hem leeg
(`GPX_TRACK_TYPE=`) voor een volledig neutrale GPX. Let op: de meeste
fietscomputers negeren deze hint en vragen het profiel bij de start van de rit —
voor een sport die je Garmin écht overneemt is een FIT/TCX-koers nodig.

## Tests

```bash
.venv/bin/pytest
```

## Deployen

Productie-opzet (Hetzner + OpenTofu + Ansible + GitHub Actions, met automatische
HTTPS en deploy bij elke push naar `main`) staat in **[`deploy/README.md`](deploy/README.md)**.
Omdat de backend stateless is, is er geen database om te bewaren.

## Routing-engine

Standaard de publieke [BRouter](https://brouter.de)-server met het
`trekking`-profiel. Zelf hosten of een ander profiel kan via `BROUTER_BASE_URL` /
`BROUTER_PROFILE` in `.env`.

## Route afstellen

De route wordt *door* elk gebied geregen — een ingang aan de kant van het vorige
gebied en een uitgang aan de kant van het volgende — zodat de rit doorloopt in
plaats van er telkens in te duiken en terug te keren. Twee constanten in de code
sturen dat gedrag:

- **`ENTRY_DEPTH_M`** (`src/postcodejager/postcodes.py`, standaard `250`) — hoe
  diep (in meters) een waypoint het gebied in ligt. Hoger = robuuster afvinken
  (minder kans dat BRouter een waypoint net buiten de grens snapt), maar minder
  vloeiend. Lager = strakkere lijn, iets gevoeliger voor GPS-ruis.
- **`COLLAPSE_M`** (`src/postcodejager/planning.py`, standaard `40`) — liggen de
  in- en uitgang dichter dan dit bij elkaar, dan worden ze één punt. Voorkomt een
  nutteloze mini-omweg in gebieden die te klein of te ingeklemd zijn om
  doorheen te rijden.

## Databronnen & attributie

- Postcodegrenzen: **CBS / Kadaster (BAG)** via OpenDataSoft — CC BY 4.0
  (`georef-netherlands-postcode-pc4`)
- Provinciegrenzen: **Kadaster** via OpenDataSoft — CC0 1.0
  (`georef-netherlands-provincie`, meegeleverd in `src/postcodejager/data/provinces.geojson`)
- Kaarttegels: **CARTO** basemaps · © **OpenStreetMap**-bijdragers
- Routing: **BRouter** op **OpenStreetMap**-data (ODbL)
- Activiteiten: **Strava** (scope `activity:read_all`, alleen je eigen data) —
  onder de Strava API Agreement en merkrichtlijnen
