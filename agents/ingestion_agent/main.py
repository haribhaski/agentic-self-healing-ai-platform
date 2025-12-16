import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from common.kafka_utils import create_producer, create_consumer
from common.config import config
from common.schemas import RawEvent, AgentMetric
from backend.database.db_manager import DatabaseManager
import logging
import uuid
from datetime import datetime
import time
import random
import threading
import psutil

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class IngestionAgent:
    def __init__(self):
        self.config = config.get_agent_config("IngestionAgent", 8001)
        self.producer = create_producer(self.config.kafka)
        self.db = DatabaseManager(self.config.database.connection_string)
        self.events_processed = 0
        self.running = True
        logger.info("IngestionAgent initialized")
    
    def generate_synthetic_event(self) -> RawEvent:
        trace_id = str(uuid.uuid4())
        event = RawEvent(
            event_id=str(uuid.uuid4()),
            trace_id=trace_id,
            timestamp=datetime.utcnow().isoformat(),
            event_type=random.choice(["user_action", "system_event", "api_call"]),
            data={
                "user_id": random.randint(1000, 9999),
                "value": random.uniform(10, 100),
                "category": random.choice(["A", "B", "C"]),
                "metadata": {"source": "web", "session": str(uuid.uuid4())}
            }
        )
        return event
    
    def send_heartbeat(self):
        while self.running:
            try:
                process = psutil.Process()
                metric = AgentMetric(
                    agent="IngestionAgent",
                    status="OK",
                    latency_ms=random.uniform(10, 50),
                    timestamp=datetime.utcnow().isoformat(),
                    cpu_percent=process.cpu_percent(),
                    memory_mb=process.memory_info().rss / 1024 / 1024,
                    events_processed=self.events_processed
                )
                self.producer.send("agent-metrics", metric.to_json())
                
                self.db.update_agent_health(
                    agent_name="IngestionAgent",
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
        
        logger.info("Starting event ingestion...")
        try:
            while self.running:
                event = self.generate_synthetic_event()
                
                success = self.producer.send("raw-events", event.to_json(), key=event.trace_id)
                
                if success:
                    self.events_processed += 1
                    if self.events_processed % 100 == 0:
                        logger.info(f"Processed {self.events_processed} events")
                
                time.sleep(random.uniform(0.01, 0.05))
                
        except KeyboardInterrupt:
            logger.info("Shutting down IngestionAgent")
        finally:
            self.running = False
            self.producer.close()

if __name__ == "__main__":
    agent = IngestionAgent()
    agent.run()
