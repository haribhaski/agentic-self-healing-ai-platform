# Self-Healing Agentic AI Platform - Backend

Complete implementation of a production-grade self-healing AI system with Kafka, LangGraph agents, MLflow, and autonomous healing capabilities.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    AGENTIC AI LAYER                         │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌──────────┐  │
│  │Ingestion │→ │ Feature  │→ │   Model   │→ │ Decision │  │
│  │  Agent   │  │  Agent   │  │   Agent   │  │  Agent   │  │
│  └──────────┘  └──────────┘  └───────────┘  └──────────┘  │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│              KAFKA STREAMING LAYER                          │
│  raw-events → features → predictions → decisions            │
│  agent-metrics | feedback | alerts | policy-* | config-*   │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│         SELF-HEALING LAYER (AGL + Memory)                   │
│  ┌──────────────┐         ┌─────────────┐                  │
│  │  Monitoring  │→ Alert →│   Healing   │→ Config Update   │
│  │    Agent     │         │    Agent    │                  │
│  └──────────────┘         └─────────────┘                  │
│         ↓                        ↓                          │
│  ┌──────────────────────────────────────────┐              │
│  │  AGL Policy Engine + Memory Store        │              │
│  └──────────────────────────────────────────┘              │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│              DATABASE (PostgreSQL + ORM)                    │
│  incidents | healing_actions | config_history | memory     │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Start Infrastructure

```bash
cd infra
chmod +x kafka-topics.sh
docker-compose up -d
./kafka-topics.sh
```

This starts:
- Kafka + Zookeeper
- PostgreSQL
- MLflow
- Prometheus + Grafana

### 2. Install Python Dependencies

```bash
pip install kafka-python sqlalchemy psycopg2-binary mlflow psutil numpy scikit-learn langgraph langchain
```

### 3. Initialize Database

```bash
python -c "from backend.database.models import init_db; init_db('postgresql://agentic_user:agentic_pass@localhost:5432/agentic_db')"
```

### 4. Start Agents

Open 6 terminal windows:

```bash
# Terminal 1
python agents/ingestion_agent/main.py

# Terminal 2  
python agents/feature_agent/main.py

# Terminal 3
python agents/model_agent/main.py

# Terminal 4
python agents/decision_agent/main.py

# Terminal 5
python agents/monitoring_agent/main.py

# Terminal 6
python agents/healing_agent/main.py
```

### 5. Simulate Failures

```bash
# Inject latency spike
python experiments/simulate_latency_spike.py

# Watch healing happen automatically in logs
# Check incidents table
psql postgresql://agentic_user:agentic_pass@localhost:5432/agentic_db -c "SELECT * FROM incidents;"
```

## Healing Scenarios Implemented

### Scenario 1: Latency SLO Breach
**Trigger:** ModelAgent inference > 300ms for 100 events  
**Detection:** MonitoringAgent tracks end-to-end latency  
**Action:** Enable SAFE_MODE (skip model, use rules)  
**Verification:** Latency drops below 300ms  
**MTTR:** ~15-30 seconds

### Scenario 2: Model Performance Drop
**Trigger:** Accuracy < 0.75 for 200 feedback events  
**Detection:** MonitoringAgent computes rolling accuracy  
**Action:** Rollback to previous model version  
**Verification:** Accuracy returns above threshold  
**MTTR:** ~20-40 seconds

### Scenario 3: Agent Down
**Trigger:** Missing heartbeat for 30 seconds  
**Detection:** MonitoringAgent checks agent-metrics topic  
**Action:** Publish restart_request  
**Verification:** Heartbeat resumes  
**MTTR:** ~10-20 seconds

### Scenario 4: Data Drift
**Trigger:** PSI/KS drift score > 0.2  
**Detection:** MonitoringAgent compares feature distributions  
**Action:** Reduce threshold + trigger retraining  
**Verification:** Drift score decreases  
**MTTR:** ~30-60 seconds

## Healing Process (7 Steps)

1. **Detection:** MonitoringAgent identifies anomaly
2. **Logging:** Incident created in DB + published to incident-log
3. **Planning:** HealingAgent selects playbook action
4. **Approval:** AGL evaluates policy constraints
5. **Execution:** Config update or model rollback
6. **Verification:** Metrics checked post-action
7. **Memory:** Stored for future faster healing

## Database Schema

### incidents
- `incident_id` (PK)
- `type` (ENUM: DATA_DRIFT, PERF_DROP, LATENCY_SLO_BREACH, AGENT_DOWN)
- `detected_at`, `resolved_at`
- `status` (ENUM: OPEN, MITIGATING, RESOLVED, FAILED)
- `metrics_snapshot` (JSON)
- `mttr_seconds`

### healing_actions
- `action_id` (PK)
- `incident_id` (FK)
- `proposed_action` (JSON)
- `agl_decision` (ENUM: APPROVED, DENIED, MODIFIED)
- `approved_action` (JSON)
- `executed_at`
- `result` (ENUM: SUCCESS, FAIL)

