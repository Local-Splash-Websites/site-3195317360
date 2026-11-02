# Bennett's Moving Company

Static copy of https://www.bennettmoving.net/ migrated from Duda by Dudaport (run `dpr_f99qjv3rb6dtsb59gh5m`, profile 1412063, Duda site `1e10ecc1`).

| Path | What it is |
|---|---|
| `src/` | Page templates (the crawled HTML with placeholders such as `{{ business.telephone | phone_national }}`) and assets |
| `data/site.json` | Business variables (schema.org names). **Edit them in Deploy** (Site registry → this site); Deploy commits here |
| `build/render.py` | Renders `src/` with `data/site.json` into `public/` (stage 1 of the Dockerfile) |
| `apache/site.conf` | Apache config: clean page URLs and the `/v1/lead` proxy to the shared lead service |
| `report/` | What the migration found: gaps, phone replacements and warnings, forms, assets, verification |

Builds need only this repository. A rollback is a redeploy of an older commit.

## Run locally

```sh
docker build -t site-3195317360 .
docker run --rm -p 8080:80 -e LEADS_SERVICE_URL=http://website-lead-submit:8080 site-3195317360
```

Or render without Docker: `pip install -r build/requirements.txt && python build/render.py` (output in `public/`).
