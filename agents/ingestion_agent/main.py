import sys
import os
import signal
import hashlib

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(ROOT_DIR)

from common.kafka_utils import create_producer
from common.config import config
from common.schemas import RawEvent, AgentMetric, Feedback
from backend.database.db_manager import DatabaseManager
from common.logger import setup_logger
from common.metrics_utils import AgentMetricsExporter
import uuid
from datetime import datetime, timezone
import time
import random
import threading
import psutil

# Log file path
LOG_FILE = os.path.join(os.path.dirname(__file__), "../../backend/logs/ingestion.log")

logger = setup_logger("IngestionAgent", config.kafka)

class IngestionAgent:
    def __init__(self):
        self.config = config.get_agent_config("IngestionAgent", 8001)
        self.producer = create_producer(self.config.kafka)
        self.db = DatabaseManager(self.config.database.connection_string)
        self.metrics_exporter = AgentMetricsExporter("IngestionAgent", 8001)
        self.metrics_exporter.start()
        self.events_processed = 0
        self.running = True
        self.drift_factor = 1.0
        self.last_feedback_time = time.time()
        self.last_send_latency = 0.0
        
        # CPU/Memory Monitoring
        self.process = psutil.Process()
        self.process.cpu_percent() # Initial call to "prime" it
        
        # Signal handling
        signal.signal(signal.SIGINT, self.handle_shutdown)
        signal.signal(signal.SIGTERM, self.handle_shutdown)
        
        logger.info("IngestionAgent initialized")

    
    def handle_shutdown(self, signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False

    def generate_synthetic_event(self) -> RawEvent:
        trace_id = str(uuid.uuid4())
        
        # Slowly increase drift every 10 seconds
        self.drift_factor += 0.0001
        
        # Inject High-Risk Anomaly (20% chance)
        is_anomaly = random.random() < 0.2
        if is_anomaly:
            value = random.uniform(900, 2000) * self.drift_factor
            category = random.choice(["A", "B", "C", "X"])
        else:
            value = random.uniform(10, 100) * self.drift_factor
            category = random.choice(["A", "B", "C"])
            
        event = RawEvent(
            event_id=str(uuid.uuid4()),
            trace_id=trace_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            event_type="user_action" if not is_anomaly else "anomaly_event",
            data={
                "user_id": random.randint(1000, 9999),
                "value": float(value),
                "category": category,
                "metadata": {"source": "web", "session": str(uuid.uuid4()), "is_anomaly": is_anomaly}
            }
        )
        event.validate() # Ensure schema validation
        return event
    
    def send_feedback(self):
        while self.running:
            try:
                elapsed = time.time() - self.last_feedback_time
                inject_perf_drop = (int(elapsed) % 30) > 20
                
                if inject_perf_drop:
                    actual_outcome = True
                    predicted_outcome = False
                else:
                    is_correct = random.random() > 0.15
                    actual_outcome = True
                    predicted_outcome = True if is_correct else False
                
                feedback = Feedback(
                    trace_id=str(uuid.uuid4()), 
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    actual_outcome=actual_outcome,
                    predicted_outcome=predicted_outcome,
                    metadata={"reason": "simulated_feedback"}
                )
                self.producer.send("feedback", feedback.to_json())
                time.sleep(2)
            except Exception as e:
                if self.running:
                    logger.error(f"Feedback error: {e}")
                time.sleep(5)

    def send_heartbeat(self):
        while self.running:
            try:
                metric = AgentMetric(
                    agent="IngestionAgent",
                    status="OK",
                    latency_ms=self.last_send_latency,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    cpu_percent=self.process.cpu_percent(),
                    memory_mb=self.process.memory_info().rss / 1024 / 1024,
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
                
                self.metrics_exporter.update_metrics(
                    latency_ms=metric.latency_ms,
                    events_increment=0,
                    cpu_percent=metric.cpu_percent,
                    memory_mb=metric.memory_mb
                )
                
                time.sleep(self.config.heartbeat_interval_seconds)
            except Exception as e:
                if self.running:
                    logger.error(f"Heartbeat error: {e}")
                time.sleep(self.config.heartbeat_interval_seconds)
    
    def run(self):
        heartbeat_thread = threading.Thread(target=self.send_heartbeat, daemon=True)
        heartbeat_thread.start()
        
        feedback_thread = threading.Thread(target=self.send_feedback, daemon=True)
        feedback_thread.start()
        
        logger.info("Starting event ingestion...")
        try:
            target_rate = 1000 # events per second
            batch_size = 100
            interval = batch_size / target_rate
            
            while self.running:
                loop_start = time.time()
                
                # Send a larger batch for high throughput
                for _ in range(batch_size):
                    event = self.generate_synthetic_event()
                    self.producer.send("raw-events", event.to_json(), key=event.trace_id)
                    self.events_processed += 1
                
                if self.events_processed % 1000 == 0:
                    logger.info(f"Processed {self.events_processed} events")
                
                elapsed = time.time() - loop_start
                sleep_time = interval - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)
                
        except Exception as e:
            logger.error(f"Unexpected error in IngestionAgent: {e}")
        finally:
            self.cleanup()

    def cleanup(self):
        logger.info("Cleaning up resources...")
        self.running = False
        if hasattr(self, 'producer'):
            self.producer.flush()
            self.producer.close()
        logger.info("Shutdown complete")

if __name__ == "__main__":
    agent = IngestionAgent()
    agent.run()
