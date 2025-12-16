from sqlalchemy.orm import Session
from backend.database.models import (
    Incident, HealingAction, ConfigHistory, MemoryChunk,
    AgentHealth, PerformanceMetric, DriftMetric, init_db, get_session
)
from common.schemas import IncidentType, IncidentStatus, AGLDecision, ActionResult
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, connection_string: str):
        self.engine = init_db(connection_string)
        logger.info("Database initialized successfully")
    
    def get_session(self) -> Session:
        return get_session(self.engine)
    
    def create_incident(
        self,
        incident_id: str,
        incident_type: IncidentType,
        metrics_snapshot: Dict[str, Any],
        description: str
    ) -> Incident:
        session = self.get_session()
        try:
            incident = Incident(
                incident_id=incident_id,
                type=incident_type,
                detected_at=datetime.utcnow(),
                status=IncidentStatus.OPEN,
                metrics_snapshot=metrics_snapshot,
                description=description
            )
            session.add(incident)
            session.commit()
            logger.info(f"Created incident {incident_id} of type {incident_type}")
            return incident
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to create incident: {e}")
            raise
        finally:
            session.close()
    
    def update_incident_status(
        self,
        incident_id: str,
        status: IncidentStatus,
        resolved_at: Optional[datetime] = None,
        mttr_seconds: Optional[float] = None
    ):
        session = self.get_session()
        try:
            incident = session.query(Incident).filter_by(incident_id=incident_id).first()
            if incident:
                incident.status = status
                if resolved_at:
                    incident.resolved_at = resolved_at
                if mttr_seconds:
                    incident.mttr_seconds = mttr_seconds
                session.commit()
                logger.info(f"Updated incident {incident_id} status to {status}")
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to update incident status: {e}")
            raise
        finally:
            session.close()
    
    def create_healing_action(
        self,
        action_id: str,
        incident_id: str,
        proposed_action: Dict[str, Any],
        agl_decision: AGLDecision,
        approved_action: Dict[str, Any],
        reasoning: Optional[str] = None
    ) -> HealingAction:
        session = self.get_session()
        try:
            action = HealingAction(
                action_id=action_id,
                incident_id=incident_id,
                proposed_action=proposed_action,
                agl_decision=agl_decision,
                approved_action=approved_action,
                reasoning=reasoning
            )
            session.add(action)
            session.commit()
            logger.info(f"Created healing action {action_id} for incident {incident_id}")
            return action
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to create healing action: {e}")
            raise
        finally:
            session.close()
    
    def update_action_result(
        self,
        action_id: str,
        result: ActionResult,
        executed_at: datetime
    ):
        session = self.get_session()
        try:
            action = session.query(HealingAction).filter_by(action_id=action_id).first()
            if action:
                action.result = result
                action.executed_at = executed_at
                session.commit()
                logger.info(f"Updated action {action_id} result to {result}")
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to update action result: {e}")
            raise
        finally:
            session.close()
    
    def create_config_history(
        self,
        config_id: str,
        changed_by: str,
        changes: Dict[str, Any],
        reason: str,
        incident_id: Optional[str] = None
    ):
        session = self.get_session()
        try:
            config = ConfigHistory(
                config_id=config_id,
                changed_by=changed_by,
                changes=changes,
                reason=reason,
                incident_id=incident_id
            )
            session.add(config)
            session.commit()
            logger.info(f"Created config history {config_id}")
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to create config history: {e}")
            raise
        finally:
            session.close()
    
    def create_memory_chunk(
        self,
        memory_id: str,
        incident_type: IncidentType,
        incident_summary: str,
        action_taken: Dict[str, Any],
        outcome: str,
        metrics_before: Optional[Dict[str, Any]] = None,
        metrics_after: Optional[Dict[str, Any]] = None,
        mttr_seconds: Optional[float] = None
    ):
        session = self.get_session()
        try:
            memory = MemoryChunk(
                memory_id=memory_id,
                incident_type=incident_type,
                incident_summary=incident_summary,
                action_taken=action_taken,
                outcome=outcome,
                metrics_before=metrics_before,
                metrics_after=metrics_after,
                mttr_seconds=mttr_seconds
            )
            session.add(memory)
            session.commit()
            logger.info(f"Created memory chunk {memory_id}")
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to create memory chunk: {e}")
            raise
        finally:
            session.close()
    
    def get_similar_incidents(self, incident_type: IncidentType, limit: int = 5) -> List[MemoryChunk]:
        session = self.get_session()
        try:
            memories = session.query(MemoryChunk)\
                .filter_by(incident_type=incident_type)\
                .order_by(MemoryChunk.created_at.desc())\
                .limit(limit)\
                .all()
            return memories
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
                last_heartbeat=datetime.utcnow(),
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
    
    def get_recent_agent_health(self, agent_name: str, minutes: int = 5) -> List[AgentHealth]:
        session = self.get_session()
        try:
            threshold = datetime.utcnow() - timedelta(minutes=minutes)
            health_records = session.query(AgentHealth)\
                .filter(
                    AgentHealth.agent_name == agent_name,
                    AgentHealth.created_at >= threshold
                )\
                .order_by(AgentHealth.created_at.desc())\
                .all()
            return health_records
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
                prediction_confidence=prediction_confidence
            )
            session.add(metric)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to record performance metric: {e}")
        finally:
            session.close()
    
    def get_average_mttr(self, incident_type: Optional[IncidentType] = None) -> float:
        session = self.get_session()
        try:
            query = session.query(Incident).filter(Incident.mttr_seconds.isnot(None))
            if incident_type:
                query = query.filter(Incident.type == incident_type)
            incidents = query.all()
            if not incidents:
                return 0.0
            return sum(i.mttr_seconds for i in incidents) / len(incidents)
        finally:
            session.close()
