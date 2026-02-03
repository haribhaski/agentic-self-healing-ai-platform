# Why Agents Show as "Idle" Even When Running

## Root Cause
The `AgentStatus.tsx` component marks an agent as **idle** if no metrics heartbeat is received within **20 seconds**:

```typescript
const alive = a.lastSeenMs > 0 && nowMs - a.lastSeenMs < 20000; // 20s threshold
return {
  ...a,
  status: alive ? "active" : "idle",
};
```

## Why This Happens

1. **Agents send heartbeats every 10 seconds** (config: `heartbeat_interval_seconds: int = 10`)
2. **Frontend checks every 1 second** if a heartbeat arrived in the last 20 seconds
3. **Network/Processing delays** between Kafka publishing → API streaming → Frontend receiving can exceed this window

### The Issue Chain:
```
Agent sends metric (every 10s)
    ↓
→ Published to Kafka "agent-metrics" topic
    ↓
→ API consumes from Kafka (lag: 0-2s)
    ↓
→ API streams via SSE to browser (lag: 0-1s)
    ↓
→ Frontend receives & updates lastSeenMs
    ↓
If any step is slow or delayed, the 20s window can expire!
```

## Why Agents Are Actually Working

Despite showing "idle", agents **are processing**:
- ✅ Kafka topics have messages flowing
- ✅ Event counts increase (12445000 events, 37400 predictions, etc.)
- ✅ Database is being updated
- ✅ Metrics ARE being sent every 10 seconds

## Solutions

### Option 1: Increase Heartbeat Frequency (Recommended)
Change `heartbeat_interval_seconds` from 10s to **5s** in [common/config.py](common/config.py):
```python
heartbeat_interval_seconds: int = 5  # Send metrics more frequently
```

### Option 2: Increase Idle Threshold
Change the 20-second threshold to 30+ seconds in [src/components/AgentStatus.tsx](src/components/AgentStatus.tsx):
```typescript
const alive = a.lastSeenMs > 0 && nowMs - a.lastSeenMs < 30000; // 30s instead of 20s
```

### Option 3: Reduce Heartbeat Delay in API
Optimize the Kafka consumer in [src/app/api/agent-metrics/route.ts](src/app/api/agent-metrics/route.ts) to process metrics faster

## Status Check

Run agents with: `bash run_all_agents.sh`
Stop agents with: `bash stop_all_agents.sh`

Then check:
- Frontend: http://localhost:3000 (Agent Status component)
- Kafka topic: `docker exec kafka kafka-console-consumer --bootstrap-server localhost:9092 --topic agent-metrics --from-beginning --max-messages 10`
