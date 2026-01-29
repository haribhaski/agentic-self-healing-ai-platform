import asyncio
import json
import logging
import signal
import time
from datetime import datetime
import sys
import os
import psutil

sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))
from common.config import config
from common.logger import setup_logger
from common.kafka_utils import create_producer, create_consumer
from common.schemas import Prediction, Decision, AgentMetric
from backend.database.db_manager import DatabaseManager

logger = setup_logger("DecisionAgent", config.kafka)

class DecisionAgent:
    def __init__(self):
        self.config = config.get_agent_config("DecisionAgent", 8004)
        self.producer = create_producer(self.config.kafka)
        self.db = DatabaseManager(self.config.database.connection_string)
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
        
    def make_decision(self, prediction: Prediction):
        start_time = time.time()
        risk_score = prediction.confidence
        risk_class = prediction.prediction
        
        if risk_class == "HIGH_RISK":
            action = "REJECT"
            reason = f"High risk score {risk_score:.3f}"
        elif risk_class == "MEDIUM_RISK":
            action = "MANUAL_REVIEW"
            reason = f"Medium risk score {risk_score:.3f}, requires review"
        else:
            action = "APPROVE"
            reason = f"Low risk score {risk_score:.3f}"
        
        latency = (time.time() - start_time) * 1000
        return action, reason, latency
    
    def process_message(self, topic: str, message: str):
        if not self.running:
            return
            
        try:
            prediction = Prediction.from_json(message)
            action, reason, latency = self.make_decision(prediction)
            self.last_latency = latency
            
            decision = Decision(
                trace_id=prediction.trace_id,
                timestamp=datetime.utcnow().isoformat(),
                decision=action,
                reasoning=reason,
                confidence=prediction.confidence,
                metadata={"model_version": prediction.model_version}
            )
            
            self.producer.send('decisions', decision.to_json())
            self.events_processed += 1
            
            if self.events_processed % 100 == 0:
                logger.info(f"Processed {self.events_processed} decisions")
            
        except Exception as e:
            logger.error(f"Error processing prediction: {e}", exc_info=True)

    async def heartbeat_loop(self):
        while self.running:
            try:
                process = psutil.Process()
                metric = AgentMetric(
                    agent="DecisionAgent",
                    status="OK",
                    latency_ms=self.last_latency,
                    timestamp=datetime.utcnow().isoformat(),
                    cpu_percent=process.cpu_percent(),
                    memory_mb=process.memory_info().rss / 1024 / 1024,
                    events_processed=self.events_processed
                )
                self.producer.send('agent-metrics', metric.to_json())
                
                self.db.update_agent_health(
                    agent_name="DecisionAgent",
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
            ['predictions'],
            f'{self.config.kafka.group_id_prefix}-decision-agent',
            self.process_message
        )
        
        logger.info("DecisionAgent starting consumer...")
        try:
            await asyncio.get_event_loop().run_in_executor(None, self.consumer.start)
        finally:
            self.cleanup()
            heartbeat_task.cancel()

    def cleanup(self):
        logger.info("Cleaning up resources...")
        self.running = False
        if hasattr(self, 'consumer'):
            self.consumer.close()
        if hasattr(self, 'producer'):
            self.producer.flush()
            self.producer.close()
        logger.info("Shutdown complete")

if __name__ == "__main__":
    agent = DecisionAgent()
    asyncio.run(agent.run())
