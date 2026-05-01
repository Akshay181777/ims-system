# IMS Project – Build Notes / Prompts / Plan

## Objective
Build a production-style Incident Management System with:
- Async ingestion
- Queue-based processing
- State machine lifecycle
- RCA + MTTR tracking
- Real-time dashboard

---

## Architecture Plan
1. FastAPI backend for ingestion and APIs
2. Redis queue for buffering signals
3. Worker to process signals asynchronously
4. PostgreSQL for structured incident storage
5. MongoDB for raw signal storage
6. React frontend for dashboard

---

## Design Decisions

### Why Redis?
- Decouples ingestion from processing
- Handles burst traffic

### Why Worker?
- Avoid blocking API
- Enables async processing

### Why PostgreSQL?
- Strong consistency for incidents

### Why MongoDB?
- Flexible storage for raw signals

---

## State Machine Design
OPEN → INVESTIGATING → RESOLVED → CLOSED

- Prevents invalid transitions
- Enforced in backend

---

## RCA Design
Mandatory fields:
- start_time
- end_time
- root_cause_category
- fix_applied
- prevention_steps

---

## MTTR Calculation
MTTR = end_time - start_time

Stored in PostgreSQL and shown in UI

---

## Challenges Faced
- Docker issues on Windows (WSL crash)
- Image build failures
- State transition validation bugs

---

## Improvements (Future Work)
- Grafana dashboard
- Prometheus metrics
- Kubernetes deployment
- AWS cloud deployment

---

## Conclusion
Built a distributed, production-style incident management system with:
- Async processing
- Queue-based architecture
- State-driven workflow
- Real-time UI