import json, random, sys, time, urllib.request, urllib.error, argparse

API = "http://localhost:8000"

def post(path, data):
    body = json.dumps(data).encode()
    req = urllib.request.Request(f"{API}{path}", data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"error": e.code}
    except Exception as e:
        return {"error": str(e)}

def send(comp, msg, meta=None):
    r = post("/signal", {"component_id": comp, "message": msg, "metadata": meta or {}})
    print(f"  {'✅' if 'error' not in r else '⚠️ '} {comp}: {msg[:50]}")

def check_health():
    try:
        with urllib.request.urlopen(f"{API}/health", timeout=3) as resp:
            d = json.loads(resp.read())
            print(f"✅ Backend healthy. Queue: {d.get('queue_depth','?')}")
            return True
    except:
        print(f"❌ Backend not reachable at {API}\n   Run: docker compose up -d")
        return False

def scenario_rdbms():
    print("\n🔴 RDBMS Outage (P0)")
    for i in range(15):
        send("RDBMS_PRIMARY", f"Connection timeout attempt {i+1}", {"latency_ms": 5000})
        time.sleep(0.2)
    for i in range(5):
        send("RDBMS_REPLICA_01", "Replication lag critical", {"lag_seconds": 30+i*5})
        time.sleep(0.2)

def scenario_mcp():
    print("\n🟠 MCP Host Cascade (P1)")
    for host in ["MCP_HOST_01", "MCP_HOST_02"]:
        for i in range(8):
            send(host, "Health check failed", {"response_code": 503})
            time.sleep(0.15)

def scenario_cache():
    print("\n🟡 Cache Degradation (P2)")
    for i in range(10):
        send("CACHE_CLUSTER_01", "Cache miss rate elevated", {"hit_rate": max(0.1, 0.9-i*0.08)})
        time.sleep(0.3)

def scenario_volume():
    print("\n📈 High Volume Load (100 signals)")
    comps = ["RDBMS_PRIMARY","CACHE_CLUSTER_01","QUEUE_ASYNC_01","MCP_HOST_01","API_GATEWAY"]
    for i in range(100):
        send(random.choice(comps), f"Signal #{i+1}", {"index": i})
        time.sleep(0.05)

def scenario_full():
    print("\n💥 Full Stack Outage")
    for comp in ["RDBMS_PRIMARY","CACHE_CLUSTER_01","QUEUE_ASYNC_01","MCP_HOST_01","MCP_HOST_02","API_GATEWAY","NOSQL_MONGO_01"]:
        send(comp, "Critical failure", {"critical": True})
        time.sleep(0.1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=["rdbms","mcp","cache","volume","full","all"], default="all")
    args = parser.parse_args()
    print("🚀 IMS Simulator")
    if not check_health(): sys.exit(1)
    s = args.scenario
    if s in ("rdbms","all"): scenario_rdbms()
    if s in ("mcp","all"):   scenario_mcp()
    if s in ("cache","all"): scenario_cache()
    if s in ("volume","all"): scenario_volume()
    if s in ("full","all"):  scenario_full()
    print("\n✅ Done! Open http://localhost:3000")
