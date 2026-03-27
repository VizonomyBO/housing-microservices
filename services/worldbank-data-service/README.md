# World Bank Data Service

FastAPI microservice for Data360 indicator retrieval and chart recommendation.

## Endpoints

- `GET /health`
- `GET /v1/worldbank/indicators/{indicator_id}/csv`
- `GET /v1/worldbank/indicators/{indicator_id}/chart`
- `POST /v1/worldbank/charts/recommend`

## Allowed Indicators

- `WB_FINDEX_FIN22A`
- `WB_GS_SG_OWN_HS`
- `WB_SSGD_PCT_URBAN_POP`

## Local Run

```bash
cd services/worldbank-data-service
uv sync --all-extras
uv run uvicorn worldbank_data_service.main:app --host 0.0.0.0 --port 8092
```

## Environment

- `WORLDBANK_DATA_SERVICE_PORT` (default `8092`)
- `WORLDBANK_DATA_CORS_ORIGINS` (default `*`)
- `DATA360_BASE_URL` (default `https://data360api.worldbank.org`)
- `DATA360_REQUEST_TIMEOUT_SECONDS` (default `30`)
