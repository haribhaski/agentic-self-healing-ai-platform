import json
import time
import logging
from kafka import KafkaProducer
import random
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("LatencySimulator")

class LatencySimulator:
    def __init__(self):
        self.producer = KafkaProducer(
            bootstrap_servers='localhost:29092',
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
    
    def inject_latency_spike(self, duration_sec=60):
        """Simulate latency spike by sending slow events"""
        logger.info(f"🔴 INJECTING LATENCY SPIKE for {duration_sec} seconds")
        logger.info("This will cause ModelAgent to slow down inference...")
        
        start_time = time.time()
        event_count = 0
        
        while time.time() - start_time < duration_sec:
            event = {
                "event_id": f"latency_test_{event_count}",
                "trace_id": f"trace_{event_count}",
                "user_id": f"user_{random.randint(1000, 9999)}",
                "credit_score": random.randint(600, 800),
                "debt_ratio": random.uniform(10, 60),
                "income": random.uniform(30000, 120000),
                "loan_amount": random.uniform(5000, 50000),
                "employment_years": random.uniform(0, 20),
                "INJECT_LATENCY": True,
                "latency_ms": 2000,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            self.producer.send('raw-events', event)
            event_count += 1
            
            time.sleep(0.1)
        
        logger.info(f"✅ Latency spike completed. Sent {event_count} slow events.")
        logger.info("MonitoringAgent should detect LATENCY_SLO_BREACH")
        logger.info("HealingAgent should propose ENABLE_SAFE_MODE")
        
        self.send_normal_traffic(30)
    
    def send_normal_traffic(self, duration_sec=30):
        """Send normal traffic after spike"""
        logger.info(f"Sending normal traffic for {duration_sec} seconds...")
        
        start_time = time.time()
        event_count = 0
        
        while time.time() - start_time < duration_sec:
            event = {
                "event_id": f"normal_{event_count}",
                "trace_id": f"trace_normal_{event_count}",
                "user_id": f"user_{random.randint(1000, 9999)}",
                "credit_score": random.randint(600, 800),
                "debt_ratio": random.uniform(10, 60),
                "income": random.uniform(30000, 120000),
                "loan_amount": random.uniform(5000, 50000),
                "employment_years": random.uniform(0, 20),
                "timestamp": datetime.utcnow().isoformat()
            }
            
            self.producer.send('raw-events', event)
            event_count += 1
            
            time.sleep(0.1)
        
        logger.info(f"✅ Normal traffic completed. Sent {event_count} events.")
        logger.info("Check if latency returned to normal after healing action!")

if __name__ == "__main__":
    simulator = LatencySimulator()
    
    logger.info("="*60)
    logger.info("LATENCY SPIKE HEALING SIMULATION")
    logger.info("="*60)
    logger.info("This will:")
    logger.info("1. Inject 2000ms latency into events")
    logger.info("2. MonitoringAgent detects LATENCY_SLO_BREACH")
    logger.info("3. HealingAgent proposes ENABLE_SAFE_MODE")
    logger.info("4. AGL approves (mock)")
    logger.info("5. System switches to rule-based (fast) decisions")
    logger.info("6. Latency returns to normal")
    logger.info("="*60)
    
    input("Press Enter to start simulation...")
    
    simulator.inject_latency_spike(duration_sec=60)
    
    logger.info("="*60)
    logger.info("SIMULATION COMPLETE")
    logger.info("Check:")
    logger.info("- Kafka topic 'alerts' for LATENCY_SLO_BREACH")
    logger.info("- Kafka topic 'policy-requests' for SAFE_MODE request")
    logger.info("- Database incidents table for new incident")
    logger.info("- Database healing_actions for executed action")
    logger.info("="*60)
