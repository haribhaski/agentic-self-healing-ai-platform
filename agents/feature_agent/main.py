import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from common.kafka_utils import create_producer, create_consumer
from common.config import config
from common.schemas import RawEvent, FeatureVector, AgentMetric
from backend.database.db_manager import DatabaseManager
import logging
import threading
import time
import random
from datetime import datetime
import psutil

from common.logger import setup_logger
from common.config import config

logger = setup_logger("FeatureAgent", config.kafka)

class FeatureAgent:
    def __init__(self):
        self.config = config.get_agent_config("FeatureAgent", 8002)
        self.producer = create_producer(self.config.kafka)
        self.db = DatabaseManager(self.config.database.connection_string)
        self.events_processed = 0
        self.running = True
        logger.info("FeatureAgent initialized")
    
    def extract_features(self, event: RawEvent) -> FeatureVector:
        value = event.data.get("value", 0)
        category = event.data.get("category", "A")
        
        features = {
            "feature_1": value * 2,
            "feature_2": value / 10,
            "feature_3": 1.0 if category == "A" else 0.0,
            "feature_4": random.uniform(0, 1),
            "feature_5": value ** 0.5
        }
        
        return FeatureVector(
            trace_id=event.trace_id,
            timestamp=datetime.utcnow().isoformat(),
            features=features,
            metadata={"original_event_type": event.event_type}
        )
    
    def process_message(self, topic: str, message: str):
        try:
            event = RawEvent.from_json(message)
            features = self.extract_features(event)
            
            self.producer.send("features", features.to_json(), key=features.trace_id)
            self.events_processed += 1
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    def send_heartbeat(self):
        while self.running:
            try:
                process = psutil.Process()
                metric = AgentMetric(
                    agent="FeatureAgent",
                    status="OK",
                    latency_ms=random.uniform(15, 60),
                    timestamp=datetime.utcnow().isoformat(),
                    cpu_percent=process.cpu_percent(),
                    memory_mb=process.memory_info().rss / 1024 / 1024,
                    events_processed=self.events_processed
                )
                self.producer.send("agent-metrics", metric.to_json())
                
                self.db.update_agent_health(
                    agent_name="FeatureAgent",
                    status="OK",
                    latency_ms=metric.latency_ms,
                    cpu_percent=metric.cpu_percent,
                    memory_mb=metric.memory_mb,
                    events_processed=self.events_processed
                )
                
                time.sleep(self.config.heartbeat_interval_seconds)
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
                time.sleep(self.config.heartbeat_interval_seconds)
    
    def run(self):
        heartbeat_thread = threading.Thread(target=self.send_heartbeat, daemon=True)
        heartbeat_thread.start()
        
        consumer = create_consumer(
            self.config.kafka,
            ["raw-events"],
            "feature-agent",
            self.process_message
        )
        consumer.start()

if __name__ == "__main__":
    agent = FeatureAgent()
    agent.run()
