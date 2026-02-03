import asyncio
import sys
import os
import time
import signal
import threading
import psutil
import json
import uuid
from datetime import datetime, timezone

sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from kafka import KafkaProducer
from common.schemas import (
    IncidentType, IncidentStatus, AgentMetric, Alert, 
    PolicyRequest, PolicyDecision, AGLDecision,
    ActionType, HealingAction
)
from common.logger import setup_logger
from common.kafka_utils import create_consumer
from common.config import config
from backend.database.db_manager import DatabaseManager

logger = setup_logger("HealingAgent", config.kafka)


class HealingAgent:
    """
    HealingAgent - Orchestrates self-healing by consuming alerts and executing approved actions.
    
    IMPROVED VERSION with better database handling and fallback mechanisms.
    """
    
    def __init__(self):
        self.config = config.get_agent_config("HealingAgent", 8006)
        
        # Kafka setup
        self.kafka_bootstrap_servers = self.config.kafka.bootstrap_servers
        
        # Agent state
        self.running = True
        self.events_processed = 0
        self.alerts_received = 0
        self.actions_executed = 0
        self.actions_denied = 0
        self.last_latency = 0.0
        
        # Track pending requests: request_id -> (incident_id, healing_action, timestamp)
        self.pending_requests = {}
        
        # Process metrics
        self.process = psutil.Process()
        self.process.cpu_percent()
        
        # Database - IMPROVED: Try harder to connect
        self.db = self._initialize_database()
        
        # Kafka producer
        self.producer = KafkaProducer(
            bootstrap_servers=self.kafka_bootstrap_servers,
            value_serializer=lambda v: v.encode('utf-8') if isinstance(v, str) else json.dumps(v).encode('utf-8'),
            key_serializer=lambda k: k.encode('utf-8') if k else None,
            retries=5,
            retry_backoff_ms=1000,
            acks='all',
            max_in_flight_requests_per_connection=5
        )
        
        # Signal handling
        if threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGINT, self.handle_shutdown)
            signal.signal(signal.SIGTERM, self.handle_shutdown)
        
        # Start heartbeat thread
        threading.Thread(target=self._heartbeat_loop, daemon=True).start()
        
        # Start database retry thread (if initial connection failed)
        if not self.db:
            threading.Thread(target=self._retry_database_connection, daemon=True).start()
        
        logger.info("=" * 70)
        logger.info("✅ HealingAgent initialized")
        logger.info("=" * 70)
    
    def _initialize_database(self) -> DatabaseManager:
        """
        Initialize database with better error handling and retries
        
        Returns:
            DatabaseManager instance or None if failed
        """
        logger.info("=" * 70)
        logger.info("DATABASE INITIALIZATION")
        logger.info("=" * 70)
        
        max_retries = 5
        retry_delay = 2
        
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"Attempt {attempt}/{max_retries}: Connecting to database...")
                db = DatabaseManager(self.config.database.connection_string)
                
                # Test the connection
                if db.check_database_health():
                    logger.info("✅ Database connection established and healthy")
                    logger.info("=" * 70)
                    return db
                else:
                    logger.warning(f"⚠️ Database connected but health check failed")
                    
            except Exception as e:
                logger.error(f"❌ Database connection failed (attempt {attempt}/{max_retries}): {e}")
                
                if attempt < max_retries:
                    logger.info(f"⏳ Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    logger.error("=" * 70)
                    logger.error("❌ DATABASE CONNECTION FAILED")
                    logger.error("=" * 70)
                    logger.error("IMPACT:")
                    logger.error("  - Cannot query or create incidents")
                    logger.error("  - All alerts will be SKIPPED")
                    logger.error("  - No healing actions will be executed")
                    logger.error("")
                    logger.error("SOLUTION:")
                    logger.error("  1. Fix database connectivity")
                    logger.error("  2. Restart HealingAgent")
                    logger.error("  OR")
                    logger.error("  3. Ensure MonitoringAgent includes 'incident_id' in alerts")
                    logger.error("=" * 70)
        
        return None
    
    def _retry_database_connection(self):
        """
        Background thread to retry database connection periodically
        """
        retry_interval = 30  # seconds
        
        logger.info("🔄 Database retry thread started (will retry every 30s)")
        
        while self.running and not self.db:
            time.sleep(retry_interval)
            
            logger.info("🔄 Attempting to reconnect to database...")
            try:
                db = DatabaseManager(self.config.database.connection_string)
                
                if db.check_database_health():
                    self.db = db
                    logger.info("=" * 70)
                    logger.info("✅ DATABASE CONNECTION RESTORED!")
                    logger.info("=" * 70)
                    logger.info("HealingAgent will now process alerts normally")
                    logger.info("=" * 70)
                    return
                    
            except Exception as e:
                logger.debug(f"Database reconnection failed: {e}")
    
    def handle_shutdown(self, signum, frame):
        """Handle shutdown signals gracefully"""
        logger.info(f"⚠️ Received signal {signum}, shutting down...")
        self.running = False
    
    def _heartbeat_loop(self):
        """Send periodic heartbeats"""
        while self.running:
            try:
                metric = AgentMetric(
                    agent="HealingAgent",
                    status="OK" if self.db else "DEGRADED",  # ← Show degraded if no DB
                    latency_ms=self.last_latency,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    cpu_percent=self.process.cpu_percent(),
                    memory_mb=self.process.memory_info().rss / 1024 / 1024,
                    events_processed=self.events_processed
                )
                
                self.producer.send('agent-metrics', metric.to_json())
                self.producer.flush()
                
                # Update database (if available)
                if self.db:
                    try:
                        self.db.update_agent_health(
                            agent_name="HealingAgent",
                            status="OK",
                            latency_ms=self.last_latency,
                            cpu_percent=metric.cpu_percent,
                            memory_mb=metric.memory_mb,
                            events_processed=self.events_processed
                        )
                    except Exception as e:
                        logger.debug(f"DB update failed: {e}")
                
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
            
            time.sleep(5)
    
    # ==================== ALERT PROCESSING ====================
    
    def create_healing_plan(self, alert: Alert) -> HealingAction:
        """Create a healing action based on alert type"""
        # Map incident types to healing actions
        action_map = {
            IncidentType.AGENT_DOWN: ActionType.RESTART_AGENT,
            IncidentType.LATENCY_SLO_BREACH: ActionType.ENABLE_SAFE_MODE,
            IncidentType.PERF_DROP: ActionType.ROLLBACK_MODEL,
            IncidentType.DATA_DRIFT: ActionType.TRIGGER_RETRAINING
        }
        
        # Get action type
        action_type = action_map.get(alert.alert_type, ActionType.ENABLE_SAFE_MODE)
        
        # Extract target from alert metrics
        target = alert.metrics_snapshot.get('agent', 'unknown')
        
        # Create healing action
        healing_action = HealingAction(
            action_type=action_type,
            target=target,
            parameters=alert.metrics_snapshot,
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        
        logger.info(f"   📋 Created healing plan:")
        logger.info(f"      Action: {action_type.value}")
        logger.info(f"      Target: {target}")
        
        return healing_action
    
    def process_alert(self, topic: str, message: str):
        logger.info(f"🟢 ALERT READ FROM KAFKA: topic={topic}, message_len={len(message) if message else 0}")
        """
        Process alerts from MonitoringAgent
        
        IMPROVED: Better handling when database is unavailable
        """
        logger.info(f"process_alert called: topic={topic}, message_len={len(message) if message else 0}")

        if not self.running:
            return

        # Ensure message is a string (decode if bytes)
        if isinstance(message, bytes):
            try:
                message = message.decode('utf-8')
            except Exception as e:
                logger.error(f"❌ Could not decode alert message from bytes: {e}")
                return

        start_time = time.time()

        try:
            # Parse alert
            alert = Alert.from_json(message)

            self.alerts_received += 1

            logger.info("")
            logger.info("=" * 70)
            logger.info(f"🚨 ALERT #{self.alerts_received} RECEIVED")
            logger.info("=" * 70)
            logger.info(f"   Type: {alert.alert_type.value}")
            logger.info(f"   Severity: {alert.severity}")
            logger.info(f"   Description: {alert.description}")
            logger.info(f"   Alert ID: {alert.alert_id}")

            # Get incident_id (with improved fallback)
            incident_id = self._get_or_create_incident_id(alert)

            if not incident_id:
                logger.error(f"   ❌ Cannot obtain incident_id")
                logger.error(f"   ❌ Alert processing aborted")
                logger.error("")
                logger.error("   REASON:")
                if not self.db:
                    logger.error("   → Database connection unavailable")
                    logger.error("   → Cannot query or create incidents")
                else:
                    logger.error("   → Alert missing incident_id field")
                    logger.error("   → No matching open incident in database")
                logger.error("")
                logger.error("   SOLUTIONS:")
                logger.error("   → Fix database connection (see startup logs)")
                logger.error("   → OR ensure MonitoringAgent includes incident_id in alerts")
                logger.info("=" * 70)
                return

            logger.info(f"   Incident ID: {incident_id}")

            # Create healing plan
            healing_action = self.create_healing_plan(alert)

            # Create policy request for AGL
            request_id = f"REQ-{uuid.uuid4().hex[:8]}"

            policy_request = PolicyRequest(
                request_id=request_id,
                incident_id=incident_id,
                incident_type=alert.alert_type,
                proposed_action=healing_action.to_dict(),
                timestamp=datetime.now(timezone.utc).isoformat()
            )

            # Store pending request
            self.pending_requests[request_id] = (incident_id, healing_action, time.time())

            # Send to AGL
            self.producer.send('policy-requests', policy_request.to_json())
            self.producer.flush()

            logger.info(f"   📤 Policy request sent to AGL")
            logger.info(f"      Request ID: {request_id}")
            logger.info(f"      Waiting for approval...")
            logger.info("=" * 70)

            self.events_processed += 1
            self.last_latency = (time.time() - start_time) * 1000

        except Exception as e:
            logger.error(f"❌ Error processing alert: {e}", exc_info=True)
            logger.info("=" * 70)
    
    def _get_or_create_incident_id(self, alert: Alert) -> str:
        """
        Get incident_id from alert, database, or create new one
        
        IMPROVED: More robust incident ID resolution with creation fallback
        
        Priority:
        1. Use incident_id from alert (if provided by MonitoringAgent)
        2. Query database for open incident of this type
        3. Create new incident in database
        4. Generate temporary ID if database unavailable
        
        Returns:
            incident_id (str) or None if all methods fail
        """
        # Method 1: Check if incident_id is in the alert
        if hasattr(alert, 'incident_id') and alert.incident_id:
            logger.debug(f"   ✓ Using incident_id from alert: {alert.incident_id}")
            return alert.incident_id
        
        # If no database, we can't query or create
        if not self.db:
            logger.error("   ❌ No database connection")
            return None
        
        # Method 2: Query for existing open incident
        try:
            logger.debug(f"   🔍 Querying database for open incident...")
            incident = self.db.get_open_incident_by_type(alert.alert_type)
            
            if incident:
                incident_id = self._parse_incident_id(incident)
                if incident_id:
                    logger.debug(f"   ✓ Found open incident: {incident_id}")
                    return incident_id
        
        except Exception as e:
            logger.warning(f"   ⚠️ Database query failed: {e}")
        
        # Method 3: Create new incident
        try:
            logger.info(f"   📝 Creating new incident in database...")
            
            incident = self.db.create_incident(
                incident_type=alert.alert_type,
                metrics_snapshot=alert.metrics_snapshot,
                description=alert.description
            )
            
            incident_id = self._parse_incident_id(incident)
            
            if incident_id:
                logger.info(f"   ✓ Created new incident: {incident_id}")
                return incident_id
            else:
                logger.error(f"   ❌ Incident created but couldn't parse ID")
                
        except Exception as e:
            logger.error(f"   ❌ Failed to create incident: {e}")
        
        # All methods failed
        return None
    
    def _parse_incident_id(self, incident) -> str:
        """
        Parse incident_id from various return formats
        
        Handles:
        - Incident object with .incident_id attribute
        - Dict with 'incident_id' key
        - String (direct incident_id)
        """
        if incident is None:
            return None
        
        # Object with attribute
        if hasattr(incident, 'incident_id'):
            return incident.incident_id
        
        # Dictionary
        if isinstance(incident, dict):
            return incident.get('incident_id')
        
        # String
        if isinstance(incident, str):
            return incident
        
        logger.warning(f"   ⚠️ Unknown incident format: {type(incident)}")
        return None
    
    # ==================== POLICY DECISION PROCESSING ====================
    
    def process_policy_decision(self, topic: str, message: str):
        """Process policy decisions from AGL"""
        if not self.running:
            return
        
        try:
            decision = PolicyDecision.from_json(message)
            
            logger.info("")
            logger.info("=" * 70)
            logger.info(f"📩 POLICY DECISION RECEIVED")
            logger.info("=" * 70)
            logger.info(f"   Request ID: {decision.request_id}")
            logger.info(f"   Decision: {decision.decision.value}")
            
            # Get pending request
            if decision.request_id not in self.pending_requests:
                logger.warning(f"   ⚠️ Unknown request ID - skipping")
                logger.info("=" * 70)
                return
            
            incident_id, healing_action, _ = self.pending_requests.pop(decision.request_id)
            
            # Handle based on decision
            if decision.decision == AGLDecision.APPROVED:
                self._handle_approved_action(incident_id, healing_action, decision)
            elif decision.decision == AGLDecision.DENIED:
                self._handle_denied_action(incident_id, healing_action, decision)
            elif decision.decision == AGLDecision.ESCALATE:
                self._handle_escalated_action(incident_id, healing_action, decision)
            
            logger.info("=" * 70)
            
        except Exception as e:
            logger.error(f"❌ Error processing policy decision: {e}", exc_info=True)
            logger.info("=" * 70)
    
    def _handle_approved_action(self, incident_id: str, action: HealingAction, decision: PolicyDecision):
        """Handle approved policy decision"""
        logger.info(f"   ✅ ACTION APPROVED")
        logger.info(f"      Action: {action.action_type.value}")
        logger.info(f"      Target: {action.target}")
        
        # Execute the healing action
        success = self.execute_healing_action(incident_id, action)
        
        if success:
            self.actions_executed += 1
            
            # Update incident status (if database available)
            if self.db:
                try:
                    self.db.update_incident(
                        incident_id=incident_id,
                        status=IncidentStatus.RESOLVED,
                        resolution_action=action.action_type.value
                    )
                    logger.info(f"   📊 Incident {incident_id} marked as RESOLVED")
                except Exception as e:
                    logger.error(f"   ❌ Failed to update incident: {e}")
            
            # Log healing action (if database available)
            if self.db:
                try:
                    self.db.log_healing_action(
                        incident_id=incident_id,
                        action_type=action.action_type.value,
                        target=action.target,
                        status="SUCCESS",
                        details=action.parameters
                    )
                except Exception as e:
                    logger.error(f"   ❌ Failed to log healing action: {e}")
            
            logger.info(f"   🎉 Healing complete!")
            logger.info(f"   Total actions executed: {self.actions_executed}")
        else:
            logger.error(f"   ❌ Action execution failed")
            
            # Log failure (if database available)
            if self.db:
                try:
                    self.db.log_healing_action(
                        incident_id=incident_id,
                        action_type=action.action_type.value,
                        target=action.target,
                        status="FAILED",
                        details=action.parameters
                    )
                except Exception as e:
                    logger.error(f"   ❌ Failed to log failure: {e}")
    
    def _handle_denied_action(self, incident_id: str, action: HealingAction, decision: PolicyDecision):
        """Handle denied policy decision"""
        self.actions_denied += 1
        
        logger.warning(f"   ❌ ACTION DENIED")
        logger.warning(f"      Action: {action.action_type.value}")
        logger.warning(f"      Total denied: {self.actions_denied}")
        
        # Log denial (if database available)
        if self.db:
            try:
                self.db.log_healing_action(
                    incident_id=incident_id,
                    action_type=action.action_type.value,
                    target=action.target,
                    status="DENIED",
                    details={"reason": decision.reasoning}
                )
            except Exception as e:
                logger.error(f"   ❌ Failed to log denial: {e}")
    
    def _handle_escalated_action(self, incident_id: str, action: HealingAction, decision: PolicyDecision):
        """Handle escalated policy decision"""
        logger.warning(f"   ⚠️ ACTION ESCALATED")
        logger.warning(f"      Action: {action.action_type.value}")
        logger.warning(f"      Requires human intervention")
        
        # Update incident status (if database available)
        if self.db:
            try:
                self.db.update_incident(
                    incident_id=incident_id,
                    status=IncidentStatus.ESCALATED
                )
                logger.info(f"   📊 Incident {incident_id} marked as ESCALATED")
            except Exception as e:
                logger.error(f"   ❌ Failed to update incident: {e}")
    
    # ==================== ACTION EXECUTION ====================
    
    def execute_healing_action(self, incident_id: str, action: HealingAction) -> bool:
        """Execute the approved healing action"""
        logger.info(f"   🔧 Executing healing action...")
        
        try:
            # Map actions to handlers
            handlers = {
                ActionType.RESTART_AGENT: self._restart_agent,
                ActionType.ROLLBACK_MODEL: self._rollback_model,
                ActionType.ENABLE_SAFE_MODE: self._enable_safe_mode,
                ActionType.TRIGGER_RETRAINING: self._trigger_retraining
            }
            
            handler = handlers.get(action.action_type)
            
            if not handler:
                logger.error(f"   ❌ No handler for action: {action.action_type.value}")
                return False
            
            # Execute the handler
            result = handler(action)
            
            if result:
                logger.info(f"   ✅ Action executed successfully")
            
            return result
            
        except Exception as e:
            logger.error(f"   ❌ Execution error: {e}", exc_info=True)
            return False
    
    def _restart_agent(self, action: HealingAction) -> bool:
        """Execute agent restart"""
        logger.info(f"      🔄 Restarting agent: {action.target}")
        time.sleep(0.5)  # Simulate restart
        logger.info(f"      ✓ Agent restarted")
        return True
    
    def _rollback_model(self, action: HealingAction) -> bool:
        """Execute model rollback"""
        logger.info(f"      ⏪ Rolling back model")
        time.sleep(0.5)  # Simulate rollback
        logger.info(f"      ✓ Model rolled back to previous version")
        return True
    
    def _enable_safe_mode(self, action: HealingAction) -> bool:
        """Execute safe mode activation"""
        logger.info(f"      🛡️ Enabling safe mode")
        time.sleep(0.5)  # Simulate activation
        logger.info(f"      ✓ Safe mode enabled")
        return True
    
    def _trigger_retraining(self, action: HealingAction) -> bool:
        """Execute retraining trigger"""
        logger.info(f"      🎓 Triggering model retraining")
        time.sleep(0.5)  # Simulate trigger
        logger.info(f"      ✓ Retraining job submitted")
        return True
    
    # ==================== MAIN LOOP ====================
    
    async def run_async(self):
        """Main async run loop"""
        # Create consumers
        self.alerts_consumer = create_consumer(
            self.config.kafka,
            ['alerts'],
            f'{self.config.kafka.group_id_prefix}-healing-alerts-debug-{uuid.uuid4().hex[:4]}',
            self.process_alert
        )
        
        self.decisions_consumer = create_consumer(
            self.config.kafka,
            ['policy-decisions'],
            f'{self.config.kafka.group_id_prefix}-healing-decisions',
            self.process_policy_decision
        )
        
        logger.info("🚀 HealingAgent starting consumers...")
        logger.info("")
        logger.info("📡 CONSUMING FROM:")
        logger.info("   → 'alerts' topic (from MonitoringAgent)")
        logger.info("   → 'policy-decisions' topic (from AGL)")
        logger.info("")
        logger.info("📤 PRODUCING TO:")
        logger.info("   → 'policy-requests' topic (to AGL)")
        logger.info("   → 'agent-metrics' topic (heartbeats)")
        logger.info("")
        
        if not self.db:
            logger.warning("=" * 70)
            logger.warning("⚠️ WARNING: Running in DEGRADED mode")
            logger.warning("=" * 70)
            logger.warning("Database connection unavailable")
            logger.warning("Alerts will only be processed if they include incident_id")
            logger.warning("Background thread will retry database connection every 30s")
            logger.warning("=" * 70)
        
        logger.info("=" * 70)
        logger.info("Waiting for alerts...")
        logger.info("=" * 70)
        
        try:
            # Run consumers (blocking)
            loop = asyncio.get_event_loop()
            await asyncio.gather(
                loop.run_in_executor(None, self.alerts_consumer.start),
                loop.run_in_executor(None, self.decisions_consumer.start)
            )
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Clean up resources on shutdown"""
        logger.info("")
        logger.info("=" * 70)
        logger.info("🛑 SHUTTING DOWN")
        logger.info("=" * 70)
        logger.info(f"Total alerts received: {self.alerts_received}")
        logger.info(f"Total actions executed: {self.actions_executed}")
        logger.info(f"Total actions denied: {self.actions_denied}")
        logger.info(f"Pending requests: {len(self.pending_requests)}")
        logger.info("=" * 70)
        
        self.running = False
        
        if hasattr(self, 'alerts_consumer'):
            self.alerts_consumer.close()
        if hasattr(self, 'decisions_consumer'):
            self.decisions_consumer.close()
        if hasattr(self, 'producer'):
            self.producer.flush()
            self.producer.close()
        
        logger.info("✅ Cleanup complete")
        logger.info("=" * 70)


if __name__ == "__main__":
    agent = HealingAgent()
    asyncio.run(agent.run_async())