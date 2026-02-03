from sqlalchemy.orm import Session
from backend.database.models import (
    Incident, HealingAction, ConfigHistory, MemoryChunk,
    AgentHealth, PerformanceMetric, DriftMetric, init_db, get_session, Base
)
from sqlalchemy import text
from backend.database.models import DecisionRecord
from common.schemas import IncidentType, IncidentStatus, AGLDecision, ActionResult
from datetime import datetime, timedelta
import datetime as dt
from typing import Optional, List, Dict, Any, Union
import logging
import uuid
import math

logger = logging.getLogger(__name__)


def sanitize_json(obj):
    """
    Recursively sanitize JSON to remove NaN, Infinity, and -Infinity values.
    PostgreSQL JSON type cannot handle these values.
    """
    if isinstance(obj, dict):
        return {k: sanitize_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_json(v) for v in obj]
    elif isinstance(obj, float):
        if math.isinf(obj) or math.isnan(obj):
            return None  # Replace invalid floats with None
        return obj
    return obj


class DatabaseManager:
    """Fixed DatabaseManager with all methods consolidated and JSON sanitization"""
    
    def __init__(self, connection_string: str = None):
        if not connection_string:
            from common.config import config
            connection_string = config.database.connection_string
        self.engine = init_db(connection_string)
        logger.info("Database initialized successfully")
    
    def get_session(self) -> Session:
        return get_session(self.engine)
    
    def create_tables(self):
        """Create all tables in the database"""
        Base.metadata.create_all(self.engine)
        logger.info("Database tables created successfully")
    
    def check_database_health(self) -> bool:
        """Check if the database connection is healthy and log status."""
        try:
            session = self.get_session()
            session.execute(text("SELECT 1"))  # ← FIXED: Added text() wrapper
            session.close()
            logger.info("Database health check: OK")
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False
    
    def _to_enum(self, value: Any, enum_class: Any) -> Any:
        """Convert string or value to enum, with intelligent fallback"""
        if value is None:
            return None
        if isinstance(value, enum_class):
            return value
        if isinstance(value, str):
            val = value.upper()
            # Common mapping fixes
            if val == "APPROVE": val = "APPROVED"
            if val == "DENY": val = "DENIED"
            if val == "SUCCESS": val = "SUCCESS"
            if val == "FAIL": val = "FAIL"
            try:
                return enum_class(val)
            except ValueError:
                # Try searching by name if value fails
                for item in enum_class:
                    if item.name == val or item.value == val:
                        return item
                logger.error(f"Cannot convert {value} to {enum_class.__name__}")
                return value
        return value

    # ========== RAW EVENT & PREDICTION STORAGE ==========
    
    def store_raw_event(self, trace_id: str, timestamp, source_file: str, data: dict):
        """Store raw event from IngestAgent"""
        from backend.database.models import RawEventRecord
        session = self.get_session()
        try:
            # Sanitize data to remove Infinity/NaN values
            sanitized_data = sanitize_json(data)
            
            record = RawEventRecord(
                trace_id=trace_id,
                timestamp=timestamp,
                source_file=source_file,
                data=sanitized_data,
            )
            session.add(record)
            session.commit()
            logger.debug(f"Stored raw event {trace_id}")
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to store raw event: {e}")
        finally:
            session.close()

    def store_prediction(self, trace_id: str, timestamp, model_version: str, 
                        prediction: str, confidence: float, latency_ms: float, 
                        features: dict, source_file: str):
        """Store prediction from ModelAgent"""
        from backend.database.models import PredictionRecord
        session = self.get_session()
        try:
            # CRITICAL: Sanitize features to remove Infinity/NaN values
            # PostgreSQL JSON type cannot handle these values
            sanitized_features = sanitize_json(features)
            
            # Also sanitize confidence and latency_ms
            if math.isinf(confidence) or math.isnan(confidence):
                confidence = 0.0
            if math.isinf(latency_ms) or math.isnan(latency_ms):
                latency_ms = 0.0
            
            record = PredictionRecord(
                trace_id=trace_id,
                timestamp=timestamp,
                model_version=model_version,
                prediction=prediction,
                confidence=confidence,
                latency_ms=latency_ms,
                features=sanitized_features,
                source_file=source_file,
            )
            session.add(record)
            session.commit()
            logger.debug(f"Stored prediction {trace_id}")
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to store prediction: {e}")
            raise
        finally:
            session.close()

    def store_decision(self, trace_id: str, timestamp: str, decision: str, 
                    reasoning: str = None, confidence: float = None, 
                    extra_data: dict = None):  # ← Changed from 'metadata' to 'extra_data'
        """
        Store a decision record in the database.
        
        Args:
            trace_id: Unique identifier for the event
            timestamp: ISO format timestamp
            decision: The decision made (BLOCK, ALERT, MONITOR, ALLOW)
            reasoning: Explanation for the decision
            confidence: Confidence score from prediction
            extra_data: Additional metadata (model_version, latency, etc.)
        """
        try:
            session = get_session(self.engine)
            
            # Parse timestamp
            if isinstance(timestamp, str):
                ts = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            else:
                ts = timestamp
            
            record = DecisionRecord(
                trace_id=trace_id,
                timestamp=ts,
                decision=decision,
                reasoning=reasoning,
                confidence=confidence,
                extra_data=extra_data  # ← Changed from metadata to extra_data
            )
            
            session.add(record)
            session.commit()
            session.close()
            
        except Exception as e:
            if 'session' in locals():
                session.rollback()
                session.close()
            raise Exception(f"Failed to store decision: {e}")

    # ========== INCIDENT MANAGEMENT ==========

    def create_incident(
        self,
        incident_type: Any = None,
        metrics_snapshot: Dict[str, Any] = None,
        description: str = "No description provided",
        incident_id: Optional[str] = None,
        *args,
        **kwargs
    ) -> Incident:
        """Create a new incident. incident_id is optional and will be generated if not provided."""
        session = self.get_session()
        try:
            # Handle cases where incident_id might be passed as first positional arg
            actual_incident_id = incident_id or kwargs.get('incident_id')
                
            actual_incident_type = incident_type
            actual_metrics = metrics_snapshot
            actual_desc = description

            # If incident_type looks like an ID and incident_id is None, swap them
            if isinstance(incident_type, str) and incident_type.startswith("INC-") and actual_incident_id is None:
                actual_incident_id = incident_type

            target_type = self._to_enum(actual_incident_type, IncidentType)

            if not actual_incident_id:
                actual_incident_id = f"INC-{uuid.uuid4().hex[:8].upper()}"
            
            # Sanitize metrics snapshot
            sanitized_metrics = sanitize_json(actual_metrics or {})
                
            incident = Incident(
                incident_id=actual_incident_id,
                type=target_type,
                detected_at=dt.datetime.now(dt.timezone.utc),
                status=IncidentStatus.OPEN,
                metrics_snapshot=sanitized_metrics,
                description=actual_desc
            )
            session.add(incident)
            session.commit()
            logger.info(f"Created incident {actual_incident_id} of type {target_type}")
            return actual_incident_id
        except Exception as e:
            if session:
                session.rollback()
            logger.error(f"Failed to create incident: {e}")
            raise
        finally:
            if session:
                session.close()

    def get_open_incident_by_type(self, incident_type: Any) -> Optional[str]:
        """Get the most recent open incident of a specific type"""
        session = self.get_session()
        try:
            target_type = self._to_enum(incident_type, IncidentType)
            incident = session.query(Incident)\
                .filter(Incident.status == IncidentStatus.OPEN, Incident.type == target_type)\
                .order_by(Incident.detected_at.desc())\
                .first()
            
            return incident.incident_id if incident else None
        except Exception as e:
            logger.error(f"Error getting open incident: {e}")
            return None
        finally:
            session.close()

    def update_incident_status(
        self,
        incident_id: str,
        status: Any,
        resolved_at: Optional[datetime] = None,
        mttr_seconds: Optional[float] = None
    ):
        """Update incident status"""
        session = self.get_session()
        try:
            status_enum = self._to_enum(status, IncidentStatus)

            incident = session.query(Incident).filter_by(incident_id=incident_id).first()
            if incident:
                incident.status = status_enum
                if resolved_at:
                    incident.resolved_at = resolved_at
                elif status_enum == IncidentStatus.RESOLVED:
                    incident.resolved_at = dt.datetime.now(dt.timezone.utc)
                
                if mttr_seconds:
                    incident.mttr_seconds = mttr_seconds
                elif incident.resolved_at and incident.detected_at:
                    # Auto-calculate MTTR if possible
                    delta = incident.resolved_at - incident.detected_at
                    incident.mttr_seconds = delta.total_seconds()
                    
                session.commit()
                logger.info(f"Updated incident {incident_id} status to {status_enum}")
            else:
                logger.warning(f"Incident {incident_id} not found")
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to update incident status: {e}")
            raise
        finally:
            session.close()

    # ========== HEALING ACTIONS ==========

    def log_healing_action(
        self,
        incident_id: str = None,
        action_type: str = "UNKNOWN",
        action_details: Dict[str, Any] = None,
        agl_decision: Any = "PENDING",
        *args,
        **kwargs
    ):
        """Log a healing action taken by an agent."""
        session = self.get_session()
        try:
            actual_incident_id = incident_id or kwargs.get('incident_id')
            if not actual_incident_id and args:
                actual_incident_id = args[0]
                
            if not actual_incident_id:
                logger.error("Cannot log healing action without incident_id")
                return

            decision_enum = self._to_enum(agl_decision or kwargs.get('agl_decision'), AGLDecision)
            
            # Sanitize action details
            sanitized_details = sanitize_json(action_details or {})

            action = HealingAction(
                action_id=f"ACT-{uuid.uuid4().hex[:8].upper()}",
                incident_id=actual_incident_id,
                proposed_action={"type": action_type, "details": sanitized_details},
                agl_decision=decision_enum,
                approved_action={"type": action_type, "details": sanitized_details} if decision_enum == AGLDecision.APPROVED else None,
                executed_at=dt.datetime.now(dt.timezone.utc) if decision_enum == AGLDecision.APPROVED else None,
                result=ActionResult.SUCCESS if decision_enum == AGLDecision.APPROVED else None,
                reasoning=f"Decision {decision_enum.value if hasattr(decision_enum, 'value') else decision_enum} by AGL"
            )
            session.add(action)
            session.commit()
            logger.info(f"Logged healing action for incident {actual_incident_id}: {decision_enum}")
        except Exception as e:
            if session:
                session.rollback()
            logger.error(f"Failed to log healing action: {e}")
        finally:
            if session:
                session.close()

    # ========== MEMORY STORAGE ==========

    def store_memory(
        self,
        incident_type: Any,
        action_taken: Dict[str, Any],
        outcome: str,
        metadata: Dict[str, Any]
    ):
        """Store memory of incident resolution for learning"""
        session = self.get_session()
        try:
            inc_type = self._to_enum(incident_type, IncidentType)
            if not isinstance(inc_type, IncidentType):
                # Intelligent mapping fallback
                val = str(incident_type).upper()
                if "LATENCY" in val:
                    inc_type = IncidentType.LATENCY_SLO_BREACH
                elif "DRIFT" in val:
                    inc_type = IncidentType.DATA_DRIFT
                elif "PERF" in val or "ACCURACY" in val:
                    inc_type = IncidentType.PERF_DROP
                elif "DOWN" in val or "RESTART" in val:
                    inc_type = IncidentType.AGENT_DOWN
                else:
                    inc_type = IncidentType.LATENCY_SLO_BREACH
            
            # Sanitize action_taken and metadata
            sanitized_action = sanitize_json(action_taken)
            sanitized_metadata = sanitize_json(metadata)
                
            memory = MemoryChunk(
                memory_id=f"MEM-{uuid.uuid4().hex[:8].upper()}",
                incident_type=inc_type,
                incident_summary=sanitized_metadata.get("incident_id", "Unknown"),
                action_taken=sanitized_action,
                outcome=outcome,
                created_at=dt.datetime.now(dt.timezone.utc)
            )
            session.add(memory)
            session.commit()
            logger.info(f"Stored memory for {inc_type}")
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to store memory: {e}")
        finally:
            session.close()

    # ========== AGENT HEALTH MONITORING ==========

    def update_agent_health(
        self,
        agent_name: str,
        status: str,
        latency_ms: Optional[float] = None,
        cpu_percent: Optional[float] = None,
        memory_mb: Optional[float] = None,
        events_processed: Optional[int] = None
    ):
        """Update agent health metrics"""
        session = self.get_session()
        try:
            # Sanitize numeric values
            if latency_ms and (math.isinf(latency_ms) or math.isnan(latency_ms)):
                latency_ms = None
            if cpu_percent and (math.isinf(cpu_percent) or math.isnan(cpu_percent)):
                cpu_percent = None
            if memory_mb and (math.isinf(memory_mb) or math.isnan(memory_mb)):
                memory_mb = None
            
            health = AgentHealth(
                agent_name=agent_name,
                status=status,
                last_heartbeat=dt.datetime.now(dt.timezone.utc),
                latency_ms=latency_ms,
                cpu_percent=cpu_percent,
                memory_mb=memory_mb,
                events_processed=events_processed
            )
            session.add(health)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to update agent health: {e}")
        finally:
            session.close()

    def get_agent_health(self, agent_name: str) -> Optional[AgentHealth]:
        """Get latest health status for an agent"""
        session = self.get_session()
        try:
            health = session.query(AgentHealth)\
                .filter_by(agent_name=agent_name)\
                .order_by(AgentHealth.last_heartbeat.desc())\
                .first()
            return health
        except Exception as e:
            logger.error(f"Failed to get agent health: {e}")
            return None
        finally:
            session.close()

    # ========== PERFORMANCE METRICS ==========

    def record_performance_metric(
        self,
        trace_id: str,
        end_to_end_latency_ms: float,
        accuracy: Optional[float] = None,
        prediction_confidence: Optional[float] = None
    ):
        """Record performance metrics for tracing"""
        session = self.get_session()
        try:
            # Sanitize numeric values
            if math.isinf(end_to_end_latency_ms) or math.isnan(end_to_end_latency_ms):
                end_to_end_latency_ms = 0.0
            if accuracy and (math.isinf(accuracy) or math.isnan(accuracy)):
                accuracy = None
            if prediction_confidence and (math.isinf(prediction_confidence) or math.isnan(prediction_confidence)):
                prediction_confidence = None
            
            metric = PerformanceMetric(
                trace_id=trace_id,
                end_to_end_latency_ms=end_to_end_latency_ms,
                accuracy=accuracy,
                prediction_confidence=prediction_confidence,
                created_at=dt.datetime.now(dt.timezone.utc)
            )
            session.add(metric)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to record performance metric: {e}")
        finally:
            session.close()
    
    def get_recent_performance_metrics(self, limit: int = 100) -> List[PerformanceMetric]:
        """Get recent performance metrics"""
        session = self.get_session()
        try:
            metrics = session.query(PerformanceMetric)\
                .order_by(PerformanceMetric.created_at.desc())\
                .limit(limit)\
                .all()
            return metrics
        except Exception as e:
            logger.error(f"Failed to get performance metrics: {e}")
            return []
        finally:
            session.close()

    # ========== DRIFT METRICS ==========

    def record_drift_metric(
        self,
        metric_name: str,
        drift_score: float,
        reference_mean: float,
        current_mean: float,
        threshold: float
    ):
        """Record data drift metrics"""
        session = self.get_session()
        try:
            # Sanitize all float values
            if math.isinf(drift_score) or math.isnan(drift_score):
                drift_score = 0.0
            if math.isinf(reference_mean) or math.isnan(reference_mean):
                reference_mean = 0.0
            if math.isinf(current_mean) or math.isnan(current_mean):
                current_mean = 0.0
            if math.isinf(threshold) or math.isnan(threshold):
                threshold = 0.0
            
            metric = DriftMetric(
                metric_name=metric_name,
                drift_score=drift_score,
                reference_mean=reference_mean,
                current_mean=current_mean,
                threshold=threshold,
                created_at=dt.datetime.now(dt.timezone.utc)
            )
            session.add(metric)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to record drift metric: {e}")
        finally:
            session.close()

    # ========== QUERY HELPERS ==========

    def get_recent_incidents(self, limit: int = 10, status: Optional[IncidentStatus] = None) -> List[Incident]:
        """Get recent incidents, optionally filtered by status"""
        session = self.get_session()
        try:
            query = session.query(Incident).order_by(Incident.detected_at.desc())
            if status:
                query = query.filter_by(status=status)
            incidents = query.limit(limit).all()
            return incidents
        except Exception as e:
            logger.error(f"Failed to get recent incidents: {e}")
            return []
        finally:
            session.close()

    def get_incident_by_id(self, incident_id: str) -> Optional[Incident]:
        """Get incident by ID"""
        session = self.get_session()
        try:
            incident = session.query(Incident).filter_by(incident_id=incident_id).first()
            return incident
        except Exception as e:
            logger.error(f"Failed to get incident: {e}")
            return None
        finally:
            session.close()

    def get_healing_actions_for_incident(self, incident_id: str) -> List[HealingAction]:
        """Get all healing actions for an incident"""
        session = self.get_session()
        try:
            actions = session.query(HealingAction)\
                .filter_by(incident_id=incident_id)\
                .order_by(HealingAction.executed_at.desc())\
                .all()
            return actions
        except Exception as e:
            logger.error(f"Failed to get healing actions: {e}")
            return []
        finally:
            session.close()
    
    # ========== POLICY & CONFIG (used by HealingAgent) ==========

    def store_policy_request(
        self,
        request_id: str,
        incident_id: str,
        incident_type: Any,
        proposed_action: Dict[str, Any],
        timestamp: str
    ):
        """Log a policy request as a healing action with PENDING decision."""
        session = self.get_session()
        try:
            inc_type = self._to_enum(incident_type, IncidentType)

            # Ensure the incident exists; create one if not
            existing = session.query(Incident).filter_by(incident_id=incident_id).first()
            if not existing:
                incident = Incident(
                    incident_id=incident_id,
                    type=inc_type,
                    detected_at=dt.datetime.now(dt.timezone.utc),
                    status=IncidentStatus.OPEN,
                    description=f"Auto-created from policy request {request_id}"
                )
                session.add(incident)
                session.flush()

            action = HealingAction(
                action_id=request_id,                          # reuse REQ-* as action_id
                incident_id=incident_id,
                proposed_action=sanitize_json(proposed_action),
                agl_decision=AGLDecision.PENDING,
                created_at=dt.datetime.now(dt.timezone.utc)
            )
            session.add(action)
            session.commit()
            logger.info(f"Stored policy request {request_id} for incident {incident_id}")
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to store policy request: {e}")
        finally:
            session.close()

    def store_config_update(
        self,
        update_id: str,
        timestamp: str,
        changed_by: str,
        changes: Dict[str, Any],
        reason: str,
        incident_id: Optional[str] = None
    ):
        """Persist a config change to ConfigHistory."""
        session = self.get_session()
        try:
            record = ConfigHistory(
                config_id=update_id,
                changed_by=changed_by,
                changes=sanitize_json(changes),
                reason=reason,
                incident_id=incident_id,
                created_at=dt.datetime.now(dt.timezone.utc)
            )
            session.add(record)
            session.commit()
            logger.info(f"Stored config update {update_id} by {changed_by}")
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to store config update: {e}")
        finally:
            session.close()
    """
Add these methods to your DatabaseManager class in backend/database/db_manager.py
"""

    def log_healing_action(self, incident_id: int, action_type: str, target: str, 
                        status: str, details: dict = None):
        """
        Log a healing action execution to the database
        
        Args:
            incident_id: ID of the incident being healed
            action_type: Type of action (RESTART_AGENT, ROLLBACK_MODEL, etc.)
            target: Target of the action (agent name, model ID, etc.)
            status: Execution status (SUCCESS, FAILED, DENIED)
            details: Additional details about the action
        """
        query = """
            INSERT INTO healing_actions 
            (incident_id, action_type, target, status, details, executed_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            RETURNING id
        """
        
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, (
                        incident_id,
                        action_type,
                        target,
                        status,
                        json.dumps(details) if details else None
                    ))
                    action_id = cursor.fetchone()[0]
                    conn.commit()
                    
                    logger.info(f"Logged healing action {action_id}: {action_type} for incident {incident_id}")
                    return action_id
                    
        except Exception as e:
            logger.error(f"Error logging healing action: {e}")
            raise


    def get_healing_actions(self, incident_id: int = None, limit: int = 100):
        """
        Retrieve healing actions, optionally filtered by incident
        
        Args:
            incident_id: Optional incident ID to filter by
            limit: Maximum number of records to return
        
        Returns:
            List of healing action records
        """
        if incident_id:
            query = """
                SELECT id, incident_id, action_type, target, status, details, executed_at
                FROM healing_actions
                WHERE incident_id = %s
                ORDER BY executed_at DESC
                LIMIT %s
            """
            params = (incident_id, limit)
        else:
            query = """
                SELECT id, incident_id, action_type, target, status, details, executed_at
                FROM healing_actions
                ORDER BY executed_at DESC
                LIMIT %s
            """
            params = (limit,)
        
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, params)
                    rows = cursor.fetchall()
                    
                    actions = []
                    for row in rows:
                        actions.append({
                            'id': row[0],
                            'incident_id': row[1],
                            'action_type': row[2],
                            'target': row[3],
                            'status': row[4],
                            'details': json.loads(row[5]) if row[5] else None,
                            'executed_at': row[6].isoformat() if row[6] else None
                        })
                    
                    return actions
                    
        except Exception as e:
            logger.error(f"Error retrieving healing actions: {e}")
            return []


    def update_incident(self, incident_id: int, status: IncidentStatus = None, 
                    resolution_action: str = None, resolved_at = None):
        """
        Update an incident's status and resolution details
        
        Args:
            incident_id: ID of the incident to update
            status: New status (optional)
            resolution_action: Action taken to resolve (optional)
            resolved_at: Timestamp of resolution (optional)
        """
        updates = []
        params = []
        
        if status:
            updates.append("status = %s")
            params.append(status.value if isinstance(status, IncidentStatus) else status)
        
        if resolution_action:
            updates.append("resolution_action = %s")
            params.append(resolution_action)
        
        if resolved_at:
            updates.append("resolved_at = %s")
            params.append(resolved_at)
        
        if not updates:
            logger.warning("No updates provided for incident")
            return
        
        params.append(incident_id)
        query = f"""
            UPDATE incidents
            SET {', '.join(updates)}, updated_at = NOW()
            WHERE id = %s
        """
        
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, tuple(params))
                    conn.commit()
                    
                    logger.info(f"Updated incident {incident_id}: {', '.join(updates)}")
                    
        except Exception as e:
            logger.error(f"Error updating incident: {e}")
            raise

