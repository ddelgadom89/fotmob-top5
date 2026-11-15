"""
Estadísticas de PORTEROS de las 5 grandes ligas (FotMob), un CSV por liga.
Guarda por liga:
  data/<liga>_gk_latest.csv   -> foto actual
  data/<liga>_gk_history.csv  -> histórico (una foto por fecha)
"""
import os
import re
import json
import time
import datetime as dt

import pandas as pd
from curl_cffi import requests

# Ligas a descargar: nombre de archivo -> (id FotMob, slug de la URL)
# Para desactivar una liga, pon # delante de su línea.
LEAGUES = {
    "serie_a": (55, "serie"),
    "premier_league": (47, "premier-league"),
    "laliga": (87, "laliga"),
    "bundesliga": (54, "bundesliga"),
    "ligue_1": (53, "ligue-1"),
}

# Categorías de portero que se descargan
GK_STATS = ["saves", "_save_percentage", "_goals_prevented", "goals_conceded",
            "clean_sheet", "penalty_save", "total_keeper_sweeper", "total_high_claim",
            "rating", "mins_played", "accurate_pass", "accurate_long_balls"]
SOLO_PORTEROS = ["saves", "_save_percentage", "_goals_prevented"]
OUT_DIR = "data"

s = requests.Session(impersonate="chrome")


def buscar_urls(obj, out):
    if isinstance(obj, dict):
        if isinstance(obj.get("fetchAllUrl"), str):
            out.add(obj["fetchAllUrl"])
        for v in obj.values():
            buscar_urls(v, out)
    elif isinstance(obj, list):
        for v in obj:
            buscar_urls(v, out)
    return out


def datos_liga(league_id, slug):
    for url in (f"https://www.fotmob.com/api/data/leagues?id={league_id}",
                f"https://www.fotmob.com/api/leagues?id={league_id}"):
        r = s.get(url, timeout=30)
        print(f"{r.status_code} {url}")
        if r.status_code == 200:
            try:
                return r.json()
            except ValueError:
                pass
    url = f"https://www.fotmob.com/leagues/{league_id}/stats/{slug}/players"
    r = s.get(url, timeout=30)
    print(f"{r.status_code} {url}")
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
    if not m:
        raise RuntimeError("No se encontraron datos de la liga en FotMob.")
    return json.loads(m.group(1))


def descargar_liga(nombre, league_id, slug):
    print(f"\n=== {nombre} ===")
    urls = buscar_urls(datos_liga(league_id, slug), set())
    stats = {u.rsplit("/", 1)[-1].replace(".json", ""): u for u in urls if "/stats/" in u}
    player_stats = {k: u for k, u in stats.items() if k in GK_STATS}
    print(f"Categorías de portero ({len(player_stats)}):", sorted(player_stats))

    filas = []
    for stat, url in player_stats.items():
        try:
            j = s.get(url, timeout=30).json()
        except Exception as e:
            print(f"  fallo en {stat}: {e}")
            continue
        for lista in j.get("TopLists", []):
            for p in lista.get("StatList", []):
                filas.append({
                    "player_id": p.get("ParticiantId") or p.get("ParticipantId"),
                    "player": p.get("ParticipantName"),
                    "team_id": p.get("TeamId"),
                    "team": p.get("TeamName"),
                    "minutes": p.get("MinutesPlayed"),
                    "matches": p.get("MatchesPlayed"),
                    "stat": stat,
                    "value": p.get("StatValue"),
                    "sub_value": p.get("SubStatValue"),
                })
        time.sleep(1)

    largo = pd.DataFrame(filas)
    # Quedarse solo con porteros
    porteros = set(largo.loc[largo["stat"].isin(SOLO_PORTEROS), "player_id"])
    largo = largo[largo["player_id"].isin(porteros)]

    base = (largo.sort_values("minutes", ascending=False)
                 .drop_duplicates("player_id")[["player_id", "player", "team_id", "team",
                                                "minutes", "matches"]])
    valores = largo.pivot_table(index="player_id", columns="stat", values="value", aggfunc="first")
    subs = largo.pivot_table(index="player_id", columns="stat", values="sub_value", aggfunc="first")
    subs.columns = [f"{c}_sub" for c in subs.columns]
    df = base.merge(valores, on="player_id", how="left").merge(subs, on="player_id", how="left")
    df = df.dropna(axis=1, how="all").sort_values("minutes", ascending=False)

    fecha = dt.date.today().isoformat()
    df.insert(0, "fecha", fecha)
    df.insert(1, "league", nombre)

    os.makedirs(OUT_DIR, exist_ok=True)
    df.to_csv(f"{OUT_DIR}/{nombre}_gk_latest.csv", index=False)
    hist_path = f"{OUT_DIR}/{nombre}_gk_history.csv"
    if os.path.exists(hist_path):
        hist = pd.read_csv(hist_path)
        df_h = pd.concat([hist[hist["fecha"] != fecha], df], ignore_index=True)
    else:
        df_h = df
    df_h.to_csv(hist_path, index=False)
    print(f"Guardado: {len(df)} porteros, {df.shape[1]} columnas")


def main():
    errores = []
    for nombre, (league_id, slug) in LEAGUES.items():
        try:
            descargar_liga(nombre, league_id, slug)
        except Exception as e:
            print(f"ERROR en {nombre}: {e}")
            errores.append(nombre)
        time.sleep(3)
    if errores and len(errores) == len(LEAGUES):
        raise SystemExit(f"Fallaron todas las ligas: {errores}")


if __name__ == "__main__":
    main()
