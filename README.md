# ZelEye · Great Heights Finder

Web estática (GitHub Pages) para encontrar la **zona de Great Heights (Call of Dragons) con menos competencia para entrar en el top 10**.

## Idea

En Great Heights compites contra todos los lords de los reinos de tu **grupo** (ver `data/groups.csv`). Cada grupo de reinos es una **zona**, y lo que decide si entras en el top 10 es el **poder del 10º lord más fuerte de la zona**. La web calcula ese umbral para cada zona, las ordena de menos a más competencia, le da una nota de *facilidad* (0–100) y te dice en qué puesto quedarías con tu poder.

## Estructura

```
data/groups.csv              Zonas de Great Heights (cada fila = 8 reinos que compiten juntos; solo se usan las globales)
data/stats/kingdoms.csv      Stats por reino (las añades tú; plantilla con cabeceras)
data/stats/top_players.csv   Lords por reino → umbral de top 10 exacto
data/history/                Una foto por escaneo (la genera el workflow) → crecimiento 7 días
scripts/build_data.py        Junta grupos + stats → site/data.json
site/                        La web (HTML/CSS/JS sin dependencias)
.github/workflows/update-and-deploy.yml   Se ejecuta 1 vez al día y publica la web
```

## Publicarla (una sola vez)

1. Fusiona la rama en `main`.
2. En GitHub: **Settings → Pages → Build and deployment → Source: GitHub Actions**.
3. **Actions → "Actualizar stats y publicar web" → Run workflow**. La web quedará en `https://<usuario>.github.io/ZelEye/`.

El escaneo de datos **no es automático**: lo lanzas tú desde *Actions → “Actualizar stats y publicar web” → Run workflow* cuando quieras datos frescos. El sitio se republica también al cambiar el código, reutilizando el último escaneo guardado.

## Fuentes de stats

La fuente principal es **cod-tracker.com**, con permiso de su responsable. Al lanzar el escaneo
(*Actions → Run workflow*), `scripts/fetch_cod_tracker.py` hace **una sola petición** a `/api/snapshot/latest`, que devuelve
todos los reinos, y calcula las stats por reino. Usa `curl_cffi` para imitar un navegador real
(como el repo Discord-Rankings); no resuelve captchas: si cod-tracker activa Turnstile, el script
termina sin datos y la web se genera con lo que haya. Se puede desactivar con la variable de
repositorio `COD_TRACKER_ENABLED=false`.

Además puedes añadir o completar datos por tu cuenta:



1. **CSV en el repo**: rellena `data/stats/kingdoms.csv` y/o `data/stats/top_players.csv` (por ejemplo, con lo que exportes desde tu cuenta en esas webs o con datos de tu alianza). Puedes tener varios ficheros (`kingdoms_*.csv`, `top_players_*.csv`). Se aceptan separador `;` o `,`, sufijos `k/m/b` y alias de columnas (`server`, `power`, `reino`, `poder`…). Solo se usan los reinos globales; los chinos (id negativo en callofstats) se ignoran.
2. **API autorizada**: si el dueño de una web de stats te da acceso, guarda `STATS_API_URL` (y `STATS_API_TOKEN`) en *Settings → Secrets → Actions*. Formato JSON esperado:
   ```json
   {"kingdoms": [{"kingdom": 338, "zone": "global", "total_power": 2.1e9, "p10_power": 4.5e7}],
    "players":  [{"kingdom": 338, "zone": "global", "name": "Lord", "alliance": "ABC", "power": 9.1e7}]}
   ```
3. **Importar CSV local** (botón en la web): carga el CSV solo en tu navegador, sin subirlo.
4. **Google Sheets (o cualquier CSV por URL)**: se lee en cada escaneo. Ver abajo.

### Google Sheets → web, automático

1. Crea una hoja en Google Sheets e importa `data/plantilla_reinos.csv` (*Archivo → Importar*). Trae los 1024 reinos globales con las columnas vacías.
2. Rellena lo que tengas: `total_power`, `p10_power` (poder del 10º lord del reino), `top1_power`, `lords`. Las filas vacías se ignoran.
3. Opcional, para que el 10º de la zona sea exacto: crea otra pestaña con `kingdom, name, alliance, power` (los 10–20 lords más fuertes de cada reino).
4. *Archivo → Compartir → Publicar en la web* → elige la pestaña → formato **CSV** → copia el enlace (uno por pestaña).
5. En GitHub: *Settings → Secrets and variables → Actions → New repository secret*, nombre `STATS_CSV_URLS`, valor: los enlaces separados por espacios.

Cuando lances el escaneo (*Actions → Run workflow*), el proceso descarga la hoja junto con cod-tracker y publica la web. Cualquiera de tu alianza puede ir rellenando la hoja entre escaneos.

### Columnas

`kingdoms.csv`: `kingdom; total_power; lords; active_lords; top1_power; p10_power; top10_power; top100_power; t5_lords; merits; kills; open_date; source`
`top_players.csv`: `kingdom; name; alliance; power`

- Con `top_players.csv` (top 10–100 de cada reino) el **poder del 10º del grupo es exacto**.
- Con solo `p10_power` por reino se muestra **≥ X**: es un mínimo garantizado, porque un reino con 10 lords por encima de X obliga a que el 10º del grupo tenga como mínimo X.

## Uso local

```bash
python3 scripts/build_data.py
```

```bash
python3 -m http.server -d site 8000
```
