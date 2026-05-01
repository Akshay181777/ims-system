from __future__ import annotations
import json
import os
import sys
import time
import psycopg2
import redis
from pymongo import MongoClient

PG_HOST    = os.getenv("POSTGRES_HOST", "localhost")
MONGO_HOST = os.getenv("MONGO_HOST", "localhost")
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")

def connect_postgres():
    for attempt in range(30):
        try:
            conn = psycopg2.connect(dbname="ims_db", user="ims", password="ims", host=PG_HOST)
            conn.autocommit = False
            print("✅ Worker connected to PostgreSQL", flush=True)
            return conn
        except Exception as exc:
            print(f"⏳ Waiting for Postgres (attempt {attempt+1}): {exc}", flush=True)
            time.sleep(2)
    sys.exit("❌ Could not connect to Postgres")

def connect_redis():
    for attempt in range(15):
        try:
            r = redis.Redis(host=REDIS_HOST, port=6379, decode_responses=True)
            r.ping()
            print("✅ Worker connected to Redis", flush=True)
            return r
        except Exception:
            print(f"⏳ Waiting for Redis (attempt {attempt+1})…", flush=True)
            time.sleep(2)
    sys.exit("❌ Could not connect to Redis")

def get_severity(component_id: str) -> str:
    if "RDBMS" in component_id or "DB" in component_id:
        return "P0"
    if "CACHE" in component_id or "REDIS" in component_id:
        return "P2"
    return "P1"

def fire_alert(severity: str, incident_id: int, component_id: str):
    icons = {"P0": "🔴", "P1": "🟠", "P2": "🟡"}
    print(f"{icons.get(severity,'⚪')} [{severity}] Alert → Incident #{incident_id} | {component_id}", flush=True)

def create_incident(cur, pg, component_id: str, severity: str, now: float) -> int:
    for attempt in range(5):
        try:
            cur.execute(
                "INSERT INTO incidents (component_id, severity, status, start_time) VALUES (%s,%s,'OPEN',%s) RETURNING id",
                (component_id, severity, now))
            incident_id = cur.fetchone()[0]
            pg.commit()
            return incident_id
        except Exception as exc:
            pg.rollback()
            print(f"⚠️  DB write failed (attempt {attempt+1}): {exc}", flush=True)
            time.sleep(1)
    raise RuntimeError(f"Failed to create incident for {component_id}")

def main():
    pg    = connect_postgres()
    cur   = pg.cursor()
    r     = connect_redis()
    mongo = MongoClient(f"mongodb://{MONGO_HOST}:27017/")
    db    = mongo["ims"]

    cur.execute("""
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
    pg.commit()

    debounce: dict[str, dict] = {}
    count     = 0
    last_tick = time.time()

    print("🚀 Worker started — consuming signal_queue…", flush=True)

    while True:
        raw = r.rpop("signal_queue")
        if not raw:
            time.sleep(0.05)
        else:
            try:
                signal = json.loads(raw)
                comp   = signal["component_id"]
                now    = time.time()
                sev    = get_severity(comp)
                entry  = debounce.get(comp)
                if entry and (now - entry["time"]) < 10:
                    incident_id = entry["id"]
                else:
                    incident_id = create_incident(cur, pg, comp, sev, now)
                    debounce[comp] = {"id": incident_id, "time": now}
                    fire_alert(sev, incident_id, comp)
                db.signals.insert_one({
                    "component_id": comp,
                    "incident_id":  incident_id,
                    "severity":     sev,
                    "payload":      signal,
                    "ingested_at":  now,
                })
                count += 1
            except Exception as exc:
                print(f"❌ Worker error: {exc}", flush=True)

        elapsed = time.time() - last_tick
        if elapsed >= 5:
            print(f"📈 Throughput: {count/elapsed:.1f} signals/sec", flush=True)
            count     = 0
            last_tick = time.time()

if __name__ == "__main__":
    main()
