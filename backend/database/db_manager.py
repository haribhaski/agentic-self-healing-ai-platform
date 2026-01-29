from sqlalchemy.orm import Session
from backend.database.models import (
    Incident, HealingAction, ConfigHistory, MemoryChunk,
    AgentHealth, PerformanceMetric, DriftMetric, init_db, get_session, Base
)
from common.schemas import IncidentType, IncidentStatus, AGLDecision, ActionResult
from datetime import datetime, timedelta
import datetime as dt
from typing import Optional, List, Dict, Any, Union
import logging
import uuid

logger = logging.getLogger(__name__)

class DatabaseManager:
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
    
    def _to_enum(self, value: Any, enum_class: Any) -> Any:
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
            # Handle cases where incident_id might be passed as first positional arg by mistake
            # or if it's passed in kwargs or args
            actual_incident_id = incident_id or kwargs.get('incident_id')
            if not actual_incident_id and args:
                # If we have positional args beyond self, maybe the first one is incident_id?
                # But our signature has incident_type as the first. 
                # This is just extreme safety.
                pass
                
            actual_incident_type = incident_type
            actual_metrics = metrics_snapshot
            actual_desc = description

            # If incident_type looks like an ID and incident_id is None, swap them
            if isinstance(incident_type, str) and incident_type.startswith("INC-") and actual_incident_id is None:
                actual_incident_id = incident_type

            target_type = self._to_enum(actual_incident_type, IncidentType)

            if not actual_incident_id:
                actual_incident_id = f"INC-{uuid.uuid4().hex[:8].upper()}"
                
            incident = Incident(
                incident_id=actual_incident_id,
                type=target_type,
                detected_at=dt.datetime.now(dt.timezone.utc),
                status=IncidentStatus.OPEN,
                metrics_snapshot=actual_metrics or {},
                description=actual_desc
            )
            session.add(incident)
            session.commit()
            logger.info(f"Created incident {actual_incident_id} of type {target_type}")
            return incident
        except Exception as e:
            if session: session.rollback()
            logger.error(f"Failed to create incident: {e}")
            raise
        finally:
            if session: session.close()

    def get_open_incident_by_type(self, incident_type: Any) -> Optional[str]:
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

            action = HealingAction(
                action_id=f"ACT-{uuid.uuid4().hex[:8].upper()}",
                incident_id=actual_incident_id,
                proposed_action={"type": action_type, "details": action_details or {}},
                agl_decision=decision_enum,
                approved_action={"type": action_type, "details": action_details} if decision_enum == AGLDecision.APPROVED else None,
                executed_at=dt.datetime.now(dt.timezone.utc) if decision_enum == AGLDecision.APPROVED else None,
                result=ActionResult.SUCCESS if decision_enum == AGLDecision.APPROVED else None,
                reasoning=f"Decision {decision_enum.value if hasattr(decision_enum, 'value') else decision_enum} by AGL"
            )
            session.add(action)
            session.commit()
            logger.info(f"Logged healing action for incident {actual_incident_id}: {decision_enum}")
        except Exception as e:
            if session: session.rollback()
            logger.error(f"Failed to log healing action: {e}")
        finally:
            if session: session.close()

    def store_memory(
        self,
        incident_type: Any,
        action_taken: Dict[str, Any],
        outcome: str,
        metadata: Dict[str, Any]
    ):
        session = self.get_session()
        try:
            inc_type = self._to_enum(incident_type, IncidentType)
            if not isinstance(inc_type, IncidentType):
                # Intelligent mapping fallback
                val = str(incident_type).upper()
                if "LATENCY" in val: inc_type = IncidentType.LATENCY_SLO_BREACH
                elif "DRIFT" in val: inc_type = IncidentType.DATA_DRIFT
                elif "PERF" in val or "ACCURACY" in val: inc_type = IncidentType.PERF_DROP
                elif "DOWN" in val or "RESTART" in val: inc_type = IncidentType.AGENT_DOWN
                else: inc_type = IncidentType.LATENCY_SLO_BREACH
                
            memory = MemoryChunk(
                memory_id=f"MEM-{uuid.uuid4().hex[:8].upper()}",
                incident_type=inc_type,
                incident_summary=metadata.get("incident_id", "Unknown"),
                action_taken=action_taken,
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
    
    def update_incident_status(
        self,
        incident_id: str,
        status: Any,
        resolved_at: Optional[datetime] = None,
        mttr_seconds: Optional[float] = None
    ):
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
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to update incident status: {e}")
            raise
        finally:
            session.close()

    def update_agent_health(
        self,
        agent_name: str,
        status: str,
        latency_ms: Optional[float] = None,
        cpu_percent: Optional[float] = None,
        memory_mb: Optional[float] = None,
        events_processed: Optional[int] = None
    ):
        session = self.get_session()
        try:
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

    def record_performance_metric(
        self,
        trace_id: str,
        end_to_end_latency_ms: float,
        accuracy: Optional[float] = None,
        prediction_confidence: Optional[float] = None
    ):
        session = self.get_session()
        try:
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
