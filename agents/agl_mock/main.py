import asyncio
import json
import logging
from datetime import datetime
from kafka import KafkaConsumer, KafkaProducer
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))
from common.logger import setup_logger
from common.config import config

logger = setup_logger("AGL_Mock", config.kafka)

class AGLMock:
    """Mock AGL (Agentic Governance Layer) for auto-approving healing actions"""
    
    def __init__(self):
        self.config = config
        self.consumer = KafkaConsumer(
            'policy-requests',
            bootstrap_servers=self.config.kafka.bootstrap_servers,
            value_deserializer=lambda v: json.loads(v.decode('utf-8')),
            group_id='agl-mock-group'
        )
        
        self.producer = KafkaProducer(
            bootstrap_servers=self.config.kafka.bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
        
        self.policies = {
            "ENABLE_SAFE_MODE": "APPROVE",
            "ROLLBACK_MODEL": "APPROVE",
            "TRIGGER_RETRAINING": "APPROVE",
            "RESTART_AGENT": "APPROVE"
        }
    
    async def process_requests(self):
        """Auto-approve policy requests based on rules"""
        logger.info("AGL Mock started, auto-approving policy requests...")
        
        try:
            for message in self.consumer:
                try:
                    request = message.value
                    incident_id = request['incident_id']
                    proposed_action = request['proposed_action']
                    action_type = proposed_action['action_type']
                    
                    decision = self.policies.get(action_type, "DENY")
                    
                    policy_decision = {
                        "incident_id": incident_id,
                        "decision": decision,
                        "approved_action": proposed_action if decision == "APPROVE" else None,
                        "reason": f"Auto-{decision} by AGL policy",
                        "timestamp": datetime.utcnow().isoformat()
                    }
                    
                    self.producer.send('policy-decisions', policy_decision)
                    
                    logger.info(f"AGL Decision: {action_type} -> {decision} (incident {incident_id})")
                    
                except Exception as e:
                    logger.error(f"Error processing policy request: {e}")
        
        except KeyboardInterrupt:
            logger.info("Shutting down AGL Mock")
        finally:
            self.consumer.close()
            self.producer.close()

if __name__ == "__main__":
    agl = AGLMock()
    asyncio.run(agl.process_requests())
