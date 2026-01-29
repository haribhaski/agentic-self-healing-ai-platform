import asyncio
import json
import logging
import signal
import time
from datetime import datetime
import datetime as dt
import sys
import os
import psutil

sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))
from common.config import config
from common.logger import setup_logger
from common.kafka_utils import create_producer, create_consumer
from common.schemas import (
    IncidentType, IncidentStatus, AgentMetric, 
    Alert, PolicyRequest, PolicyDecision, ConfigUpdate
)
from backend.database.db_manager import DatabaseManager

logger = setup_logger("HealingAgent", config.kafka)

class HealingAgent:
    def __init__(self):
        self.config = config.get_agent_config("HealingAgent", 8006)
        self.producer = create_producer(self.config.kafka)
        self.db = DatabaseManager(self.config.database.connection_string)
        
        self.playbooks = {
            IncidentType.LATENCY_SLO_BREACH: self.handle_latency_breach,
            IncidentType.PERF_DROP: self.handle_performance_drop,
            IncidentType.DATA_DRIFT: self.handle_data_drift,
            IncidentType.AGENT_DOWN: self.handle_agent_down
        }
        
        self.running = True
        self.events_processed = 0
        self.last_latency = 0.0
        
        # Signal handling
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop = asyncio.get_event_loop()
                loop.add_signal_handler(sig, self.handle_shutdown)
            except NotImplementedError:
                pass
    
    def handle_shutdown(self):
        logger.info("Shutdown signal received...")
        self.running = False
        
    def handle_latency_breach(self, alert: Alert):
        incident_id = self.db.get_open_incident_by_type(IncidentType.LATENCY_SLO_BREACH)
        if not incident_id: return
        
        proposed_action = {
            "action_type": "ENABLE_SAFE_MODE",
            "config_changes": {"safe_mode": True, "reason": "Latency breach"},
            "expected_outcome": "Reduce latency < 300ms"
        }
        
        request = PolicyRequest(
            request_id=f"REQ-{int(time.time())}",
            incident_id=str(incident_id),
            incident_type=IncidentType.LATENCY_SLO_BREACH,
            proposed_action=proposed_action,
            timestamp=datetime.utcnow().isoformat()
        )
        self.producer.send('policy-requests', request.to_json())
        logger.info(f"Requested approval for SAFE_MODE (incident {incident_id})")
    
    def handle_performance_drop(self, alert: Alert):
        incident_id = self.db.get_open_incident_by_type(IncidentType.PERF_DROP)
        if not incident_id: return
        
        proposed_action = {
            "action_type": "ROLLBACK_MODEL",
            "config_changes": {"model_version": "previous"},
            "expected_outcome": "Restore accuracy > 0.8"
        }
        
        request = PolicyRequest(
            request_id=f"REQ-{int(time.time())}",
            incident_id=str(incident_id),
            incident_type=IncidentType.PERF_DROP,
            proposed_action=proposed_action,
            timestamp=datetime.utcnow().isoformat()
        )
        self.producer.send('policy-requests', request.to_json())
        logger.info(f"Requested approval for ROLLBACK (incident {incident_id})")

    def handle_data_drift(self, alert: Alert):
        incident_id = self.db.get_open_incident_by_type(IncidentType.DATA_DRIFT)
        if not incident_id: return
        
        proposed_action = {
            "action_type": "TRIGGER_RETRAINING",
            "config_changes": {"retrain": True},
            "expected_outcome": "Update model with new distribution"
        }
        
        request = PolicyRequest(
            request_id=f"REQ-{int(time.time())}",
            incident_id=str(incident_id),
            incident_type=IncidentType.DATA_DRIFT,
            proposed_action=proposed_action,
            timestamp=datetime.utcnow().isoformat()
        )
        self.producer.send('policy-requests', request.to_json())
        logger.info(f"Requested approval for RETRAINING (incident {incident_id})")

    def handle_agent_down(self, alert: Alert):
        incident_id = self.db.get_open_incident_by_type(IncidentType.AGENT_DOWN)
        if not incident_id: return
        
        proposed_action = {
            "action_type": "RESTART_AGENT",
            "config_changes": {"agent": alert.metrics_snapshot.get("agent"), "restart": True},
            "expected_outcome": "Agent resumes heartbeat"
        }
        
        request = PolicyRequest(
            request_id=f"REQ-{int(time.time())}",
            incident_id=str(incident_id),
            incident_type=IncidentType.AGENT_DOWN,
            proposed_action=proposed_action,
            timestamp=datetime.utcnow().isoformat()
        )
        self.producer.send('policy-requests', request.to_json())
        logger.info(f"Requested approval for RESTART (incident {incident_id})")

    def execute_action(self, decision: PolicyDecision):
        start_time = time.time()
        incident_id = decision.request_id # For simplicity mapping request_id to incident check
        # Actually request_id should be used to look up proposed action, but we can use incident_id if we store it
        
        # In this implementation, let's assume request_id lookup or similar
        # For demo purposes, we'll try to find the incident from the DB if needed
        # But we'll just log the action
        
        if decision.decision == "DENIED":
            logger.warning(f"Action DENIED for {decision.request_id}")
            return
        
        action = decision.approved_action
        if not action: return
        
        update = ConfigUpdate(
            update_id=f"CFG-{int(time.time())}",
            timestamp=datetime.utcnow().isoformat(),
            changed_by="HealingAgent",
            changes=action.get("config_changes", {}),
            reason=f"Approved action for request {decision.request_id}"
        )
        self.producer.send('config-updates', update.to_json())
        
        # We need the real incident_id to update the DB
        # Ideally PolicyDecision should contain incident_id
        # Let's assume we can find it or it's passed
        
        logger.info(f"Executed {action.get('action_type')} for {decision.request_id}")
        self.last_latency = (time.time() - start_time) * 1000
        self.events_processed += 1

    def process_message(self, topic: str, message: str):
        if not self.running: return
        try:
            self.events_processed += 1
            if topic == 'alerts':
                alert = Alert.from_json(message)
                logger.info(f"Processing alert: {alert.alert_type} ({alert.severity})")
                if alert.alert_type in self.playbooks:
                    self.playbooks[alert.alert_type](alert)
            elif topic == 'policy-decisions':
                decision = PolicyDecision.from_json(message)
                logger.info(f"Processing policy decision: {decision.request_id} -> {decision.decision}")
                self.execute_action(decision)
        except Exception as e:
            logger.error(f"Error processing message: {e}")

    async def heartbeat_loop(self):
        while self.running:
            try:
                process = psutil.Process()
                metric = AgentMetric(
                    agent="HealingAgent",
                    status="OK",
                    latency_ms=self.last_latency,
                    timestamp=datetime.utcnow().isoformat(),
                    cpu_percent=process.cpu_percent(),
                    memory_mb=process.memory_info().rss / 1024 / 1024,
                    events_processed=self.events_processed
                )
                self.producer.send('agent-metrics', metric.to_json())
                
                self.db.update_agent_health(
                    agent_name="HealingAgent",
                    status="OK",
                    latency_ms=metric.latency_ms,
                    cpu_percent=metric.cpu_percent,
                    memory_mb=metric.memory_mb,
                    events_processed=self.events_processed
                )
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
            await asyncio.sleep(self.config.heartbeat_interval_seconds)

    async def run(self):
        heartbeat_task = asyncio.create_task(self.heartbeat_loop())
        
        self.consumer = create_consumer(
            self.config.kafka,
            ['alerts', 'policy-decisions'],
            'healing-agent-group',
            self.process_message
        )
        
        logger.info("HealingAgent starting consumer...")
        try:
            await asyncio.get_event_loop().run_in_executor(None, self.consumer.start)
        finally:
            self.cleanup()
            heartbeat_task.cancel()

    def cleanup(self):
        logger.info("Cleaning up resources...")
        self.running = False
        if hasattr(self, 'consumer'): self.consumer.close()
        if hasattr(self, 'producer'):
            self.producer.flush()
            self.producer.close()
        logger.info("Shutdown complete")

if __name__ == "__main__":
    agent = HealingAgent()
    asyncio.run(agent.run())