### config_history
- `config_id` (PK)
- `changed_by`
- `changes` (JSON)
- `reason`
- `incident_id`

### memory_chunks
- `memory_id` (PK)
- `incident_type`
- `incident_summary`, `action_taken`, `outcome`
- `metrics_before`, `metrics_after`
- `mttr_seconds`

## Kafka Topics

| Topic | Purpose | Producer | Consumer |
|-------|---------|----------|----------|
| raw-events | Ingested events | IngestionAgent | FeatureAgent |
| features | Feature vectors | FeatureAgent | ModelAgent |
| predictions | Model outputs | ModelAgent | DecisionAgent |
| decisions | Final decisions | DecisionAgent | - |
| agent-metrics | Heartbeats | All agents | MonitoringAgent |
| feedback | Ground truth | Simulator | MonitoringAgent |
| alerts | Anomalies | MonitoringAgent | HealingAgent |
| policy-requests | Healing proposals | HealingAgent | AGLAgent |
| policy-decisions | AGL approvals | AGLAgent | HealingAgent |
| config-updates | Config changes | HealingAgent | All agents |
| incident-log | Incident records | HealingAgent | - |

## Checking Healing

### Via Database
```sql
-- Check incidents
SELECT incident_id, type, status, mttr_seconds, detected_at, resolved_at 
FROM incidents ORDER BY detected_at DESC LIMIT 10;

-- Check actions
SELECT a.action_id, a.incident_id, a.agl_decision, a.result
FROM healing_actions a JOIN incidents i ON a.incident_id = i.incident_id
ORDER BY a.created_at DESC LIMIT 10;

-- Average MTTR
SELECT type, AVG(mttr_seconds) as avg_mttr, COUNT(*) as count
FROM incidents WHERE status = 'RESOLVED'
GROUP BY type;
```

### Via Logs
```bash
# Watch healing in real-time
tail -f agents/healing_agent/healing.log | grep "RESOLVED"
tail -f agents/monitoring_agent/monitoring.log | grep "ALERT"
```

### Via Kafka
```bash
# Read alerts
kafka-console-consumer --bootstrap-server localhost:29092 --topic alerts --from-beginning

# Read incident logs
kafka-console-consumer --bootstrap-server localhost:29092 --topic incident-log --from-beginning
```

## Demo Script for Viva

```bash
# 1. Start all agents (show 6 terminals)
# 2. Show normal metrics: latency ~100ms, accuracy ~0.9
# 3. Press 1 to inject latency spike
python experiments/demo_controller.py

# 4. Show:
#    - Alert appears in Kafka alerts topic
#    - Incident created in DB (OPEN status)
#    - HealingAgent proposes safe_mode=1
#    - AGL approves
#    - Config updated
#    - Latency drops back to ~100ms
#    - Incident marked RESOLVED

# 5. Query DB to show:
SELECT * FROM incidents WHERE type = 'LATENCY_SLO_BREACH' ORDER BY detected_at DESC LIMIT 1;
SELECT * FROM config_history ORDER BY created_at DESC LIMIT 1;
SELECT * FROM memory_chunks ORDER BY created_at DESC LIMIT 1;
```

## Future Work (Mentioned in Code Comments)

- Actual Kubernetes restarts via API
- Multi-playbook escalation chains
- Reinforcement learning for action selection
- Distributed tracing with OpenTelemetry
- Advanced drift detection (Kolmogorov-Smirnov, Jensen-Shannon)
- Model A/B testing framework
- Cost-aware healing decisions

## Metrics Exposed

Each agent exposes Prometheus metrics on ports 8001-8006:
- `events_processed_total`
- `processing_latency_seconds`
- `errors_total`

Access Grafana at http://localhost:3001 (admin/admin)

## Project Structure

```
self-healing-agentic-platform/
├─ infra/
│   ├─ docker-compose.yml
│   ├─ kafka-topics.sh
│   └─ prometheus.yml
├─ agents/
│   ├─ ingestion_agent/main.py
│   ├─ feature_agent/main.py
│   ├─ model_agent/main.py
│   ├─ decision_agent/main.py
│   ├─ monitoring_agent/main.py
│   └─ healing_agent/main.py
├─ backend/
│   └─ database/
│       ├─ models.py
│       └─ db_manager.py
├─ common/
│   ├─ kafka_utils.py
│   ├─ config.py
│   └─ schemas.py
├─ mlops/
│   ├─ train.py
│   └─ retrain.py
├─ experiments/
│   ├─ simulate_latency_spike.py
│   ├─ simulate_data_drift.py
│   ├─ simulate_agent_down.py
│   └─ demo_controller.py
└─ docs/
    ├─ architecture.md
    └─ evaluation_plan.md
```

## Environment Variables

Create `.env`:
```bash
KAFKA_BOOTSTRAP_SERVERS=localhost:29092
DB_HOST=localhost
DB_PORT=5432
DB_USER=agentic_user
DB_PASSWORD=agentic_pass
DB_NAME=agentic_db
MLFLOW_TRACKING_URI=http://localhost:5000
```
