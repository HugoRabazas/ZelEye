#!/usr/bin/env python3
"""Descarga las stats de Call of Dragons desde cod-tracker.com y las deja en data/stats/.

Pensado para correr en GitHub Actions (una vez al día). Hace UNA sola petición de datos
(`/api/snapshot/latest`), que devuelve todos los reinos a la vez, para no cargar su servidor.

Reutiliza el mismo método que el repositorio Discord-Rankings del autor: curl_cffi imita el
handshake TLS de un navegador real para pasar Cloudflare, y pide el token de la web igual que
haría un visitante. No resuelve ningún captcha: si cod-tracker activa el modo "enforce" con
Turnstile, el token llega con 403 y el script termina sin datos en vez de intentar saltárselo.

Uso autorizado por el responsable de cod-tracker. Créditos a cod-tracker.com en la web.

Salida (ignorada por git, la regenera el workflow):
  data/stats/kingdoms_codtracker.csv      total_power, lords, top1_power, p10_power, t5_lords, merits por reino
  data/stats/top_players_codtracker.csv   kingdom, name, alliance, power (para el 10º exacto de la zona)

Variables de entorno:
  COD_TRACKER_BASE   (opcional) base URL, por defecto https://cod-tracker.com
  COD_TRACKER_MAX_KINGDOM (opcional) nº de reino global máximo, por defecto 1024
"""
from __future__ import annotations

import csv
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATS = ROOT / "data" / "stats"
BASE = os.environ.get("COD_TRACKER_BASE", "https://cod-tracker.com").rstrip("/")
MAX_KINGDOM = int(os.environ.get("COD_TRACKER_MAX_KINGDOM", "1024"))
PROFILES = ["chrome124", "chrome120", "safari17_0", "firefox120"]


def fetch_snapshot() -> dict:
    """Devuelve {realm(str): [jugadores]} con UNA petición de datos. Lanza excepción si falla."""
    from curl_cffi import requests as cr  # import tardío: solo hace falta al descargar

    last = None
    for profile in PROFILES:
        try:
            s = cr.Session(impersonate=profile)
            # 1) visita la portada y la vista para asentar las cookies de Cloudflare
            s.get(f"{BASE}/", timeout=15)
            time.sleep(1.0)
            s.get(f"{BASE}/view", timeout=15)
            time.sleep(1.0)
            # 2) token de la web (sin captcha en modo monitor)
            tok_resp = s.get(
                f"{BASE}/api/token",
                headers={"Accept": "application/json, text/plain, */*", "Origin": BASE,
                         "Referer": f"{BASE}/view", "Sec-Fetch-Dest": "empty",
                         "Sec-Fetch-Mode": "cors", "Sec-Fetch-Site": "same-origin"},
                timeout=15,
            )
            if tok_resp.status_code != 200:
                raise RuntimeError(f"/api/token HTTP {tok_resp.status_code}: {tok_resp.text[:120]}")
            tok = tok_resp.json().get("token")
            if not tok:
                raise RuntimeError(f"token ausente (¿Turnstile activo?): {tok_resp.text[:120]}")
            s.headers.update({"X-App-Token": tok})
            # 3) una sola petición con todos los reinos
            snap = s.get(
                f"{BASE}/api/snapshot/latest",
                headers={"Accept": "application/json, text/plain, */*", "Referer": f"{BASE}/view",
                         "Sec-Fetch-Dest": "empty", "Sec-Fetch-Mode": "cors", "Sec-Fetch-Site": "same-origin"},
                timeout=60,
            )
            if snap.status_code != 200:
                raise RuntimeError(f"/api/snapshot/latest HTTP {snap.status_code}: {snap.text[:120]}")
            data = snap.json()
            if not isinstance(data, dict) or not data:
                raise RuntimeError("respuesta vacía o con formato inesperado")
            print(f"[+] cod-tracker: {len(data)} reinos (perfil {profile})")
            return data
        except Exception as e:  # prueba el siguiente perfil de navegador
            print(f"[!] perfil {profile} falló: {e}", file=sys.stderr)
            last = e
            time.sleep(1.5)
    raise RuntimeError(f"No se pudo descargar cod-tracker: {last}")


def player_power(p: dict):
    for key in ("powerMax", "power"):
        v = p.get(key)
        if isinstance(v, (int, float)) and v > 0:
            return int(v)
    return None


def write_outputs(snapshot: dict) -> int:
    """Escribe los dos CSV. Devuelve el nº de reinos globales con datos."""
    STATS.mkdir(parents=True, exist_ok=True)
    kingdom_rows, player_rows = [], []
    kingdoms_with_data = 0

    for realm, players in snapshot.items():
        try:
            kid = int(str(realm).strip())
        except (TypeError, ValueError):
            continue
        if not (1 <= kid <= MAX_KINGDOM):  # solo reinos globales
            continue
        if not isinstance(players, list) or not players:
            continue

        powers, merits, t5 = [], 0, 0
        for p in players:
            if not isinstance(p, dict):
                continue
            pw = player_power(p)
            if pw is None:
                continue
            powers.append(pw)
            if isinstance(p.get("merit"), (int, float)):
                merits += int(p["merit"])
            if isinstance(p.get("grade"), (int, float)) and p["grade"] >= 5:
                t5 += 1
            player_rows.append([kid, p.get("name", ""), p.get("alliance", ""), pw])
        if not powers:
            continue
        powers.sort(reverse=True)
        kingdom_rows.append([
            kid, sum(powers), len(powers), powers[0],
            powers[9] if len(powers) >= 10 else "", t5, merits,
        ])
        kingdoms_with_data += 1

    with (STATS / "kingdoms_codtracker.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["kingdom", "total_power", "lords", "top1_power", "p10_power", "t5_lords", "merits"])
        w.writerows(sorted(kingdom_rows))
    with (STATS / "top_players_codtracker.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["kingdom", "name", "alliance", "power"])
        w.writerows(player_rows)

    print(f"[+] {kingdoms_with_data} reinos globales, {len(player_rows)} lords -> data/stats/*_codtracker.csv")
    return kingdoms_with_data


def main() -> int:
    try:
        snapshot = fetch_snapshot()
    except Exception as e:
        print(f"[X] cod-tracker no disponible: {e}", file=sys.stderr)
        return 1
    write_outputs(snapshot)
    return 0


if __name__ == "__main__":
    sys.exit(main())
