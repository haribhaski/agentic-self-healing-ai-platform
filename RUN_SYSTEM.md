# 🚀 Self-Healing Agentic AI Platform - Complete Setup Guide

## Architecture Overview

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│ Ingestion   │────▶│ Feature      │────▶│ Model       │
│ Agent       │     │ Agent        │     │ Agent       │
└─────────────┘     └──────────────┘     └─────────────┘
                                               │
                    ┌──────────────┐           │
                    │ Monitoring   │           ▼
                    │ Agent        │     ┌─────────────┐
                    └──────────────┘     │ Decision    │
                          │              │ Agent       │
                          │              └─────────────┘
                          ▼
                    ┌──────────────┐
                    │ Healing      │◀────┐
                    │ Agent        │     │
                    └──────────────┘     │
                          │              │
                          ▼              │
                    ┌──────────────┐     │
                    │ AGL Mock     │─────┘
                    └──────────────┘
```

## Step 1: Start Infrastructure

```bash
cd infra
docker-compose up -d

# Wait 30 seconds for services to initialize
sleep 30

# Create Kafka topics
chmod +x kafka-topics.sh
./kafka-topics.sh
```

**Verify services:**
- Kafka: http://localhost:9092
- PostgreSQL: localhost:5432
- MLflow: http://localhost:5000
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3001 (admin/admin)

## Step 2: Setup Python Environment

```bash
cd ..
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

pip install -r backend/requirements.txt
```

## Step 3: Initialize Database

```bash
python -c "from backend.database.db_manager import DatabaseManager; DatabaseManager().create_tables()"
```

This creates:
- `incidents` - tracks all failure events
- `healing_actions` - logs healing attempts
- `config_history` - version control for configs
- `memory_chunks` - learning memory for faster healing

## Step 4: Train Initial Model

```bash
cd mlops
python train.py
```

This generates synthetic credit risk data and trains a Random Forest model in MLflow.

**Verify:** Visit http://localhost:5000 to see the model in MLflow UI.

## Step 5: Start All Agents

Open 7 terminal windows and run:

### Terminal 1: Ingestion Agent
```bash
source venv/bin/activate
python agents/ingestion_agent/main.py
```

### Terminal 2: Feature Agent
```bash
source venv/bin/activate
python agents/feature_agent/main.py
```

### Terminal 3: Model Agent
```bash
source venv/bin/activate
python agents/model_agent/main.py
```

### Terminal 4: Decision Agent
```bash
source venv/bin/activate
python agents/decision_agent/main.py
```

### Terminal 5: Monitoring Agent
```bash
source venv/bin/activate
python agents/monitoring_agent/main.py
```

### Terminal 6: Healing Agent
```bash
source venv/bin/activate
python agents/healing_agent/main.py
```

### Terminal 7: AGL Mock (auto-approves healing actions)
```bash
source venv/bin/activate
python agents/agl_mock/main.py
```

## Step 6: Run Healing Simulations

### Simulation 1: Latency Spike Healing

Open a new terminal:

```bash
source venv/bin/activate
python experiments/simulate_latency_spike.py
```

**What happens:**
1. 🔴 Injects 2000ms latency into ModelAgent
2. 📊 MonitoringAgent detects `LATENCY_SLO_BREACH`
3. 🔧 HealingAgent proposes `ENABLE_SAFE_MODE`
4. ✅ AGL approves
5. ⚡ System switches to rule-based (fast) decisions
6. 📈 Latency drops back to < 300ms

**Verify healing:**
```bash
# Check incidents table
psql -h localhost -U aura_user -d aura_db -c "SELECT * FROM incidents WHERE incident_type='LATENCY_SLO_BREACH';"

# Check healing actions
psql -h localhost -U aura_user -d aura_db -c "SELECT * FROM healing_actions ORDER BY executed_at DESC LIMIT 5;"
```

### Simulation 2: Data Drift Healing

```bash
python experiments/simulate_data_drift.py
```

**What happens:**
1. 📊 Establishes baseline (credit score mean=700)
2. 🔴 Injects drift (credit score mean=550)
3. 📊 MonitoringAgent detects `DATA_DRIFT`
4. 🔧 HealingAgent proposes `TRIGGER_RETRAINING`
5. ✅ AGL approves
6. 🎯 System triggers model retraining

## Step 7: Verify Self-Healing

### Check Kafka Topics

```bash
# List all topics
docker exec -it kafka kafka-topics --bootstrap-server localhost:9092 --list

