import asyncio
import json
import logging
from datetime import datetime
from kafka import KafkaConsumer, KafkaProducer
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))
from common.config import Config
from backend.database.db_manager import DatabaseManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("HealingAgent")

class HealingAgent:
    def __init__(self):
        self.config = Config()
        self.db = DatabaseManager()
        
        self.consumer = KafkaConsumer(
            'alerts',
            'policy-decisions',
            bootstrap_servers=self.config.KAFKA_BOOTSTRAP_SERVERS,
            value_deserializer=lambda v: json.loads(v.decode('utf-8')),
            group_id='healing-agent-group'
        )
        
        self.producer = KafkaProducer(
            bootstrap_servers=self.config.KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
        
        self.playbooks = {
            "LATENCY_SLO_BREACH": self.handle_latency_breach,
            "PERF_DROP": self.handle_performance_drop,
            "DATA_DRIFT": self.handle_data_drift,
            "AGENT_DOWN": self.handle_agent_down
        }
        
        self.pending_approvals = {}
    
    def handle_latency_breach(self, alert):
        """Playbook: Switch to SAFE_MODE (rule-based)"""
        incident_id = self.db.get_open_incident_by_type("LATENCY_SLO_BREACH")
        
        proposed_action = {
            "action_type": "ENABLE_SAFE_MODE",
            "config_changes": {
                "safe_mode": True,
                "reason": "Latency breach - switching to rule-based decisions"
            },
            "expected_outcome": "Reduce latency to < 300ms"
        }
        
        policy_request = {
            "incident_id": incident_id,
            "alert_type": alert['alert_type'],
            "proposed_action": proposed_action,
            "severity": alert['severity'],
            "timestamp": datetime.utcnow().isoformat()
        }
        
        self.producer.send('policy-requests', policy_request)
        self.pending_approvals[incident_id] = policy_request
        logger.info(f"Requesting AGL approval for SAFE_MODE (incident {incident_id})")
        
        return incident_id
    
    def handle_performance_drop(self, alert):
        """Playbook: Rollback to previous model version"""
        incident_id = self.db.get_open_incident_by_type("PERF_DROP")
        
        proposed_action = {
            "action_type": "ROLLBACK_MODEL",
            "config_changes": {
                "model_version": "previous",
                "reason": "Performance drop detected"
            },
            "expected_outcome": "Restore accuracy > 0.8"
        }
        
        policy_request = {
            "incident_id": incident_id,
            "alert_type": alert['alert_type'],
            "proposed_action": proposed_action,
            "severity": alert['severity'],
            "timestamp": datetime.utcnow().isoformat()
        }
        
        self.producer.send('policy-requests', policy_request)
        self.pending_approvals[incident_id] = policy_request
        logger.info(f"Requesting AGL approval for MODEL_ROLLBACK (incident {incident_id})")
        
        return incident_id
    
    def handle_data_drift(self, alert):
        """Playbook: Trigger retraining"""
        incident_id = self.db.get_open_incident_by_type("DATA_DRIFT")
        
        proposed_action = {
            "action_type": "TRIGGER_RETRAINING",
            "config_changes": {
                "retrain": True,
                "reason": "Data drift detected"
            },
            "expected_outcome": "Update model with new data distribution"
        }
        
        policy_request = {
            "incident_id": incident_id,
            "alert_type": alert['alert_type'],
            "proposed_action": proposed_action,
            "severity": alert['severity'],
            "timestamp": datetime.utcnow().isoformat()
        }
        
        self.producer.send('policy-requests', policy_request)
        self.pending_approvals[incident_id] = policy_request
        logger.info(f"Requesting AGL approval for RETRAINING (incident {incident_id})")
        
        return incident_id
    
    def handle_agent_down(self, alert):
        """Playbook: Request agent restart"""
        incident_id = self.db.get_open_incident_by_type("AGENT_DOWN")
        
        proposed_action = {
            "action_type": "RESTART_AGENT",
            "config_changes": {
                "agent": alert.get('agent'),
                "restart": True,
                "reason": "Agent heartbeat missing"
            },
            "expected_outcome": "Agent resumes heartbeat"
        }
        
        policy_request = {
            "incident_id": incident_id,
            "alert_type": alert['alert_type'],
            "proposed_action": proposed_action,
            "severity": alert['severity'],
            "timestamp": datetime.utcnow().isoformat()
        }
        
        self.producer.send('policy-requests', policy_request)
        self.pending_approvals[incident_id] = policy_request
        logger.info(f"Requesting AGL approval for AGENT_RESTART (incident {incident_id})")
        
        return incident_id
    
    def execute_action(self, decision):
        """Execute approved healing action"""
        incident_id = decision['incident_id']
        agl_decision = decision['decision']
        
        if agl_decision == "DENY":
            logger.warning(f"Action DENIED by AGL for incident {incident_id}")
            self.db.update_incident_status(incident_id, "OPEN")
            return
        
        action = decision['approved_action']
        action_type = action['action_type']
        config_changes = action['config_changes']
        
        config_update = {
            "incident_id": incident_id,
            "action_type": action_type,
            "config_changes": config_changes,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        self.producer.send('config-updates', config_update)
        
        self.db.log_healing_action(
            incident_id=incident_id,
            action_type=action_type,
            action_details=config_changes,
            agl_decision=agl_decision
        )
        
        self.db.update_incident_status(incident_id, "MITIGATING")
        
        logger.info(f"Executed {action_type} for incident {incident_id}")
        
        self.db.store_memory(
            incident_type=action_type,
            action_taken=action,
            outcome="EXECUTED",
            metadata={"incident_id": incident_id}
        )
    
    async def process_alerts(self):
        """Process alerts and policy decisions"""
        logger.info("HealingAgent started, consuming from alerts and policy-decisions")
        
        try:
            for message in self.consumer:
                try:
                    if message.topic == 'alerts':
                        alert = message.value
                        alert_type = alert['alert_type']
                        
                        if alert_type in self.playbooks:
                            logger.info(f"Handling alert: {alert_type}")
                            self.playbooks[alert_type](alert)
                        else:
                            logger.warning(f"No playbook for alert type: {alert_type}")
                    
                    elif message.topic == 'policy-decisions':
                        decision = message.value
                        self.execute_action(decision)
                    
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
        
        except KeyboardInterrupt:
            logger.info("Shutting down HealingAgent")
        finally:
            self.consumer.close()
            self.producer.close()

if __name__ == "__main__":
    agent = HealingAgent()
    asyncio.run(agent.process_alerts())
