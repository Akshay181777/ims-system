# Prompts, Specs & Plans Used

## Objective
Build a production-style Incident Management System with:
- Async ingestion
- Queue-based processing  
- State machine lifecycle
- RCA + MTTR tracking
- Real-time dashboard

## Architecture Plan
1. FastAPI backend for ingestion and APIs
2. Redis queue for buffering signals
3. Worker to process signals asynchronously
4. PostgreSQL for structured incident storage
5. MongoDB for raw signal storage
6. React frontend for dashboard

## Design Decisions

### Why Redis?
- Decouples ingestion from processing
- Handles burst traffic up to 10,000 signals/sec

### Why Worker?
- Avoids blocking API
- Enables async processing with debounce logic

### Why PostgreSQL?
- Strong consistency for incident state transitions
- ACID guarantees for OPEN→INVESTIGATING→RESOLVED→CLOSED

### Why MongoDB?
- Flexible schema for raw signal payloads
- High-volume append-only writes (audit log)

## State Machine Design
OPEN → INVESTIGATING → RESOLVED → CLOSED
- Prevents invalid transitions
- Enforced via WorkItemStateMachine class in backend

## Alert Strategy Design (Strategy Pattern)
- P0AlertStrategy → RDBMS failures → PagerDuty + escalate
- P1AlertStrategy → API/Queue/MCP → Slack + Email
- P2AlertStrategy → Cache failures → Slack only

## RCA Design
Mandatory fields (all required, whitespace rejected):
- start_time
- end_time
- root_cause_category
- fix_applied
- prevention_steps

## MTTR Calculation
MTTR = end_time - start_time
Stored in PostgreSQL and shown in UI on closed incidents

## Backpressure Handling
1. Rate limiter on /signal (100 req/10s) — blocks floods at API
2. Redis queue absorbs bursts — API returns immediately after LPUSH
3. Worker drains at Postgres write speed — sustainable processing

## Challenges Faced
- Docker issues on Windows (path permission errors with /home)
- asyncpg incompatible with Python 3.14 alpha — solved by running tests inside Docker container
- State transition validation bugs — fixed by WorkItemStateMachine class

## Improvements (Future Work)
- Grafana dashboard for metrics visualization
- Prometheus metrics endpoint
- Kubernetes deployment with HPA
- AWS cloud deployment

## Conclusion
Built a distributed, production-style incident management system with:
- Async processing throughout
- Queue-based backpressure architecture  
- State-driven workflow with design patterns
- Real-time UI with MongoDB signal viewer
- 21 passing unit tests