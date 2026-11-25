#!/usr/bin/env python3
"""Descarga las stats de Call of Dragons desde cod-tracker.com y las deja en data/stats/.

Pensado para correr en GitHub Actions a demanda (Run workflow). Pide los datos reino por reino
(`/api/snapshot/server/{realm}?sv=v2`), con una pausa entre peticiones para no saturar
el servidor. (cod-tracker retiró el endpoint que devolvía todos los reinos de golpe.)

Reutiliza el mismo método que el repositorio Discord-Rankings del autor: curl_cffi imita el
handshake TLS de un navegador real para pasar Cloudflare, y pide el token de la web igual que
haría un visitante. No resuelve ningún captcha: si cod-tracker activa el modo "enforce" con
Turnstile, el token llega con 403 y el script termina sin datos en vez de intentar saltárselo.

Uso autorizado por el responsable de cod-tracker. Créditos a cod-tracker.com en la web.

Salida (ignorada por git, la regenera el workflow):
  data/stats/kingdoms_codtracker.csv      total_power, lords, top1_power, p10_power, merits por reino
  data/stats/top_players_codtracker.csv   kingdom, name, alliance, power (para el 10º exacto de la zona)

Variables de entorno (todas opcionales):
  COD_TRACKER_BASE     base URL, por defecto https://cod-tracker.com
  COD_TRACKER_REALMS   reinos a pedir, p. ej. "1-1024" o "729-736,100-108". Por defecto "1-1024".
  COD_TRACKER_DELAY    segundos de pausa entre peticiones, por defecto 0.25
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
DELAY = float(os.environ.get("COD_TRACKER_DELAY", "0.25"))
PROFILES = ["chrome124", "chrome120", "safari17_0", "chrome116"]
MAX_CONSEC_FAILS = 25  # si fallan tantos reinos seguidos, algo va mal (bloqueo/token): parar


def parse_realms(spec: str) -> list[int]:
    out: list[int] = []
    for part in spec.replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return sorted(set(out))


def make_session():
    """Crea una sesión que pasa Cloudflare y trae un X-App-Token válido. Lanza excepción si no puede."""
    from curl_cffi import requests as cr  # import tardío: solo hace falta al descargar

    last = None
    for profile in PROFILES:
        try:
            s = cr.Session(impersonate=profile)
            s.get(f"{BASE}/", timeout=15)
            time.sleep(1.0)
            s.get(f"{BASE}/view", timeout=15)
            time.sleep(1.0)
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
            print(f"[+] cod-tracker: sesión lista (perfil {profile})")
            return s
        except Exception as e:  # prueba el siguiente perfil de navegador
            print(f"[!] perfil {profile} falló: {e}", file=sys.stderr)
            last = e
            time.sleep(1.5)
    raise RuntimeError(f"No se pudo iniciar sesión en cod-tracker: {last}")


def fetch_realm(session, realm: int):
    """Devuelve la lista de jugadores del día más reciente de un reino, o None si no hay datos."""
    headers = {"Accept": "application/json, text/plain, */*", "Referer": f"{BASE}/view",
               "Sec-Fetch-Dest": "empty", "Sec-Fetch-Mode": "cors", "Sec-Fetch-Site": "same-origin"}
    r = session.get(f"{BASE}/api/snapshot/server/{realm}?sv=v2", headers=headers, timeout=20)
    if r.status_code == 404:
        return None  # reino inexistente
    if r.status_code in (401, 403):
        raise PermissionError(f"HTTP {r.status_code}: {r.text[:100]}")  # token caducado o bloqueo
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:100]}")
    data = (r.json() or {}).get("data", {})
    if not data:
        return None
    latest = sorted(data.keys(), reverse=True)[0]
    return data[latest]


def player_power(p: dict):
    for key in ("powerMax", "power"):
        v = p.get(key)
        if isinstance(v, (int, float)) and v > 0:
            return int(v)
    return None


def write_outputs(snapshot: dict) -> int:
    """Escribe los dos CSV a partir de {realm(int): [jugadores]}. Devuelve nº de reinos con datos."""
    STATS.mkdir(parents=True, exist_ok=True)
    kingdom_rows, player_rows, with_data = [], [], 0
    for kid, players in snapshot.items():
        if not isinstance(players, list) or not players:
            continue
        powers, merits = [], 0
        for p in players:
            if not isinstance(p, dict):
                continue
            pw = player_power(p)
            if pw is None:
                continue
            powers.append(pw)
            if isinstance(p.get("merit"), (int, float)):
                merits += int(p["merit"])
            player_rows.append([kid, p.get("name", ""), p.get("alliance", ""), pw])
        if not powers:
            continue
        powers.sort(reverse=True)
        kingdom_rows.append([kid, sum(powers), len(powers), powers[0],
                             powers[9] if len(powers) >= 10 else "", merits])
        with_data += 1

    with (STATS / "kingdoms_codtracker.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["kingdom", "total_power", "lords", "top1_power", "p10_power", "merits"])
        w.writerows(sorted(kingdom_rows))
    with (STATS / "top_players_codtracker.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["kingdom", "name", "alliance", "power"])
        w.writerows(player_rows)
    print(f"[+] {with_data} reinos con datos, {len(player_rows)} lords -> data/stats/*_codtracker.csv")
    return with_data


def main() -> int:
    realms = parse_realms((os.environ.get("COD_TRACKER_REALMS") or "1-1024").strip() or "1-1024")
    print(f"[*] cod-tracker: pidiendo {len(realms)} reinos (pausa {DELAY}s)...")
    try:
        session = make_session()
    except Exception as e:
        print(f"[X] cod-tracker no disponible: {e}", file=sys.stderr)
        return 1

    snapshot, consec_fails, retried = {}, 0, False
    for i, realm in enumerate(realms, 1):
        try:
            players = fetch_realm(session, realm)
            consec_fails = 0
            if players:
                snapshot[realm] = players
        except PermissionError as e:
            # token caducado o bloqueo temporal: renovar sesión UNA vez y reintentar el reino
            if not retried:
                print(f"[!] {e} -> renovando sesión...", file=sys.stderr)
                retried = True
                try:
                    session = make_session()
                    continue
                except Exception as e2:
                    print(f"[X] no se pudo renovar la sesión: {e2}", file=sys.stderr)
                    break
            consec_fails += 1
        except Exception as e:
            consec_fails += 1
            if consec_fails <= 3:
                print(f"[!] reino {realm}: {e}", file=sys.stderr)
        if consec_fails >= MAX_CONSEC_FAILS:
            print(f"[X] {MAX_CONSEC_FAILS} fallos seguidos, paro para no insistir.", file=sys.stderr)
            break
        if i % 100 == 0:
            print(f"    ... {i}/{len(realms)} reinos, {len(snapshot)} con datos")
        time.sleep(DELAY)

    if not snapshot:
        print("[X] cod-tracker: ningún reino devolvió datos.", file=sys.stderr)
        return 1
    write_outputs(snapshot)
    return 0


if __name__ == "__main__":
    sys.exit(main())
