from sqlalchemy import create_engine, Column, String, Integer, Float, DateTime, JSON, Enum as SQLEnum, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from common.schemas import IncidentType, IncidentStatus, AGLDecision, ActionResult
import enum

Base = declarative_base()

class RawEventRecord(Base):
    __tablename__ = 'raw_events'
    id = Column(Integer, primary_key=True, autoincrement=True)
    trace_id = Column(String(255), nullable=False)
    timestamp = Column(DateTime, nullable=False)
    source_file = Column(String(255), nullable=True)
    data = Column(JSON, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

class PredictionRecord(Base):
    __tablename__ = 'predictions'
    id = Column(Integer, primary_key=True, autoincrement=True)
    trace_id = Column(String(255), nullable=False)
    timestamp = Column(DateTime, nullable=False)
    model_version = Column(String(50), nullable=True)
    prediction = Column(String(50), nullable=False)
    confidence = Column(Float, nullable=True)
    latency_ms = Column(Float, nullable=True)
    features = Column(JSON, nullable=True)
    source_file = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

# FIXED DecisionRecord - 'metadata' is reserved in SQLAlchemy
# Use 'meta_data' or 'extra_data' instead

class DecisionRecord(Base):
    """Decision records from DecisionAgent"""
    __tablename__ = 'decisions'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    trace_id = Column(String(255), nullable=False)
    timestamp = Column(DateTime, nullable=False)
    decision = Column(String(50), nullable=False)
    reasoning = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True)
    extra_data = Column(JSON, nullable=True)  # ← Changed from 'metadata' to 'extra_data'
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
class Incident(Base):
    __tablename__ = 'incidents'
    
    incident_id = Column(String(255), primary_key=True)
    type = Column(SQLEnum(IncidentType), nullable=False)
    detected_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)
    status = Column(SQLEnum(IncidentStatus), nullable=False, default=IncidentStatus.OPEN)
    metrics_snapshot = Column(JSON, nullable=True)
    description = Column(Text, nullable=True)
    mttr_seconds = Column(Float, nullable=True)

class HealingAction(Base):
    __tablename__ = 'healing_actions'
    
    action_id = Column(String(255), primary_key=True)
    incident_id = Column(String(255), nullable=False)
    proposed_action = Column(JSON, nullable=False)
    agl_decision = Column(SQLEnum(AGLDecision), nullable=False)
    approved_action = Column(JSON, nullable=True)
    executed_at = Column(DateTime, nullable=True)
    result = Column(SQLEnum(ActionResult), nullable=True)
    reasoning = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

class ConfigHistory(Base):
    __tablename__ = 'config_history'
    
    config_id = Column(String(255), primary_key=True)
    changed_by = Column(String(100), nullable=False)
    changes = Column(JSON, nullable=False)
    reason = Column(Text, nullable=False)
    incident_id = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

class MemoryChunk(Base):
    __tablename__ = 'memory_chunks'
    
    memory_id = Column(String(255), primary_key=True)
    incident_type = Column(SQLEnum(IncidentType), nullable=False)
    incident_summary = Column(Text, nullable=False)
    action_taken = Column(JSON, nullable=False)
    outcome = Column(String(100), nullable=False)
    metrics_before = Column(JSON, nullable=True)
    metrics_after = Column(JSON, nullable=True)
    mttr_seconds = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

class AgentHealth(Base):
    __tablename__ = 'agent_health'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_name = Column(String(100), nullable=False)
    status = Column(String(50), nullable=False)
    last_heartbeat = Column(DateTime, nullable=False)
    latency_ms = Column(Float, nullable=True)
    cpu_percent = Column(Float, nullable=True)
    memory_mb = Column(Float, nullable=True)
    events_processed = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

class PerformanceMetric(Base):
    __tablename__ = 'performance_metrics'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    trace_id = Column(String(255), nullable=False)
    end_to_end_latency_ms = Column(Float, nullable=False)
    accuracy = Column(Float, nullable=True)
    prediction_confidence = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

class DriftMetric(Base):
    __tablename__ = 'drift_metrics'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    feature_name = Column(String(255), nullable=False)
    drift_score = Column(Float, nullable=False)
    distribution_snapshot = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

def init_db(connection_string: str):
    import time
    from sqlalchemy.exc import OperationalError
    
    # Retry logic for database connection
    max_retries = 10
    retry_delay = 1
    
    for i in range(max_retries):
        try:
            engine = create_engine(connection_string, pool_pre_ping=True)
            # Test connection
            with engine.connect() as conn:
                pass
            Base.metadata.create_all(engine)
            return engine
        except OperationalError as e:
            if i == max_retries - 1:
                raise
            print(f"Database connection failed, retrying in {retry_delay}s... ({i+1}/{max_retries})")
            time.sleep(retry_delay)
            retry_delay *= 2 # Exponential backoff
    
    return create_engine(connection_string)

def get_session(engine):
    Session = sessionmaker(bind=engine)
    return Session()