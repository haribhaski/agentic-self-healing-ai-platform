import asyncio
import json
import logging
from datetime import datetime, timedelta
from collections import deque
from kafka import KafkaConsumer, KafkaProducer
import numpy as np
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))
from common.config import Config
from backend.database.db_manager import DatabaseManager

from common.logger import setup_logger
from common.config import config

logger = setup_logger("MonitoringAgent", config.kafka)

class MonitoringAgent:
    def __init__(self):
        self.config = config
        self.db = DatabaseManager(self.config.database.connection_string)
        
        self.metrics_consumer = KafkaConsumer(
            'agent-metrics',
            bootstrap_servers=self.config.kafka.bootstrap_servers,
            value_deserializer=lambda v: json.loads(v.decode('utf-8')),
            group_id='monitoring-agent-metrics'
        )
        
        self.decisions_consumer = KafkaConsumer(
            'decisions',
            'feedback',
            bootstrap_servers=self.config.kafka.bootstrap_servers,
            value_deserializer=lambda v: json.loads(v.decode('utf-8')),
            group_id='monitoring-agent-decisions'
        )
        
        self.producer = KafkaProducer(
            bootstrap_servers=self.config.kafka.bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
        
        self.latency_window = deque(maxlen=100)
        self.accuracy_window = deque(maxlen=200)
        self.feature_distributions = deque(maxlen=1000)
        self.heartbeats = {}
        self.latency_threshold_ms = 300
        self.accuracy_threshold = 0.8
        self.heartbeat_timeout_sec = 30
    
    def check_heartbeats(self):
        """Check for missing agent heartbeats"""
        now = datetime.utcnow()
        for agent, last_seen in self.heartbeats.items():
            if (now - last_seen).total_seconds() > self.heartbeat_timeout_sec:
                alert = {
                    "alert_type": "AGENT_DOWN",
                    "agent": agent,
                    "severity": "CRITICAL",
                    "description": f"{agent} heartbeat missing for {(now - last_seen).total_seconds():.0f}s",
                    "metrics": {"last_seen": last_seen.isoformat()},
                    "timestamp": now.isoformat()
                }
                self.producer.send('alerts', alert)
                logger.warning(f"ALERT: {agent} is DOWN")
                self.db.create_incident(
                    incident_type="AGENT_DOWN",
                    metrics_snapshot=alert["metrics"],
                    description=alert["description"]
                )
    
    def check_latency_slo(self):
        """Check if latency SLO is breached"""
        if len(self.latency_window) < 50:
            return
        
        median_latency = np.median(self.latency_window)
        p95_latency = np.percentile(self.latency_window, 95)
        
        if median_latency > self.latency_threshold_ms:
            alert = {
                "alert_type": "LATENCY_SLO_BREACH",
                "severity": "HIGH",
                "description": f"Median latency {median_latency:.1f}ms > {self.latency_threshold_ms}ms",
                "metrics": {
                    "median_latency_ms": median_latency,
                    "p95_latency_ms": p95_latency,
                    "threshold_ms": self.latency_threshold_ms
                },
                "timestamp": datetime.utcnow().isoformat()
            }
            self.producer.send('alerts', alert)
            logger.warning(f"ALERT: Latency SLO breach - {median_latency:.1f}ms")
            self.db.create_incident(
                incident_type="LATENCY_SLO_BREACH",
                metrics_snapshot=alert["metrics"],
                description=alert["description"]
            )
    
    def check_performance_drop(self):
        """Check for model performance degradation"""
        if len(self.accuracy_window) < 100:
            return
        
        recent_accuracy = np.mean(self.accuracy_window)
        
        if recent_accuracy < self.accuracy_threshold:
            alert = {
                "alert_type": "PERF_DROP",
                "severity": "HIGH",
                "description": f"Model accuracy {recent_accuracy:.3f} < {self.accuracy_threshold}",
                "metrics": {
                    "accuracy": recent_accuracy,
                    "threshold": self.accuracy_threshold,
                    "sample_size": len(self.accuracy_window)
                },
                "timestamp": datetime.utcnow().isoformat()
            }
            self.producer.send('alerts', alert)
            logger.warning(f"ALERT: Performance drop - accuracy {recent_accuracy:.3f}")
            self.db.create_incident(
                incident_type="PERF_DROP",
                metrics_snapshot=alert["metrics"],
                description=alert["description"]
            )
    
    def check_data_drift(self):
        """Check for data drift (simplified PSI)"""
        if len(self.feature_distributions) < 500:
            return
        
        recent = list(self.feature_distributions)[-200:]
        reference = list(self.feature_distributions)[:200]
        
        recent_mean = np.mean(recent)
        ref_mean = np.mean(reference)
        
        drift_score = abs(recent_mean - ref_mean) / (ref_mean + 1e-6)
        
        if drift_score > 0.2:
            alert = {
                "alert_type": "DATA_DRIFT",
                "severity": "MEDIUM",
                "description": f"Data drift detected: {drift_score:.3f}",
                "metrics": {
                    "drift_score": drift_score,
                    "recent_mean": recent_mean,
                    "reference_mean": ref_mean
                },
                "timestamp": datetime.utcnow().isoformat()
            }
            self.producer.send('alerts', alert)
            logger.warning(f"ALERT: Data drift detected - {drift_score:.3f}")
            self.db.create_incident(
                incident_type="DATA_DRIFT",
                metrics_snapshot=alert["metrics"],
                description=alert["description"]
            )
    
    async def monitor_metrics(self):
        """Monitor agent metrics (heartbeats)"""
        logger.info("MonitoringAgent: monitoring agent-metrics")
        
        try:
            for message in self.metrics_consumer:
                try:
                    metric = message.value
                    agent = metric.get('agent')
                    
                    if agent:
                        self.heartbeats[agent] = datetime.utcnow()
                    
                    if 'latency_ms' in metric:
                        self.latency_window.append(metric['latency_ms'])
                    
                    self.check_heartbeats()
                    self.check_latency_slo()
                    
                except Exception as e:
                    logger.error(f"Error processing metric: {e}")
        except KeyboardInterrupt:
            logger.info("Shutting down metrics monitoring")
    
    async def monitor_decisions(self):
        """Monitor decisions and feedback for performance"""
        logger.info("MonitoringAgent: monitoring decisions and feedback")
        
        try:
            for message in self.decisions_consumer:
                try:
                    event = message.value
                    
                    if message.topic == 'feedback':
                        actual = event.get('actual_outcome')
                        predicted = event.get('predicted_outcome')
                        if actual is not None and predicted is not None:
                            is_correct = (actual == predicted)
                            self.accuracy_window.append(1 if is_correct else 0)
                            self.check_performance_drop()
                    
                    if 'risk_score' in event:
                        self.feature_distributions.append(event['risk_score'])
                        self.check_data_drift()
                    
                except Exception as e:
                    logger.error(f"Error processing decision/feedback: {e}")
        except KeyboardInterrupt:
            logger.info("Shutting down decision monitoring")
    
    async def run(self):
        """Run both monitoring loops"""
        metrics_task = asyncio.create_task(self.monitor_metrics())
        decisions_task = asyncio.create_task(self.monitor_decisions())
        
        await asyncio.gather(metrics_task, decisions_task)

if __name__ == "__main__":
    agent = MonitoringAgent()
    asyncio.run(agent.run())
