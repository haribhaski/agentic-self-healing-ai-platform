import asyncio
import json
import logging
import signal
import time
from datetime import datetime, timezone
import datetime as dt
from collections import deque
import numpy as np
import sys
import os
import psutil
import random

# Flush log file on restart
LOG_FILE = os.path.join(os.path.dirname(__file__), "../../backend/logs/monitoring.log")
if os.path.exists(LOG_FILE):
    with open(LOG_FILE, 'w') as f:
        f.truncate(0)

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


def _extract_incident_id(result) -> str:
    """
    Safely pull a plain string ID out of whatever db.create_incident() returns.
    Handles:
      - An Incident object with an .incident_id attribute
      - A plain string ID
      - A dict with an 'incident_id' key
    """
    if result is None:
        return None
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        return result.get('incident_id')
    if hasattr(result, 'incident_id'):
        return result.incident_id
    # Last resort: stringify it so json.dumps won't blow up downstream
    logger.warning(f"Unexpected type from create_incident(): {type(result)}. Falling back to str().")
    return str(result)


class MonitoringAgent:
    def __init__(self):
        self.config = config.get_agent_config("MonitoringAgent", 8005)
        self.producer = create_producer(self.config.kafka)
        self.db = DatabaseManager(self.config.database.connection_string)
        
        # Monitoring windows
        self.latency_window = deque(maxlen=100)
        self.accuracy_window = deque(maxlen=200)
        self.feature_distributions = deque(maxlen=1000)
        self.heartbeats = {}
        
        # FIXED THRESHOLDS - Much lower for testing
        self.latency_threshold_ms = 10  # 10ms instead of 50ms - easier to trigger
        self.accuracy_threshold = 0.90  # 90% instead of 99% - more realistic
        self.heartbeat_timeout_sec = 15  # 15s instead of 30s - faster detection
        self.drift_threshold = 0.15  # 15% instead of 1% - easier to detect
        
        # Agent state
        self.running = True
        self.events_processed = 0
        self.last_latency = 0.0
        self.process = psutil.Process()
        self.process.cpu_percent()
        
        # TESTING MODE - Generate synthetic spikes
        self.test_mode = True  # Set to False to disable testing
        self.spike_interval = 30  # Generate spike every 30 seconds
        self.last_spike_time = time.time()
        
        # Signal handling (only in main thread)
        import threading
        if threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGINT, lambda signum, frame: self.handle_shutdown())
            signal.signal(signal.SIGTERM, lambda signum, frame: self.handle_shutdown())
        
        logger.info("=" * 80)
        logger.info("✓ MonitoringAgent initialized")
        logger.info("=" * 80)
        logger.info(f"TEST MODE: {'ENABLED' if self.test_mode else 'DISABLED'}")
        logger.info(f"Latency Threshold: {self.latency_threshold_ms}ms")
        logger.info(f"Accuracy Threshold: {self.accuracy_threshold * 100}%")
        logger.info(f"Heartbeat Timeout: {self.heartbeat_timeout_sec}s")
        logger.info(f"Drift Threshold: {self.drift_threshold * 100}%")
        if self.test_mode:
            logger.info(f"Spike Interval: {self.spike_interval}s")
        logger.info("=" * 80)
    
    def handle_shutdown(self):
        """Handle shutdown signals gracefully"""
        logger.info("Shutdown signal received...")
        self.running = False

    def _parse_incident(self, incident):
        """Parse incident from DB - handles both dict and JSON string"""
        if not incident:
            return None
        if isinstance(incident, str):
            if not incident.strip():
                return None
            try:
                return json.loads(incident)
            except json.JSONDecodeError as e:
                logger.debug(f"Failed to parse incident JSON (probably empty): {e}")
                return None
        return incident

    # Only suppress a repeat alert for this many seconds after the last one.
    # After this window any stale open incident is closed and a fresh alert
    # is allowed through.
    INCIDENT_COOLDOWN_SECONDS = 60

    def _should_create_incident(self, incident_type, key=None, value=None):
        """
        Return True if a new incident should be created.
        Suppresses duplicates only within INCIDENT_COOLDOWN_SECONDS.
        Closes stale incidents that are older than the cooldown.
        """
        existing = self.db.get_open_incident_by_type(incident_type)
        existing = self._parse_incident(existing)

        if not existing:
            logger.info(f"   ✅ No open {incident_type.value} incident — will create new one")
            return True

        # Try to honour the cooldown window using created_at / timestamp
        created_at = existing.get('created_at') or existing.get('timestamp')
        if created_at:
            try:
                if isinstance(created_at, str):
                    created_dt = dt.datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                else:
                    created_dt = created_at
                if created_dt.tzinfo is None:
                    created_dt = created_dt.replace(tzinfo=dt.timezone.utc)

                age_sec = (dt.datetime.now(dt.timezone.utc) - created_dt).total_seconds()

                if age_sec < self.INCIDENT_COOLDOWN_SECONDS:
                    logger.warning(
                        f"⏳ Suppressing duplicate {incident_type.value} alert "
                        f"(existing incident is {age_sec:.0f}s old, "
                        f"cooldown={self.INCIDENT_COOLDOWN_SECONDS}s)"
                    )
                    return False

                # Cooldown expired — close the stale incident
                incident_id = _extract_incident_id(existing)
                if incident_id:
                    try:
                        self.db.update_incident_status(incident_id=incident_id, status=IncidentStatus.RESOLVED)
                        logger.info(f"   🔒 Closed stale {incident_type.value} incident {incident_id} (age {age_sec:.0f}s)")
                    except Exception as e:
                        logger.warning(f"   ⚠️ Could not close stale incident: {e}")
                return True

            except (ValueError, TypeError) as e:
                logger.warning(f"   ⚠️ Could not parse created_at '{created_at}': {e} — treating as stale")

        # No usable timestamp → can't judge age → treat as stale, allow new
        logger.warning(f"   ⚠️ Existing {incident_type.value} incident has no timestamp — treating as stale")
        return True

    def _send_alert(self, alert: Alert, incident_id: str = None):
        """
        Send alert to HealingAgent via Kafka.

        incident_id: the plain-string incident ID (already extracted from
        whatever db.create_incident() returned).  It is placed directly
        into the JSON payload so HealingAgent can use it without its own
        DB round-trip.
        """
        try:
            alert_dict = {
                "alert_id": alert.alert_id,
                "alert_type": alert.alert_type.value if hasattr(alert.alert_type, 'value') else str(alert.alert_type),
                "severity": alert.severity,
                "timestamp": alert.timestamp,
                "metrics_snapshot": alert.metrics_snapshot,
                "description": alert.description,
                # FIX: was `incident.incident_id` — `incident` was never defined
                # in this scope.  The caller already passes the extracted string
                # ID as this parameter.
                "incident_id": incident_id,
            }
            
            # Serialize to JSON string
            alert_json = json.dumps(alert_dict)
            
            # Send as bytes
            self.producer.send('alerts', alert_json)
            
            # CRITICAL: Flush to ensure message is sent immediately
            self.producer.flush()
            
            logger.info("=" * 80)
            logger.info(f"📤 ALERT SENT TO HEALING AGENT")
            logger.info("=" * 80)
            logger.info(f"Alert Type: {alert.alert_type.value if hasattr(alert.alert_type, 'value') else alert.alert_type}")
            logger.info(f"Severity: {alert.severity}")
            logger.info(f"Incident ID: {incident_id}")
            logger.info(f"Description: {alert.description}")
            logger.info("=" * 80)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to send alert: {e}", exc_info=True)
            return False

    def generate_synthetic_spike(self):
        """Generate synthetic latency/accuracy spike for testing"""
        if not self.test_mode:
            return
        
        current_time = time.time()
        if current_time - self.last_spike_time < self.spike_interval:
            return
        
        self.last_spike_time = current_time
        
        # Choose random spike type
        spike_type = random.choice(['latency', 'accuracy', 'drift'])
        
        if spike_type == 'latency':
            logger.warning("🔥 GENERATING SYNTHETIC LATENCY SPIKE FOR TESTING")
            for _ in range(60):
                self.latency_window.append(random.uniform(15, 30))
            self.check_latency_slo()
            
        elif spike_type == 'accuracy':
            logger.warning("🔥 GENERATING SYNTHETIC ACCURACY DROP FOR TESTING")
            for _ in range(120):
                self.accuracy_window.append(random.uniform(0.70, 0.85))
            self.check_model_accuracy()
            
        elif spike_type == 'drift':
            logger.warning("🔥 GENERATING SYNTHETIC DATA DRIFT FOR TESTING")
            for _ in range(200):
                self.feature_distributions.append(random.uniform(0.4, 0.6))
            for _ in range(200):
                self.feature_distributions.append(random.uniform(0.7, 0.9))
            self.check_data_drift()

    def check_heartbeats(self):
        """Monitor agent heartbeats and detect failures"""
        now = dt.datetime.now(dt.timezone.utc)
        
        for agent, last_seen in self.heartbeats.items():
            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=dt.timezone.utc)
            
            missing_sec = (now - last_seen).total_seconds()
            
            if missing_sec > self.heartbeat_timeout_sec:
                existing = self.db.get_open_incident_by_type(IncidentType.AGENT_DOWN)
                existing = self._parse_incident(existing)
                
                if existing and existing.get('agent') == agent:
                    continue
                
                alert = Alert(
                    alert_id=f"ALR-{agent}-{int(time.time())}",
                    alert_type=IncidentType.AGENT_DOWN,
                    severity="CRITICAL",
                    timestamp=now.isoformat(),
                    metrics_snapshot={"last_seen": last_seen.isoformat(), "agent": agent},
                    description=f"{agent} heartbeat missing for {missing_sec:.0f}s"
                )
                
                logger.warning(f"🚨 ALERT: {agent} is DOWN (missing for {missing_sec:.0f}s)")
                
                try:
                    # FIX: extract the plain string ID regardless of what
                    # create_incident() actually returns
                    result = self.db.create_incident(
                        incident_type=IncidentType.AGENT_DOWN,
                        metrics_snapshot=alert.metrics_snapshot,
                        description=alert.description
                    )
                    incident_id = _extract_incident_id(result)
                    
                    self._send_alert(alert, incident_id)
                    
                except Exception as e:
                    logger.error(f"Failed to create AGENT_DOWN incident: {e}")

    def check_latency_slo(self):
        """Monitor latency and detect SLO breaches"""
        if len(self.latency_window) < 20:
            return
        
        median_latency = float(np.median(self.latency_window))
        
        logger.debug(f"Latency check: median={median_latency:.2f}ms, threshold={self.latency_threshold_ms}ms")
        
        if median_latency > self.latency_threshold_ms:
            if not self._should_create_incident(
                IncidentType.LATENCY_SLO_BREACH, 
                'median_latency', 
                median_latency
            ):
                logger.warning(f"⏭️  Skipping duplicate LATENCY_SLO_BREACH alert (cooldown active)")
                return
            
            alert = Alert(
                alert_id=f"ALR-LAT-{int(time.time())}",
                alert_type=IncidentType.LATENCY_SLO_BREACH,
                severity="HIGH",
                timestamp=datetime.now(timezone.utc).isoformat(),
                metrics_snapshot={"median_latency": median_latency},
                description=f"Median latency {median_latency:.1f}ms exceeds threshold {self.latency_threshold_ms}ms"
            )
            
            logger.warning(f"🚨 ALERT: Latency SLO breach - {median_latency:.1f}ms > {self.latency_threshold_ms}ms")
            
            try:
                result = self.db.create_incident(
                    incident_type=IncidentType.LATENCY_SLO_BREACH,
                    metrics_snapshot=alert.metrics_snapshot,
                    description=alert.description
                )
                incident_id = _extract_incident_id(result)
                
                self._send_alert(alert, incident_id)
                
            except Exception as e:
                logger.error(f"Failed to create LATENCY_SLO_BREACH incident: {e}")

    def check_model_accuracy(self):
        """Monitor model accuracy and detect performance drops"""
        if len(self.accuracy_window) < 50:
            return
        
        accuracy = float(np.mean(self.accuracy_window))
        
        logger.debug(f"Accuracy check: {accuracy:.3f}, threshold={self.accuracy_threshold:.3f}")
        
        if accuracy < self.accuracy_threshold:
            if not self._should_create_incident(IncidentType.PERF_DROP):
                logger.warning(f"⏭️  Skipping duplicate PERF_DROP alert (cooldown active)")
                return
            
            alert = Alert(
                alert_id=f"ALR-PERF-{int(time.time())}",
                alert_type=IncidentType.PERF_DROP,
                severity="HIGH",
                timestamp=datetime.now(timezone.utc).isoformat(),
                metrics_snapshot={"accuracy": accuracy},
                description=f"Model accuracy {accuracy:.3f} below threshold {self.accuracy_threshold}"
            )
            
            logger.warning(f"🚨 ALERT: Model performance drop - accuracy {accuracy:.3f} < {self.accuracy_threshold:.3f}")
            
            try:
                result = self.db.create_incident(
                    incident_type=IncidentType.PERF_DROP,
                    metrics_snapshot=alert.metrics_snapshot,
                    description=alert.description
                )
                incident_id = _extract_incident_id(result)
                
                self._send_alert(alert, incident_id)
                
            except Exception as e:
                logger.error(f"Failed to create PERF_DROP incident: {e}")

    def check_data_drift(self):
        """Monitor for data distribution drift"""
        if len(self.feature_distributions) < 400:
            return
        
        recent = list(self.feature_distributions)[-200:]
        reference = list(self.feature_distributions)[:200]
        
        drift_score = abs(np.mean(recent) - np.mean(reference)) / (np.mean(reference) + 1e-6)
        
        logger.debug(f"Drift check: score={drift_score:.3f}, threshold={self.drift_threshold:.3f}")
        
        if drift_score > self.drift_threshold:
            if not self._should_create_incident(IncidentType.DATA_DRIFT):
                logger.warning(f"⏭️  Skipping duplicate DATA_DRIFT alert (cooldown active)")
                return
            
            alert = Alert(
                alert_id=f"ALR-DRIFT-{int(time.time())}",
                alert_type=IncidentType.DATA_DRIFT,
                severity="MEDIUM",
                timestamp=datetime.now(timezone.utc).isoformat(),
                metrics_snapshot={"drift_score": float(drift_score)},
                description=f"Data drift detected with score {drift_score:.3f}"
            )
            
            logger.warning(f"🚨 ALERT: Data drift detected - score {drift_score:.3f} > {self.drift_threshold:.3f}")
            
            try:
                result = self.db.create_incident(
                    incident_type=IncidentType.DATA_DRIFT,
                    metrics_snapshot=alert.metrics_snapshot,
                    description=alert.description
                )
                incident_id = _extract_incident_id(result)
                
                self._send_alert(alert, incident_id)
                
            except Exception as e:
                logger.error(f"Failed to create DATA_DRIFT incident: {e}")

    def process_metric(self, topic: str, message: str):
        """Process agent metrics from Kafka"""
        logger.warning(f"📨 process_metric CALLED — topic={topic}, msg_len={len(message) if message else 0}")
        if not self.running:
            logger.warning("   ⛔ self.running is False — dropping message")
            return
        
        start_time = time.time()
        
        try:
            metric = AgentMetric.from_json(message)
            agent = metric.agent
            
            # Update heartbeat
            self.heartbeats[agent] = dt.datetime.now(dt.timezone.utc)
            
            # Track latency
            if metric.latency_ms > 0:
                self.latency_window.append(metric.latency_ms)
            
            # Run checks
            self.check_heartbeats()
            self.check_latency_slo()
            
            # Generate synthetic spikes for testing
            self.generate_synthetic_spike()
            
            self.events_processed += 1
            if self.events_processed % 100 == 0:
                logger.info(f"✓ MonitoringAgent processed {self.events_processed} metrics")
            
            self.last_latency = (time.time() - start_time) * 1000
            
        except Exception as e:
            logger.error(f"Error processing metric: {e}", exc_info=True)

    def process_decision_feedback(self, topic: str, message: str):
        """Process decisions and feedback from Kafka"""
        logger.warning(f"📨 process_decision_feedback CALLED — topic={topic}, msg_len={len(message) if message else 0}")
        if not self.running:
            logger.warning("   ⛔ self.running is False — dropping message")
            return
        
        try:
            if topic == 'feedback':
                feedback = Feedback.from_json(message)
                is_correct = (feedback.actual_outcome == feedback.predicted_outcome)
                self.accuracy_window.append(1 if is_correct else 0)
                
                self.check_model_accuracy()
            
            elif topic == 'decisions':
                decision = Decision.from_json(message)
                
                if decision.confidence > 0:
                    self.feature_distributions.append(decision.confidence)
                    self.check_data_drift()
            
        except Exception as e:
            logger.error(f"Error processing {topic}: {e}", exc_info=True)

    async def heartbeat_loop(self):
        """
        Runs every 5 seconds on its own timer — completely independent of
        Kafka consumers.  Two jobs:
          1. Emit a live-status log every tick so we ALWAYS see output.
          2. Drive generate_synthetic_spike() on the clock so test alerts
             fire even if no consumer messages arrive.
        """
        tick = 0
        while self.running:
            tick += 1
            try:
                # ── live status ticker (ALWAYS printed) ──────────────────
                logger.warning(
                    f"💓 TICK #{tick} | "
                    f"events_processed={self.events_processed} | "
                    f"latency_window={len(self.latency_window)} | "
                    f"accuracy_window={len(self.accuracy_window)} | "
                    f"feature_distributions={len(self.feature_distributions)} | "
                    f"heartbeats={list(self.heartbeats.keys())}"
                )

                # ── drive the spike generator on the clock ───────────────
                # Previously this only ran inside process_metric() which is
                # gated on consumer delivery.  If consumers aren't firing,
                # spikes never fire and no alerts ever go out.
                self.generate_synthetic_spike()

                # ── normal heartbeat to Kafka + DB ───────────────────────
                metric = AgentMetric(
                    agent="MonitoringAgent",
                    status="OK",
                    latency_ms=self.last_latency,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    cpu_percent=self.process.cpu_percent(),
                    memory_mb=self.process.memory_info().rss / 1024 / 1024,
                    events_processed=self.events_processed
                )
                
                self.producer.send('agent-metrics', metric.to_json())
                self.producer.flush()
                
                self.db.update_agent_health(
                    agent_name="MonitoringAgent",
                    status="OK",
                    latency_ms=metric.latency_ms,
                    cpu_percent=metric.cpu_percent,
                    memory_mb=metric.memory_mb,
                    events_processed=self.events_processed
                )
                
            except Exception as e:
                logger.error(f"Heartbeat error: {e}", exc_info=True)
            
            await asyncio.sleep(5)  # tick every 5s — fast enough to see immediately

    async def run(self):
        """Main agent loop"""
        heartbeat_task = asyncio.create_task(self.heartbeat_loop())
        
        try:
            logger.warning("🔧 Creating metrics_consumer...")
            self.metrics_consumer = create_consumer(
                self.config.kafka,
                ['agent-metrics'],
                'monitoring-metrics-group',
                self.process_metric
            )
            logger.warning("✓ metrics_consumer created")
            
            logger.warning("🔧 Creating decisions_consumer...")
            self.decisions_consumer = create_consumer(
                self.config.kafka,
                ['decisions', 'feedback'],
                'monitoring-decisions-group',
                self.process_decision_feedback
            )
            logger.warning("✓ decisions_consumer created")
        
            logger.info("=" * 80)
            logger.info("🚀 MonitoringAgent starting consumers...")
            logger.info("=" * 80)
            logger.info("📡 CONSUMING FROM:")
            logger.info("   → 'agent-metrics' topic")
            logger.info("   → 'decisions' and 'feedback' topics")
            logger.info("")
            logger.info("📤 PRODUCING TO:")
            logger.info("   → 'alerts' topic (to HealingAgent)")
            logger.info("=" * 80)
            if self.test_mode:
                logger.info("⚠️  TEST MODE ACTIVE - Will generate synthetic spikes")
                logger.info(f"   Spike interval: {self.spike_interval}s")
                logger.info("=" * 80)

            loop = asyncio.get_event_loop()
            logger.warning("🚀 Launching consumer .start() threads via run_in_executor...")
            await asyncio.gather(
                loop.run_in_executor(None, self.metrics_consumer.start),
                loop.run_in_executor(None, self.decisions_consumer.start)
            )
            logger.warning("⚠️  asyncio.gather returned — consumers have exited")
        finally:
            self.cleanup()
            heartbeat_task.cancel()

    def cleanup(self):
        """Clean up resources on shutdown"""
        logger.info("Cleaning up resources...")
        self.running = False
        
        if hasattr(self, 'metrics_consumer'):
            self.metrics_consumer.close()
        if hasattr(self, 'decisions_consumer'):
            self.decisions_consumer.close()
        if hasattr(self, 'producer'):
            self.producer.flush()
            self.producer.close()
        
        logger.info("✓ Shutdown complete")


if __name__ == "__main__":
    agent = MonitoringAgent()
    asyncio.run(agent.run())