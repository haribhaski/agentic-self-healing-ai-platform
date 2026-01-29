import asyncio
import json
import logging
from datetime import datetime
from kafka import KafkaConsumer, KafkaProducer
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))
from common.config import Config

from common.logger import setup_logger
from common.config import config

logger = setup_logger("DecisionAgent", config.kafka)

class DecisionAgent:
    def __init__(self):
        self.config = config
        self.consumer = KafkaConsumer(
            'predictions',
            bootstrap_servers=self.config.kafka.bootstrap_servers,
            value_deserializer=lambda v: json.loads(v.decode('utf-8')),
            group_id='decision-agent-group'
        )
        self.producer = KafkaProducer(
            bootstrap_servers=self.config.kafka.bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
    
    def make_decision(self, prediction_data):
        """Make business decision based on prediction"""
        risk_score = prediction_data.get('confidence', 0.0)
        risk_class = prediction_data.get('prediction', 'UNKNOWN')
        
        if risk_class == "HIGH_RISK":
            action = "REJECT"
            reason = f"High risk score {risk_score:.3f}"
        elif risk_class == "MEDIUM_RISK":
            action = "MANUAL_REVIEW"
            reason = f"Medium risk score {risk_score:.3f}, requires review"
        else:
            action = "APPROVE"
            reason = f"Low risk score {risk_score:.3f}"
        
        return action, reason
    
    def send_heartbeat(self):
        """Send agent health metrics"""
        heartbeat = {
            "agent": "DecisionAgent",
            "status": "OK",
            "timestamp": datetime.utcnow().isoformat()
        }
        self.producer.send('agent-metrics', heartbeat)
    
    async def process_predictions(self):
        """Process predictions and make decisions"""
        logger.info("DecisionAgent started, consuming from predictions")
        
        heartbeat_task = asyncio.create_task(self.heartbeat_loop())
        
        try:
            for message in self.consumer:
                try:
                    prediction_data = message.value
                    trace_id = prediction_data.get('trace_id', 'UNKNOWN')
                    
                    action, reason = self.make_decision(prediction_data)
                    
                    decision_event = {
                        "trace_id": trace_id,
                        "action": action,
                        "reason": reason,
                        "risk_score": prediction_data.get('confidence', 0.0),
                        "model_version": prediction_data.get('model_version', 'UNKNOWN'),
                        "timestamp": datetime.utcnow().isoformat()
                    }
                    
                    self.producer.send('decisions', decision_event)
                    
                    logger.info(f"Decision: {trace_id} -> {action} ({reason})")
                    
                except Exception as e:
                    logger.error(f"Error processing prediction: {e}")
                    
        except KeyboardInterrupt:
            logger.info("Shutting down DecisionAgent")
        finally:
            heartbeat_task.cancel()
            self.consumer.close()
            self.producer.close()
    
    async def heartbeat_loop(self):
        """Send periodic heartbeats"""
        while True:
            self.send_heartbeat()
            await asyncio.sleep(10)

if __name__ == "__main__":
    agent = DecisionAgent()
    asyncio.run(agent.process_predictions())
