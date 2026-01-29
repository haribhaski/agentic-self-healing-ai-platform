import sys
import os

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(ROOT_DIR)

from common.kafka_utils import create_producer, create_consumer
from common.config import config
from common.schemas import RawEvent, AgentMetric, Feedback
from backend.database.db_manager import DatabaseManager
from common.logger import setup_logger
import uuid
from datetime import datetime
import time
import random
import threading
import psutil

logger = setup_logger("IngestionAgent", config.kafka)

class IngestionAgent:
    def __init__(self):
        self.config = config.get_agent_config("IngestionAgent", 8001)
        self.producer = create_producer(self.config.kafka)
        self.db = DatabaseManager(self.config.database.connection_string)
        self.events_processed = 0
        self.running = True
        self.drift_factor = 1.0
        self.last_feedback_time = time.time()
        logger.info("IngestionAgent initialized")
    
    def generate_synthetic_event(self) -> RawEvent:
        trace_id = str(uuid.uuid4())
        
        # Slowly increase drift every 10 seconds
        self.drift_factor += 0.002 # Increased drift speed
        
        # Inject High-Risk Anomaly (20% chance now)
        is_anomaly = random.random() < 0.2
        if is_anomaly:
            value = random.uniform(900, 2000) * self.drift_factor
            category = random.choice(["A", "B", "C", "X"]) # Added unknown category X
            logger.warning(f"Injecting High-Risk Anomaly: value={value:.2f}, category={category}")
        else:
            value = random.uniform(10, 100) * self.drift_factor
            category = random.choice(["A", "B", "C"])
            
        event = RawEvent(
            event_id=str(uuid.uuid4()),
            trace_id=trace_id,
            timestamp=datetime.utcnow().isoformat(),
            event_type="user_action" if not is_anomaly else "anomaly_event",
            data={
                "user_id": random.randint(1000, 9999),
                "value": value,
                "category": category,
                "metadata": {"source": "web", "session": str(uuid.uuid4()), "is_anomaly": is_anomaly}
            }
        )
        return event
    
    def send_feedback(self):
        """Simulate Performance Drop by sending negative feedback occasionally"""
        while self.running:
            try:
                # Every 30 seconds, inject a burst of "Incorrect" predictions
                elapsed = time.time() - self.last_feedback_time
                inject_perf_drop = (int(elapsed) % 30) > 20
                
                if inject_perf_drop:
                    logger.warning("Injecting Performance Drop Feedback")
                    actual_outcome = True
                    predicted_outcome = False # Mismatch
                else:
                    is_correct = random.random() > 0.15 # 85% accurate normally
                    actual_outcome = True
                    predicted_outcome = True if is_correct else False
                
                feedback = Feedback(
                    trace_id=str(uuid.uuid4()), 
                    timestamp=datetime.utcnow().isoformat(),
                    actual_outcome=actual_outcome,
                    predicted_outcome=predicted_outcome,
                    metadata={"reason": "simulated_feedback"}
                )
                self.producer.send("feedback", feedback.to_json())
                time.sleep(2) # Increased frequency
            except Exception as e:
                logger.error(f"Feedback error: {e}")
                time.sleep(5)

    def send_heartbeat(self):
        start_time = time.time()
        while self.running:
            try:
                process = psutil.Process()
                
                # Inject Latency SLO Breach Anomaly (every 60 seconds)
                elapsed = time.time() - start_time
                inject_latency_spike = (int(elapsed) % 60) > 55
                
                latency = random.uniform(400, 600) if inject_latency_spike else random.uniform(10, 50)
                if inject_latency_spike:
                    logger.warning(f"Injecting Latency Spike: {latency:.2f}ms")
                
                metric = AgentMetric(
                    agent="IngestionAgent",
                    status="OK",
                    latency_ms=latency,
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
        
        feedback_thread = threading.Thread(target=self.send_feedback, daemon=True)
        feedback_thread.start()
        
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
