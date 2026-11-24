# ZelEye · Great Heights Finder

Web estática (GitHub Pages) para encontrar la **zona de Great Heights (Call of Dragons) con menos competencia para entrar en el top 10**.

## Idea

En Great Heights compites contra todos los lords de los reinos de tu **grupo** (ver `data/groups.csv`). Cada grupo de reinos es una **zona**, y lo que decide si entras en el top 10 es el **poder del 10º lord más fuerte de la zona**. La web calcula ese umbral para cada zona, las ordena de menos a más competencia, le da una nota de *facilidad* (0–100) y te dice en qué puesto quedarías con tu poder.

## Estructura

```
data/groups.csv              Zonas de Great Heights (cada fila = 8 reinos que compiten juntos; solo se usan las globales)
data/stats/kingdoms.csv      Stats por reino (las añades tú; plantilla con cabeceras)
data/stats/top_players.csv   Lords por reino → umbral de top 10 exacto
data/history/                Una foto diaria (la genera el workflow) → crecimiento 7 días
scripts/build_data.py        Junta grupos + stats → site/data.json
site/                        La web (HTML/CSS/JS sin dependencias)
.github/workflows/update-and-deploy.yml   Se ejecuta 1 vez al día y publica la web
```

## Publicarla (una sola vez)

1. Fusiona la rama en `main`.
2. En GitHub: **Settings → Pages → Build and deployment → Source: GitHub Actions**.
3. **Actions → "Actualizar stats y publicar web" → Run workflow**. La web quedará en `https://<usuario>.github.io/ZelEye/`.

Después se actualiza sola **cada día a las 05:17 UTC**, y también cada vez que cambies algo en `data/`, `site/` o `scripts/`.

## Fuentes de stats

Las webs de stats de Call of Dragons no permiten la descarga automática:

| Web | Situación |
|---|---|
| callofstats.com | Los datos de servidores exigen login; sus términos prohíben el scraping |
| dragonstats.com | Bloquea los navegadores automatizados; sus términos prohíben saltarse los límites técnicos |
| cod-tracker.com | API protegida con token + Cloudflare Turnstile; `robots.txt` prohíbe `/api/snapshot` y `/api/greatheight` |

Por eso el proceso diario usa fuentes legítimas:

1. **CSV en el repo**: rellena `data/stats/kingdoms.csv` y/o `data/stats/top_players.csv` (por ejemplo, con lo que exportes desde tu cuenta en esas webs o con datos de tu alianza). Puedes tener varios ficheros (`kingdoms_*.csv`, `top_players_*.csv`). Se aceptan separador `;` o `,`, sufijos `k/m/b` y alias de columnas (`server`, `power`, `reino`, `poder`…). Solo se usan los reinos globales; los chinos (id negativo en callofstats) se ignoran.
2. **API autorizada**: si el dueño de una web de stats te da acceso, guarda `STATS_API_URL` (y `STATS_API_TOKEN`) en *Settings → Secrets → Actions*. Formato JSON esperado:
   ```json
   {"kingdoms": [{"kingdom": 338, "zone": "global", "total_power": 2.1e9, "p10_power": 4.5e7}],
    "players":  [{"kingdom": 338, "zone": "global", "name": "Lord", "alliance": "ABC", "power": 9.1e7}]}
   ```
3. **Importar CSV local** (botón en la web): carga el CSV solo en tu navegador, sin subirlo.

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
