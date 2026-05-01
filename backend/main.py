from __future__ import annotations
import asyncio
import json
import os
import time
from abc import ABC, abstractmethod
from collections import deque
from contextlib import asynccontextmanager
from typing import Optional
import asyncpg
import motor.motor_asyncio
import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

PG_HOST    = os.getenv("POSTGRES_HOST", "localhost")
MONGO_HOST = os.getenv("MONGO_HOST", "localhost")
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
RATE_LIMIT_MAX = 100
RATE_LIMIT_WINDOW = 10

class AlertStrategy(ABC):
    @abstractmethod
    def alert(self, incident_id: int, component_id: str) -> dict: ...

class P0AlertStrategy(AlertStrategy):
    def alert(self, incident_id: int, component_id: str) -> dict:
        print(f"🔴 [P0] CRITICAL PAGE — Incident #{incident_id} | {component_id}", flush=True)
        return {"severity": "P0", "channel": "pagerduty", "escalate": True}

class P1AlertStrategy(AlertStrategy):
    def alert(self, incident_id: int, component_id: str) -> dict:
        print(f"🟠 [P1] ALERT — Incident #{incident_id} | {component_id}", flush=True)
        return {"severity": "P1", "channel": "slack+email", "escalate": False}

class P2AlertStrategy(AlertStrategy):
    def alert(self, incident_id: int, component_id: str) -> dict:
        print(f"🟡 [P2] WARNING — Incident #{incident_id} | {component_id}", flush=True)
        return {"severity": "P2", "channel": "slack", "escalate": False}

def get_alert_strategy(component_id: str) -> AlertStrategy:
    if "RDBMS" in component_id or "DB" in component_id:
        return P0AlertStrategy()
    if "CACHE" in component_id or "REDIS" in component_id:
        return P2AlertStrategy()
    return P1AlertStrategy()

def get_severity_label(component_id: str) -> str:
    if "RDBMS" in component_id or "DB" in component_id:
        return "P0"
    if "CACHE" in component_id or "REDIS" in component_id:
        return "P2"
    return "P1"

VALID_TRANSITIONS: dict[str, list[str]] = {
    "OPEN": ["INVESTIGATING"],
    "INVESTIGATING": ["RESOLVED"],
    "RESOLVED": ["CLOSED"],
    "CLOSED": [],
}

class WorkItemStateMachine:
    def __init__(self, current_status: str):
        self._status = current_status

    @property
    def status(self) -> str:
        return self._status

    def can_transition(self, new_status: str) -> bool:
        return new_status in VALID_TRANSITIONS.get(self._status, [])

    def transition(self, new_status: str) -> str:
        if not self.can_transition(new_status):
            raise ValueError(f"Invalid transition: {self._status} → {new_status}. Allowed: {VALID_TRANSITIONS.get(self._status, [])}")
        old = self._status
        self._status = new_status
        return old

class AsyncRateLimiter:
    def __init__(self, max_requests: int, window: int):
        self._max = max_requests
        self._window = window
        self._timestamps: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def is_limited(self) -> bool:
        async with self._lock:
            now = time.monotonic()
            while self._timestamps and now - self._timestamps[0] > self._window:
                self._timestamps.popleft()
            if len(self._timestamps) >= self._max:
                return True
            self._timestamps.append(now)
            return False