# View alerts
docker exec -it kafka kafka-console-consumer --bootstrap-server localhost:9092 --topic alerts --from-beginning --max-messages 10

# View policy requests
docker exec -it kafka kafka-console-consumer --bootstrap-server localhost:9092 --topic policy-requests --from-beginning --max-messages 10

# View policy decisions
docker exec -it kafka kafka-console-consumer --bootstrap-server localhost:9092 --topic policy-decisions --from-beginning --max-messages 10
```

### Check Database

```bash
# Connect to PostgreSQL
psql -h localhost -U aura_user -d aura_db

# View all incidents
SELECT incident_id, incident_type, status, detected_at FROM incidents ORDER BY detected_at DESC LIMIT 10;

# View healing actions
SELECT incident_id, action_type, agl_decision, executed_at FROM healing_actions ORDER BY executed_at DESC LIMIT 10;

# Calculate MTTR (Mean Time To Recover)
SELECT 
  incident_type,
  AVG(EXTRACT(EPOCH FROM (resolved_at - detected_at))) as mttr_seconds
FROM incidents 
WHERE status = 'RESOLVED'
GROUP BY incident_type;
```

## Self-Healing Scenarios Implemented

| Failure Type | Detection | Healing Action | MTTR Target |
|--------------|-----------|----------------|-------------|
| **Latency SLO Breach** | Median latency > 300ms | Switch to SAFE_MODE (rule-based) | < 60s |
| **Performance Drop** | Accuracy < 0.8 | Rollback to previous model | < 120s |
| **Data Drift** | PSI > 0.2 | Trigger retraining | < 300s |
| **Agent Down** | Heartbeat missing 30s+ | Request agent restart | < 60s |

## Metrics to Track

1. **MTTR (Mean Time To Recovery)**
   - Time from detection to resolution
   - Target: < 60s for latency, < 120s for performance

2. **Healing Success Rate**
   - % of incidents resolved automatically
   - Target: > 95%

3. **False Positive Rate**
   - % of unnecessary healing actions
   - Target: < 5%

4. **Latency SLO Compliance**
   - % of requests < 300ms
   - Target: > 99%

## Troubleshooting

### Kafka not connecting
```bash
docker-compose down
docker-compose up -d
sleep 30
./kafka-topics.sh
```

### PostgreSQL connection errors
```bash
docker exec -it postgres psql -U aura_user -d aura_db -c "\dt"
```

### MLflow not loading model
```bash
# Check MLflow is running
curl http://localhost:5000

# Retrain model
python mlops/train.py
```

### Agents not receiving messages
```bash
# Check Kafka consumer groups
docker exec -it kafka kafka-consumer-groups --bootstrap-server localhost:9092 --list

# Check consumer lag
docker exec -it kafka kafka-consumer-groups --bootstrap-server localhost:9092 --describe --group ingestion-agent-group
```

## Next Steps

1. **Add LangGraph** for complex agent orchestration
2. **Real Kubernetes integration** (replace mock restart)
3. **Advanced AGL** with LLM-based policy decisions
4. **Frontend dashboard** (Next.js) for real-time visualization
5. **Prometheus metrics** export from agents

## Architecture Highlights

✅ **6 Autonomous Agents** (Ingestion, Feature, Model, Decision, Monitoring, Healing)  
✅ **Kafka Event Streaming** (11 topics for complete observability)  
✅ **PostgreSQL State Management** (incidents, actions, config, memory)  
✅ **MLflow MLOps** (model versioning, rollback, retraining)  
✅ **AGL Governance** (policy approval layer)  
✅ **Self-Healing Playbooks** (4 scenarios with MTTR tracking)  
✅ **Memory Storage** (learns from past incidents)  
✅ **Full Observability** (Prometheus + Grafana ready)

## Demo Script for Viva

1. Show running infrastructure (docker ps)
2. Show all 7 agents running in terminals
3. Run latency spike simulation
4. Show Monitoring Agent detecting breach
5. Show Healing Agent proposing action
6. Show AGL approving
7. Show latency returning to normal
8. Query database to show incident RESOLVED
9. Show MTTR calculation
10. Show memory storage for future healing

**This proves complete self-healing: detection → proposal → approval → execution → verification → learning**
