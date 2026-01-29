import json
import time
import random
from datetime import datetime, timezone
from kafka import KafkaProducer
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from common.config import config

def create_producer():
    return KafkaProducer(
        bootstrap_servers=[config.kafka.bootstrap_servers],
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )

def simulate_mlops_metrics():
    producer = create_producer()
    topic = "mlops-metrics"
    
    print(f"Starting MLOps simulator, producing to {topic}...")
    
    base_accuracy = 0.94
    base_drift = 0.14
    
    while True:
        try:
            # Simulate metrics update
            accuracy = base_accuracy + random.uniform(-0.01, 0.01)
            drift = base_drift + random.uniform(-0.02, 0.02)
            
            metrics = [
                {"name": "Accuracy", "value": round(accuracy * 100, 1), "trend": "+0.2%", "status": "good"},
                {"name": "Latency (p99)", "value": f"{random.randint(40, 50)}ms", "trend": "-2ms", "status": "good"},
                {"name": "Drift Score", "value": round(drift, 2), "trend": "+0.01", "status": "good"},
                {"name": "Data Quality", "value": 98.5 + random.uniform(-0.5, 0.5), "trend": "+0.1%", "status": "good"},
            ]
            
            # Simulate drift data for chart (last 7 points)
            drift_data = []
            now = datetime.now()
            for i in range(7):
                hour = (now.hour - (6-i) * 4) % 24
                drift_data.append({
                    "time": f"{hour:02d}:00",
                    "drift": round(base_drift + random.uniform(-0.05, 0.05), 2)
                })
            
            experiments = [
                {"id": f"exp-{random.randint(2800, 2900)}", "model": "decision-agent-v3", "status": "completed", "metric": f"{accuracy:.3f}"},
                {"id": f"exp-{random.randint(2800, 2900)}", "model": "anomaly-detector-v2", "status": "running", "metric": "---"},
                {"id": f"exp-{random.randint(2800, 2900)}", "model": "planner-agent-v4", "status": "completed", "metric": "0.918"},
            ]
            
            payload = {
                "type": "mlops_update",
                "metrics": metrics,
                "drift_data": drift_data,
                "experiments": experiments,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            producer.send(topic, payload)
            print(f"Sent MLOps update at {datetime.now().isoformat()}")
            
            time.sleep(5)
        except Exception as e:
            print(f"Error in MLOps simulator: {e}")
            time.sleep(10)

if __name__ == "__main__":
    simulate_mlops_metrics()
