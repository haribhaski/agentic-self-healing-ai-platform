import asyncio
import json
import logging
import time
import psutil
from datetime import datetime
from kafka import KafkaConsumer, KafkaProducer
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))
from common.logger import setup_logger
from common.config import config
from common.schemas import PolicyDecision, AGLDecision, AgentMetric

logger = setup_logger("AGL_Mock", config.kafka)

class AGLMock:
    """Mock AGL (Agentic Governance Layer) for auto-approving healing actions"""
    
    def __init__(self):
        self.config = config
        self.events_processed = 0
        self.running = True
        
        # Process metrics
        self.process = psutil.Process()
        self.process.cpu_percent()
        
        self.consumer = KafkaConsumer(
            'policy-requests',
            bootstrap_servers=self.config.kafka.bootstrap_servers,
            value_deserializer=lambda v: json.loads(v.decode('utf-8')),
            group_id='agl-mock-group'
        )
        
        self.producer = KafkaProducer(
            bootstrap_servers=self.config.kafka.bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode('utf-8') if isinstance(v, dict) else v
        )
        
        self.policies = {
            "ENABLE_SAFE_MODE": "APPROVED",
            "ROLLBACK_MODEL": "APPROVED",
            "TRIGGER_RETRAINING": "APPROVED",
            "RESTART_AGENT": "APPROVED"
        }
        
        # Signal handling (only in main thread)
        import threading
        if threading.current_thread() is threading.main_thread():
            import signal
            signal.signal(signal.SIGINT, self.handle_shutdown)
            signal.signal(signal.SIGTERM, self.handle_shutdown)
        
        # Start heartbeat thread
        threading.Thread(target=self._heartbeat_loop, daemon=True).start()
        
        logger.info("✓ AGL_Mock initialized - ready to approve policy requests")

    def handle_shutdown(self, signum, frame):
        logger.info("Shutdown signal received...")
        self.running = False
        self.consumer.close()
        self.producer.close()
        exit(0)
    
    def _heartbeat_loop(self):
        """Send periodic heartbeats"""
        while self.running:
            try:
                metric = AgentMetric(
                    agent="AGL_Mock",
                    status="OK",
                    latency_ms=0.0,
                    timestamp=datetime.utcnow().isoformat(),
                    cpu_percent=self.process.cpu_percent(),
                    memory_mb=self.process.memory_info().rss / 1024 / 1024,
                    events_processed=self.events_processed
                )
                self.producer.send('agent-metrics', metric.to_json().encode('utf-8'))
                self.producer.flush()
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
            
            time.sleep(5)  # Send every 5 seconds

    async def process_requests(self):
        """Auto-approve policy requests based on rules"""
        logger.info("🚀 AGL Mock started, auto-approving policy requests...")
        logger.info("📋 Waiting for messages on 'policy-requests' topic...")
        
        try:
            for message in self.consumer:
                if not self.running:
                    break
                    
                try:
                    request = message.value
                    incident_id = request['incident_id']
                    proposed_action = request['proposed_action']
                    action_type = proposed_action['action_type']
                    
                    decision_str = self.policies.get(action_type, "DENIED")
                    decision_enum = AGLDecision(decision_str)
                    
                    policy_decision = PolicyDecision(
                        request_id=request['request_id'],
                        incident_id=incident_id,
                        decision=decision_enum,
                        approved_action=proposed_action if decision_enum == AGLDecision.APPROVED else None,
                        timestamp=datetime.utcnow().isoformat(),
                        reasoning=f"Auto-{decision_enum.value} by AGL policy"
                    )
                    
                    # Ensure correct serialization for HealingAgent compatibility
                    self.producer.send('policy-decisions', policy_decision.to_json().encode('utf-8'))
                    self.producer.flush()
                    
                    self.events_processed += 1
                    
                    logger.info(f"✓ AGL Decision: {action_type} -> {decision_enum.value} (incident {incident_id})")
                    
                    if self.events_processed % 10 == 0:
                        logger.info(f"📊 Processed {self.events_processed} policy requests")
                        
                except Exception as e:
                    logger.error(f"Error processing policy request: {e}", exc_info=True)
        except KeyboardInterrupt:
            logger.info("Shutting down AGL Mock")
        finally:
            self.consumer.close()
            self.producer.close()

if __name__ == "__main__":
    agl = AGLMock()
    asyncio.run(agl.process_requests())