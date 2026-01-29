import asyncio
import json
import logging
import signal
import time
from datetime import datetime
import datetime as dt
from collections import deque
import numpy as np
import sys
import os
import psutil

sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))
from common.config import config
from common.logger import setup_logger
from common.kafka_utils import create_producer, create_consumer
from common.schemas import (
    IncidentType, IncidentStatus, AgentMetric, 
    Decision, Feedback, Alert, IncidentLog
)
from backend.database.db_manager import DatabaseManager

logger = setup_logger("MonitoringAgent", config.kafka)

class MonitoringAgent:
    def __init__(self):
        self.config = config.get_agent_config("MonitoringAgent", 8005)
        self.producer = create_producer(self.config.kafka)
        self.db = DatabaseManager(self.config.database.connection_string)
        
        self.latency_window = deque(maxlen=100)
        self.accuracy_window = deque(maxlen=200)
        self.feature_distributions = deque(maxlen=1000)
        self.heartbeats = {}
        self.latency_threshold_ms = 300
        self.accuracy_threshold = 0.8
        self.heartbeat_timeout_sec = 30
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

    def check_heartbeats(self):
        now = dt.datetime.now(dt.timezone.utc)
        for agent, last_seen in self.heartbeats.items():
            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=dt.timezone.utc)
                
            if (now - last_seen).total_seconds() > self.heartbeat_timeout_sec:
                existing_incident = self.db.get_open_incident_by_type(IncidentType.AGENT_DOWN)
                if existing_incident:
                    continue

                alert = Alert(
                    alert_id=f"ALR-{int(time.time())}",
                    alert_type=IncidentType.AGENT_DOWN,
                    severity="CRITICAL",
                    timestamp=now.isoformat(),
                    metrics_snapshot={"last_seen": last_seen.isoformat(), "agent": agent},
                    description=f"{agent} heartbeat missing for {(now - last_seen).total_seconds():.0f}s"
                )
                self.producer.send('alerts', alert.to_json())
                logger.warning(f"ALERT: {agent} is DOWN")
                self.db.create_incident(
                    incident_type=IncidentType.AGENT_DOWN,
                    metrics_snapshot=alert.metrics_snapshot,
                    description=alert.description
                )

    def process_metric(self, topic: str, message: str):
        if not self.running: return
        start_time = time.time()
        try:
            metric = AgentMetric.from_json(message)
            agent = metric.agent
            self.heartbeats[agent] = dt.datetime.now(dt.timezone.utc)
            
            if metric.latency_ms > 0:
                self.latency_window.append(metric.latency_ms)
            
            self.check_heartbeats()
            
            self.events_processed += 1
            if self.events_processed % 100 == 0:
                logger.info(f"MonitoringAgent processed {self.events_processed} metrics")
            
            if len(self.latency_window) >= 50:
                median_latency = np.median(self.latency_window)
                if median_latency > self.latency_threshold_ms:
                    existing = self.db.get_open_incident_by_type(IncidentType.LATENCY_SLO_BREACH)
                    if not existing:
                        alert = Alert(
                            alert_id=f"ALR-LAT-{int(time.time())}",
                            alert_type=IncidentType.LATENCY_SLO_BREACH,
                            severity="HIGH",
                            timestamp=datetime.utcnow().isoformat(),
                            metrics_snapshot={"median_latency": float(median_latency)},
                            description=f"Median latency {median_latency:.1f}ms > {self.latency_threshold_ms}ms"
                        )
                        self.producer.send('alerts', alert.to_json())
                        self.db.create_incident(
                            incident_type=IncidentType.LATENCY_SLO_BREACH,
                            metrics_snapshot=alert.metrics_snapshot,
                            description=alert.description
                        )
            
            self.last_latency = (time.time() - start_time) * 1000
            self.events_processed += 1
        except Exception as e:
            logger.error(f"Error processing metric: {e}")

    def process_decision_feedback(self, topic: str, message: str):
        if not self.running: return
        try:
            if topic == 'feedback':
                feedback = Feedback.from_json(message)
                is_correct = (feedback.actual_outcome == feedback.predicted_outcome)
                self.accuracy_window.append(1 if is_correct else 0)
                
                if len(self.accuracy_window) >= 100:
                    acc = np.mean(self.accuracy_window)
                    if acc < self.accuracy_threshold:
                        existing = self.db.get_open_incident_by_type(IncidentType.PERF_DROP)
                        if not existing:
                            alert = Alert(
                                alert_id=f"ALR-PERF-{int(time.time())}",
                                alert_type=IncidentType.PERF_DROP,
                                severity="HIGH",
                                timestamp=datetime.utcnow().isoformat(),
                                metrics_snapshot={"accuracy": float(acc)},
                                description=f"Model accuracy {acc:.3f} < {self.accuracy_threshold}"
                            )
                            self.producer.send('alerts', alert.to_json())
                            self.db.create_incident(
                                incident_type=IncidentType.PERF_DROP,
                                metrics_snapshot=alert.metrics_snapshot,
                                description=alert.description
                            )
            
            elif topic == 'decisions':
                decision = Decision.from_json(message)
                if decision.confidence > 0:
                    self.feature_distributions.append(decision.confidence)
                    
                    if len(self.feature_distributions) >= 500:
                        recent = list(self.feature_distributions)[-200:]
                        reference = list(self.feature_distributions)[:200]
                        drift = abs(np.mean(recent) - np.mean(reference)) / (np.mean(reference) + 1e-6)
                        
                        if drift > 0.2:
                            existing = self.db.get_open_incident_by_type(IncidentType.DATA_DRIFT)
                            if not existing:
                                alert = Alert(
                                    alert_id=f"ALR-DRIFT-{int(time.time())}",
                                    alert_type=IncidentType.DATA_DRIFT,
                                    severity="MEDIUM",
                                    timestamp=datetime.utcnow().isoformat(),
                                    metrics_snapshot={"drift_score": float(drift)},
                                    description=f"Data drift detected: {drift:.3f}"
                                )
                                self.producer.send('alerts', alert.to_json())
                                self.db.create_incident(
                                    incident_type=IncidentType.DATA_DRIFT,
                                    metrics_snapshot=alert.metrics_snapshot,
                                    description=alert.description
                                )
        except Exception as e:
            logger.error(f"Error processing decision/feedback: {e}")

    async def heartbeat_loop(self):
        while self.running:
            try:
                process = psutil.Process()
                metric = AgentMetric(
                    agent="MonitoringAgent",
                    status="OK",
                    latency_ms=self.last_latency,
                    timestamp=datetime.utcnow().isoformat(),
                    cpu_percent=process.cpu_percent(),
                    memory_mb=process.memory_info().rss / 1024 / 1024,
                    events_processed=self.events_processed
                )
                self.producer.send('agent-metrics', metric.to_json())
                
                self.db.update_agent_health(
                    agent_name="MonitoringAgent",
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
        
        self.metrics_consumer = create_consumer(
            self.config.kafka,
            ['agent-metrics'],
            'monitoring-metrics-group',
            self.process_metric
        )
        
        self.decisions_consumer = create_consumer(
            self.config.kafka,
            ['decisions', 'feedback'],
            'monitoring-decisions-group',
            self.process_decision_feedback
        )
        
        logger.info("MonitoringAgent starting consumers...")
        try:
            # Run consumers in separate threads since they are blocking
            loop = asyncio.get_event_loop()
            await asyncio.gather(
                loop.run_in_executor(None, self.metrics_consumer.start),
                loop.run_in_executor(None, self.decisions_consumer.start)
            )
        finally:
            self.cleanup()
            heartbeat_task.cancel()

    def cleanup(self):
        logger.info("Cleaning up resources...")
        self.running = False
        if hasattr(self, 'metrics_consumer'): self.metrics_consumer.close()
        if hasattr(self, 'decisions_consumer'): self.decisions_consumer.close()
        if hasattr(self, 'producer'):
            self.producer.flush()
            self.producer.close()
        logger.info("Shutdown complete")

if __name__ == "__main__":
    agent = MonitoringAgent()
    asyncio.run(agent.run())