rate_limiter = AsyncRateLimiter(RATE_LIMIT_MAX, RATE_LIMIT_WINDOW)
pg_pool: asyncpg.Pool | None = None
mongo_client = None
redis_client = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global pg_pool, mongo_client, redis_client
    for attempt in range(20):
        try:
            pg_pool = await asyncpg.create_pool(
                host=PG_HOST, database="ims_db", user="ims", password="ims",
                min_size=2, max_size=10)
            print("✅ Connected to PostgreSQL", flush=True)
            break
        except Exception:
            print(f"⏳ Waiting for Postgres (attempt {attempt+1})…", flush=True)
            await asyncio.sleep(2)
    async with pg_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS incidents (
                id           SERIAL PRIMARY KEY,
                component_id TEXT             NOT NULL,
                severity     TEXT             NOT NULL DEFAULT 'P1',
                status       TEXT             NOT NULL DEFAULT 'OPEN',
                start_time   DOUBLE PRECISION NOT NULL,
                end_time     DOUBLE PRECISION,
                mttr_seconds DOUBLE PRECISION,
                rca          JSONB
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS signal_stats (
                bucket BIGINT PRIMARY KEY,
                count  INT DEFAULT 0
            )
        """)
    mongo_client = motor.motor_asyncio.AsyncIOMotorClient(f"mongodb://{MONGO_HOST}:27017/")
    redis_client = await aioredis.from_url(f"redis://{REDIS_HOST}:6379", decode_responses=True)
    print("✅ Connected to MongoDB and Redis", flush=True)
    yield
    await pg_pool.close()
    mongo_client.close()
    await redis_client.aclose()

app = FastAPI(title="IMS API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class SignalPayload(BaseModel):
    component_id: str
    message: Optional[str] = "Failure detected"
    metadata: Optional[dict] = {}

class TransitionPayload(BaseModel):
    status: str

class RCAPayload(BaseModel):
    start_time: str
    end_time: str
    root_cause_category: str
    fix_applied: str
    prevention_steps: str

    def validate_complete(self):
        missing = [f for f in ["start_time","end_time","root_cause_category","fix_applied","prevention_steps"]
                   if not getattr(self, f, "").strip()]
        if missing:
            raise ValueError(f"Incomplete RCA. Missing fields: {missing}")

@app.get("/health")
async def health():
    queue_len = await redis_client.llen("signal_queue")
    return {"status": "ok", "queue_depth": queue_len, "timestamp": time.time()}

@app.post("/signal")
async def ingest_signal(signal: SignalPayload):
    if await rate_limiter.is_limited():
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    payload = {"component_id": signal.component_id, "message": signal.message,
                "metadata": signal.metadata, "timestamp": time.time()}
    await redis_client.lpush("signal_queue", json.dumps(payload))
    bucket = int(time.time() // 300) * 300
    async with pg_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO signal_stats (bucket, count) VALUES ($1, 1)
            ON CONFLICT (bucket) DO UPDATE SET count = signal_stats.count + 1
        """, bucket)
    return {"status": "queued", "component_id": signal.component_id}

@app.get("/incidents")
async def get_incidents():
    cached = await redis_client.get("dashboard:incidents")
    if cached:
        return json.loads(cached)
    async with pg_pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, component_id, severity, status, start_time, end_time, mttr_seconds, rca
            FROM incidents
            ORDER BY CASE severity WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 ELSE 2 END, id DESC
        """)
    result = [dict(r) for r in rows]
    await redis_client.setex("dashboard:incidents", 5, json.dumps(result, default=str))
    return result

@app.get("/signals/{incident_id}")
async def get_signals(incident_id: int):
    db = mongo_client["ims"]
    cursor = db.signals.find({"incident_id": incident_id}, {"_id": 0}).limit(100)
    return await cursor.to_list(length=100)

@app.post("/transition/{incident_id}")
async def transition(incident_id: int, body: TransitionPayload):
    async with pg_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT status FROM incidents WHERE id=$1", incident_id)
        if not row:
            raise HTTPException(status_code=404, detail="Incident not found")
        sm = WorkItemStateMachine(row["status"])
        try:
            old = sm.transition(body.status)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        await conn.execute("UPDATE incidents SET status=$1 WHERE id=$2", sm.status, incident_id)
    await redis_client.delete("dashboard:incidents")
    return {"message": f"{old} → {sm.status}"}

@app.post("/rca/{incident_id}")
async def submit_rca(incident_id: int, rca: RCAPayload):
    try:
        rca.validate_complete()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    async with pg_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT status, start_time FROM incidents WHERE id=$1", incident_id)
        if not row:
            raise HTTPException(status_code=404, detail="Incident not found")
        sm = WorkItemStateMachine(row["status"])
        try:
            sm.transition("CLOSED")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        end_time = time.time()
        mttr = end_time - row["start_time"]
        rca_json = json.dumps(rca.model_dump())
        await conn.execute("""
            UPDATE incidents SET status=$1, end_time=$2, mttr_seconds=$3, rca=$4 WHERE id=$5
        """, "CLOSED", end_time, mttr, rca_json, incident_id)
    await redis_client.delete("dashboard:incidents")
    return {"message": "Incident closed", "mttr_seconds": round(mttr, 2), "mttr_minutes": round(mttr/60, 2)}

@app.get("/stats")
async def stats():
    async with pg_pool.acquire() as conn:
        by_component = await conn.fetch("""
            SELECT component_id, severity, COUNT(*) as count, AVG(mttr_seconds) as avg_mttr
            FROM incidents GROUP BY component_id, severity ORDER BY count DESC
        """)
        timeseries = await conn.fetch("""
            SELECT bucket, count FROM signal_stats ORDER BY bucket DESC LIMIT 24
        """)
    return {"by_component": [dict(r) for r in by_component],
            "timeseries": [dict(r) for r in reversed(timeseries)]}
