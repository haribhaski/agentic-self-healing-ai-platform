import sys
import os
import signal
import hashlib
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from common.kafka_utils import create_producer, create_consumer
from common.config import config
from common.schemas import RawEvent, FeatureVector, AgentMetric
from backend.database.db_manager import DatabaseManager
import logging
import threading
import time
import random
from datetime import datetime, timezone
import psutil

from common.logger import setup_logger
from common.metrics_utils import AgentMetricsExporter

# Log file path
LOG_FILE = os.path.join(os.path.dirname(__file__), "../../backend/logs/feature.log")

logger = setup_logger("FeatureAgent", config.kafka, log_file=LOG_FILE)

class FeatureAgent:
    def __init__(self):
        self.config = config.get_agent_config("FeatureAgent", 8002)
        self.producer = create_producer(self.config.kafka)
        self.db = DatabaseManager(self.config.database.connection_string)
        self.events_processed = 0
        self.running = True
        self.last_latency = 0.0
        self.process = psutil.Process()
        self.process.cpu_percent()
        
        # Signal handling for graceful shutdown
        signal.signal(signal.SIGINT, self.handle_shutdown)
        signal.signal(signal.SIGTERM, self.handle_shutdown)
        
        logger.info("FeatureAgent initialized")
    
    def handle_shutdown(self, signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False

    def extract_features(self, event: RawEvent) -> FeatureVector:
        value = event.data.get("value", 0)
        category = event.data.get("category", "A")
        
        # Deterministic feature_4 derived from event_id
        hash_val = int(hashlib.md5(event.event_id.encode()).hexdigest(), 16)
        feature_4 = (hash_val % 1000) / 1000.0
        
        features = {
            "feature_1": float(value * 2),
            "feature_2": float(value / 10),
            "feature_3": 1.0 if category == "A" else 0.0,
            "feature_4": feature_4,
            "feature_5": float(abs(value) ** 0.5)
        }
        
        return FeatureVector(
            trace_id=event.trace_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            features=features,
            metadata={"original_event_type": event.event_type}
        )
    
    def process_message(self, topic: str, message: str):
        if not self.running:
            return
            
        start_time = time.time()
        try:
            event = RawEvent.from_json(message)
            features = self.extract_features(event)
            
            self.producer.send("features", features.to_json(), key=features.trace_id)
            self.events_processed += 1
            if self.events_processed % 100 == 0:
                logger.info(f"Processed {self.events_processed} features")
            
            # Update real processing latency
            self.last_latency = (time.time() - start_time) * 1000
            
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
    
    def send_heartbeat(self):
        while self.running:
            try:
                metric = AgentMetric(
                    agent="FeatureAgent",
                    status="OK",
                    latency_ms=self.last_latency,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    cpu_percent=self.process.cpu_percent(),
                    memory_mb=self.process.memory_info().rss / 1024 / 1024,
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
        
        self.consumer = create_consumer(
            self.config.kafka,
            ["raw-events"],
            f"{self.config.kafka.group_id_prefix}-feature-agent",
            self.process_message
        )
        
        logger.info("Starting consumer...")
        try:
            # The consumer.start() is blocking until KeyboardInterrupt or close()
            self.consumer.start()
        finally:
            self.cleanup()

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
    agent = FeatureAgent()
    agent.run()
