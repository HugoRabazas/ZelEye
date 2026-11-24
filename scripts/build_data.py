#!/usr/bin/env python3
"""Construye site/data.json a partir de los grupos de Great Heights y las stats disponibles.

Fuentes (todas opcionales salvo groups.csv):
  data/groups.csv                 Grupos de Great Heights (zona, config, grupo, reinos, fusiones).
  data/stats/kingdoms.csv         Una fila por reino con sus stats agregadas.
  data/stats/top_players.csv      Una fila por lord (reino, poder) -> permite calcular el umbral exacto de top 10.
  STATS_CSV_URLS                  URLs de CSV (p. ej. Google Sheets publicada como CSV), separadas por espacios o saltos de línea.
  STATS_API_URL (+ STATS_API_TOKEN) Endpoint JSON autorizado por el dueño de una web de stats (ver README).

Solo usa la librería estándar de Python.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SITE = ROOT / "site"
HISTORY = DATA / "history"

# Alias de columnas aceptados en los CSV (en minúsculas, sin espacios ni símbolos).
KINGDOM_ALIASES = {
    "kingdom": ["kingdom", "server", "serverid", "kd", "reino", "id"],
    "zone": ["zone", "zona", "region"],
    "total_power": ["totalpower", "power", "kingdompower", "poder", "podertotal"],
    "lords": ["lords", "players", "lordcount", "playercount", "jugadores", "numlords", "numjugadores"],
    "active_lords": ["activelords", "activeplayers", "activos"],
    "top1_power": ["top1power", "top1", "maxpower", "highestpower", "top1poder", "podertop1", "podermaximo"],
    "p10_power": ["p10power", "top10thpower", "rank10power", "power10", "decimo", "10poder", "poder10", "poderdel10", "poderdecimo", "decimopoder", "10power"],
    "top10_power": ["top10power", "top10sum", "top10"],
    "top100_power": ["top100power", "top100sum", "top100"],
    "t5_lords": ["t5lords", "t5players", "t5", "t5count"],
    "merits": ["merits", "totalmerits", "meritos"],
    "merits_prev": ["meritsprev", "meritosanterior", "meritostemporadapasada", "meritoslasttemp", "lastseasonmerit", "meritprev"],
    "kills": ["kills", "totalkills", "unitskilled"],
    "open_date": ["opendate", "opened", "startdate", "fechaapertura"],
    "source": ["source", "fuente"],
}
PLAYER_ALIASES = {
    "kingdom": ["kingdom", "server", "serverid", "kd", "reino"],
    "zone": ["zone", "zona", "region"],
    "power": ["power", "poder", "highestpower", "currentpower"],
    "name": ["name", "lord", "lordname", "nombre"],
    "alliance": ["alliance", "guild", "alianza"],
}


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def to_num(v):
    if v is None:
        return None
    s = str(v).strip().replace(",", "").replace("_", "")
    if not s:
        return None
    m = re.fullmatch(r"(-?\d+(?:\.\d+)?)\s*([kmbt])?", s, re.I)
    if not m:
        return None
    n = float(m.group(1))
    n *= {"k": 1e3, "m": 1e6, "b": 1e9, "t": 1e12}.get((m.group(2) or "").lower(), 1)
    return int(n) if n.is_integer() else n


def read_csv(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8-sig")
    lines = [l for l in text.splitlines() if l.strip() and not l.lstrip().startswith("#")]
    if not lines:
        return []
    delim = ";" if lines[0].count(";") >= lines[0].count(",") else ","
    return list(csv.DictReader(lines, delimiter=delim))


def map_columns(row: dict, aliases: dict) -> dict:
    by_norm = {norm(k): v for k, v in row.items() if k is not None}
    out = {}
    for field, names in aliases.items():
        for n in names:
            if n in by_norm and str(by_norm[n]).strip() != "":
                out[field] = by_norm[n].strip()
                break
    return out


def zone_and_id(raw_kingdom, raw_zone=None):
    """callofstats usa ids negativos para China (-338 = reino 338 de China)."""
    k = to_num(raw_kingdom)
    if k is None:
        return None, None
    zone = (raw_zone or "").strip().lower() or None
    if k < 0:
        return "china", int(-k)
    if zone in ("cn", "china", "chn"):
        zone = "china"
    return zone or "global", int(k)


# ---------------------------------------------------------------- grupos
def load_groups() -> list[dict]:
    groups = []
    for r in read_csv(DATA / "groups.csv"):
        if r["zone"] != "global":  # solo interesan los reinos globales
            continue
        merged = {}
        for tok in (r.get("merged_kingdoms") or "").split():
            m = re.fullmatch(r"(\d+)\(([^)]+)\)", tok)
            if m:
                merged[int(m.group(1))] = m.group(2)
        groups.append({
            "id": f"{r['zone']}-{r['config']}-{r['group_no']}",
            "zone": r["zone"],
            "config": r["config"],
            "group_no": int(r["group_no"]),
            "kingdoms": [int(x) for x in r["kingdoms"].split()],
            "merged": {str(k): v for k, v in merged.items()},
        })
    return groups


# ---------------------------------------------------------------- stats
def load_kingdom_stats() -> dict:
    stats = {}
    paths = sorted((DATA / "stats").glob("kingdoms*.csv"))
    for p in paths:
        for row in read_csv(p):
            m = map_columns(row, KINGDOM_ALIASES)
            zone, kid = zone_and_id(m.get("kingdom"), m.get("zone"))
            if kid is None:
                continue
            # Filas vacías (p. ej. la plantilla sin rellenar) no cuentan como datos.
            if not any(to_num(m[f]) is not None for f in m if f not in ("kingdom", "zone", "open_date", "source")):
                continue
            rec = stats.setdefault((zone, kid), {})
            for f in KINGDOM_ALIASES:
                if f in ("kingdom", "zone") or f not in m:
                    continue
                rec[f] = m[f] if f in ("open_date", "source") else to_num(m[f])
            rec.setdefault("source", p.name)
    return stats


def load_players() -> dict:
    players: dict = {}
    for p in sorted((DATA / "stats").glob("top_players*.csv")):
        for row in read_csv(p):
            m = map_columns(row, PLAYER_ALIASES)
            zone, kid = zone_and_id(m.get("kingdom"), m.get("zone"))
            pw = to_num(m.get("power"))
            if kid is None or pw is None:
                continue
            players.setdefault((zone, kid), []).append(
                {"p": pw, "n": m.get("name", ""), "a": m.get("alliance", "")}
            )
    return players


def load_api() -> tuple[dict, dict]:
    """Fuente opcional: JSON autorizado. Formato esperado:
    {"kingdoms": [{"kingdom": 338, "zone": "global", "total_power": ..., ...}],
     "players":  [{"kingdom": 338, "power": ..., "name": "..."}]}
    """
    url = os.environ.get("STATS_API_URL")
    if not url:
        return {}, {}
    headers = {"User-Agent": "great-heights-finder/1.0", "Accept": "application/json"}
    if os.environ.get("STATS_API_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['STATS_API_TOKEN']}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as r:
        payload = json.load(r)
    ks, ps = {}, {}
    for row in payload.get("kingdoms", []):
        m = map_columns({k: str(v) for k, v in row.items()}, KINGDOM_ALIASES)
        zone, kid = zone_and_id(m.get("kingdom"), m.get("zone"))
        if kid is None:
            continue
        rec = {f: (m[f] if f in ("open_date", "source") else to_num(m[f]))
               for f in KINGDOM_ALIASES if f in m and f not in ("kingdom", "zone")}
        rec.setdefault("source", "api")
        ks[(zone, kid)] = rec
    for row in payload.get("players", []):
        m = map_columns({k: str(v) for k, v in row.items()}, PLAYER_ALIASES)
        zone, kid = zone_and_id(m.get("kingdom"), m.get("zone"))
        pw = to_num(m.get("power"))
        if kid is not None and pw is not None:
            ps.setdefault((zone, kid), []).append({"p": pw, "n": m.get("name", ""), "a": m.get("alliance", "")})
    return ks, ps


# ---------------------------------------------------------------- cálculo
def fetch_remote_csvs() -> None:
    """Descarga cada URL de STATS_CSV_URLS a data/stats/ (ignorado por git) antes de leer los CSV.

    El tipo se deduce de la cabecera: si tiene columna de nombre de lord y de poder es una lista
    de jugadores (top_players_remote_N.csv); si no, stats por reino (kingdoms_remote_N.csv).
    """
    urls = (os.environ.get("STATS_CSV_URLS") or "").split()
    stats_dir = DATA / "stats"
    for old in stats_dir.glob("*_remote_*.csv"):
        old.unlink()
    for i, url in enumerate(urls, 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "great-heights-finder/1.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                text = r.read().decode("utf-8-sig", errors="replace")
        except Exception as e:  # una URL caída no debe tumbar la web
            print(f"[aviso] No se pudo descargar la URL de CSV nº {i}: {e}", file=sys.stderr)
            continue
        first = next((l for l in text.splitlines() if l.strip() and not l.lstrip().startswith("#")), "")
        cols = {norm(c) for c in re.split(r"[;,]", first)}
        is_players = bool(cols & {"name", "lord", "lordname", "nombre"}) and bool(cols & {"power", "poder", "highestpower", "currentpower"})
        name = f"{'top_players' if is_players else 'kingdoms'}_remote_{i}.csv"
        (stats_dir / name).write_text(text, encoding="utf-8")
        print(f"URL de CSV nº {i}: {len(text.splitlines())} líneas -> {name}")


def kth(values, k):
    v = sorted((x for x in values if x is not None), reverse=True)
    return v[k - 1] if len(v) >= k else None


def build():
    groups = load_groups()
    fetch_remote_csvs()
    kstats = load_kingdom_stats()
    players = load_players()
    try:
        api_k, api_p = load_api()
    except Exception as e:  # una caída de la API no debe tumbar la web
        print(f"[aviso] STATS_API_URL falló: {e}", file=sys.stderr)
        api_k, api_p = {}, {}
    for key, rec in api_k.items():
        kstats.setdefault(key, {}).update(rec)
    for key, lst in api_p.items():
        players[key] = lst  # la API sustituye al CSV para ese reino

    kingdoms_out = []
    for g in groups:
        group_players = []
        p10s, totals = [], []
        for kid in g["kingdoms"]:
            key = (g["zone"], kid)
            s = dict(kstats.get(key, {}))
            pl = sorted(players.get(key, []), key=lambda x: -x["p"])
            if pl:
                s.setdefault("top1_power", pl[0]["p"])
                if len(pl) >= 10:
                    s.setdefault("p10_power", pl[9]["p"])
                    s.setdefault("top10_power", sum(x["p"] for x in pl[:10]))
                group_players.extend(pl)
            p10s.append(s.get("p10_power"))
            totals.append(s.get("total_power"))
            kingdoms_out.append({
                "zone": g["zone"], "kingdom": kid, "group": g["id"],
                "merged": g["merged"].get(str(kid)),
                "stats": s,
                "players": [x["p"] for x in pl[:100]],
                "top_names": [[x["n"], x["a"], x["p"]] for x in pl[:10]],
            })

        group_players.sort(key=lambda x: -x["p"])
        if len(group_players) >= 10:
            thr, thr_kind = group_players[9]["p"], "exact"
        elif any(p10s):
            # Un reino con 10 lords por encima de X garantiza que el umbral del grupo es >= X.
            thr, thr_kind = max(x for x in p10s if x), "lower_bound"
        else:
            thr, thr_kind = None, None
        known_tot = [t for t in totals if t]
        g["metrics"] = {
            "top10_threshold": thr,
            "top10_threshold_kind": thr_kind,
            "top1_power": group_players[0]["p"] if group_players else kth(
                [kstats.get((g["zone"], k), {}).get("top1_power") for k in g["kingdoms"]], 1),
            "total_power": sum(known_tot) if known_tot else None,
            "avg_kingdom_power": (sum(known_tot) / len(known_tot)) if known_tot else None,
            "max_kingdom_power": max(known_tot) if known_tot else None,
            "kingdoms_with_stats": sum(1 for k in g["kingdoms"] if (g["zone"], k) in kstats or (g["zone"], k) in players),
            "players_known": len(group_players),
            "top10": [[x["n"], x["a"], x["p"]] for x in group_players[:10]],
        }
        g["players"] = [x["p"] for x in group_players[:300]]

    now = dt.datetime.now(dt.timezone.utc)
    out = {
        "generated_at": now.isoformat(timespec="seconds"),
        "has_stats": bool(kstats or players),
        "sources": sorted({s.get("source", "?") for s in kstats.values()} | ({"top_players.csv"} if players else set())),
        "groups": groups,
        "kingdoms": kingdoms_out,
    }
    SITE.mkdir(exist_ok=True)
    (SITE / "data.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # Histórico compacto (1 fichero por día) para ver crecimiento de poder.
    if out["has_stats"]:
        HISTORY.mkdir(exist_ok=True)
        snap = {f"{k['zone']}:{k['kingdom']}": {f: k["stats"].get(f) for f in ("total_power", "p10_power", "top1_power")}
                for k in kingdoms_out if k["stats"]}
        (HISTORY / f"{now.date()}.json").write_text(json.dumps(snap, separators=(",", ":")), encoding="utf-8")
    hist = sorted(HISTORY.glob("*.json"))[-60:]
    (SITE / "history.json").write_text(json.dumps(
        {p.stem: json.loads(p.read_text()) for p in hist}, separators=(",", ":")), encoding="utf-8")

    # Versión en las URLs de CSS/JS para que el navegador no mezcle ficheros viejos y nuevos.
    # Solo en GitHub Actions, para no ensuciar el index.html del repo al compilar en local.
    index = SITE / "index.html"
    stamp = now.strftime("%Y%m%d%H%M%S")
    if os.environ.get("GITHUB_ACTIONS"):
        index.write_text(re.sub(r'(styles\.css|app\.js)\?v=[^"]*', rf'\1?v={stamp}', index.read_text(encoding="utf-8")), encoding="utf-8")

    print(f"{len(groups)} grupos, {len(kingdoms_out)} reinos, stats para {len(kstats)} reinos, "
          f"{sum(len(v) for v in players.values())} lords.")


if __name__ == "__main__":
    build()
