# 🚨 Incident Management System (IMS)

## Architecture
## Design Patterns
- **Strategy Pattern** — P0AlertStrategy / P1AlertStrategy / P2AlertStrategy
- **State Pattern** — WorkItemStateMachine (OPEN→INVESTIGATING→RESOLVED→CLOSED)

## Backpressure
Redis queue absorbs signal bursts. API returns immediately after LPUSH. Worker drains at Postgres write speed. Rate limiter (100 req/10s) blocks floods at the API layer. Queue depth shown on /health.

## Setup
```bash
docker compose up --build
# Wait 30s then open http://localhost:3000
python simulate.py
```

## Run Tests
```bash
pip install fastapi asyncpg motor pytest
pytest tests/ -v
```

## API
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /signal | Ingest signal |
| GET | /incidents | List incidents (cached) |
| GET | /signals/{id} | Raw signals from MongoDB |
| POST | /transition/{id} | State transition |
| POST | /rca/{id} | Submit RCA and close |
| GET | /stats | Aggregations |
| GET | /health | Health + queue depth |
