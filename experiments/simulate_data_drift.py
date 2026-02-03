import json
import time
import logging
from kafka import KafkaProducer
import random
from datetime import datetime
import numpy as np

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DriftSimulator")

class DataDriftSimulator:
    def __init__(self):
        self.producer = KafkaProducer(
            bootstrap_servers='localhost:29092',
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
    
    def send_normal_distribution(self, duration_sec=30):
        """Send events with normal credit score distribution (mean=700)"""
        logger.info(f"📊 Sending NORMAL distribution for {duration_sec} seconds")
        logger.info("Credit scores: mean=700, std=80")
        
        start_time = time.time()
        event_count = 0
        
        while time.time() - start_time < duration_sec:
            credit_score = np.random.normal(700, 80)
            credit_score = np.clip(credit_score, 300, 850)
            
            event = {
                "event_id": f"normal_dist_{event_count}",
                "trace_id": f"trace_{event_count}",
                "user_id": f"user_{random.randint(1000, 9999)}",
                "credit_score": float(credit_score),
                "debt_ratio": random.uniform(10, 60),
                "income": random.uniform(30000, 120000),
                "loan_amount": random.uniform(5000, 50000),
                "employment_years": random.uniform(0, 20),
                "timestamp": datetime.utcnow().isoformat()
            }
            
            self.producer.send('raw-events', event)
            event_count += 1
            
            time.sleep(0.05)
        
        logger.info(f"✅ Sent {event_count} events with normal distribution")
    
    def inject_data_drift(self, duration_sec=60):
        """Simulate data drift with shifted credit score distribution"""
        logger.info(f"🔴 INJECTING DATA DRIFT for {duration_sec} seconds")
        logger.info("Credit scores: mean=550 (shifted down by 150 points!)")
        
        start_time = time.time()
        event_count = 0
        
        while time.time() - start_time < duration_sec:
            credit_score = np.random.normal(550, 80)
            credit_score = np.clip(credit_score, 300, 850)
            
            event = {
                "event_id": f"drift_{event_count}",
                "trace_id": f"trace_drift_{event_count}",
                "user_id": f"user_{random.randint(1000, 9999)}",
                "credit_score": float(credit_score),
                "debt_ratio": random.uniform(10, 60),
                "income": random.uniform(30000, 120000),
                "loan_amount": random.uniform(5000, 50000),
                "employment_years": random.uniform(0, 20),
                "timestamp": datetime.utcnow().isoformat()
            }
            
            self.producer.send('raw-events', event)
            event_count += 1
            
            time.sleep(0.05)
        
        logger.info(f"✅ Data drift injected. Sent {event_count} drifted events.")
        logger.info("MonitoringAgent should detect DATA_DRIFT")
        logger.info("HealingAgent should propose TRIGGER_RETRAINING")
    
    def run_simulation(self):
        """Full drift simulation workflow"""
        logger.info("="*60)
        logger.info("DATA DRIFT HEALING SIMULATION")
        logger.info("="*60)
        logger.info("Phase 1: Send normal distribution (baseline)")
        logger.info("Phase 2: Inject drift (shift credit scores down)")
        logger.info("Phase 3: MonitoringAgent detects drift")
        logger.info("Phase 4: HealingAgent triggers retraining")
        logger.info("="*60)
        
        input("Press Enter to start simulation...")
        
        self.send_normal_distribution(duration_sec=30)
        
        logger.info("\n⏸️  Baseline established. Now injecting drift...\n")
        time.sleep(2)
        
        self.inject_data_drift(duration_sec=60)
        
        logger.info("\n⏸️  Drift injected. Returning to normal...\n")
        time.sleep(2)
        
        self.send_normal_distribution(duration_sec=30)
        
        logger.info("="*60)
        logger.info("SIMULATION COMPLETE")
        logger.info("Check:")
        logger.info("- Kafka topic 'alerts' for DATA_DRIFT alert")
        logger.info("- Kafka topic 'policy-requests' for RETRAINING request")
        logger.info("- Database incidents table for drift incident")
        logger.info("- MLflow for new training run triggered")
        logger.info("="*60)

if __name__ == "__main__":
    simulator = DataDriftSimulator()
    simulator.run_simulation()
