from typing import Optional, Dict, Any, List
from datetime import datetime
from dataclasses import dataclass, asdict
from enum import Enum
import json

class IncidentType(str, Enum):
    DATA_DRIFT = "DATA_DRIFT"
    PERF_DROP = "PERF_DROP"
    LATENCY_SLO_BREACH = "LATENCY_SLO_BREACH"
    AGENT_DOWN = "AGENT_DOWN"
    FN_SPIKE = "FN_SPIKE"

class IncidentStatus(str, Enum):
    OPEN = "OPEN"
    MITIGATING = "MITIGATING"
    RESOLVED = "RESOLVED"
    FAILED = "FAILED"

class AGLDecision(str, Enum):
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    MODIFIED = "MODIFIED"

class ActionResult(str, Enum):
    SUCCESS = "SUCCESS"
    FAIL = "FAIL"

@dataclass
class RawEvent:
    event_id: str
    trace_id: str
    timestamp: str
    event_type: str
    data: Dict[str, Any]
    
    def validate(self):
        if not isinstance(self.event_id, str): raise ValueError("event_id must be string")
        if not isinstance(self.trace_id, str): raise ValueError("trace_id must be string")
        if not isinstance(self.event_type, str): raise ValueError("event_type must be string")
        if not isinstance(self.data, dict): raise ValueError("data must be dict")
        # Ensure 'value' exists and is numeric if it's a data event
        if "value" in self.data and not isinstance(self.data["value"], (int, float)):
            try:
                self.data["value"] = float(self.data["value"])
            except (ValueError, TypeError):
                raise ValueError(f"Invalid value in data: {self.data['value']}")

    def to_json(self) -> str:
        return json.dumps(asdict(self))
    
    @classmethod
    def from_json(cls, json_str: str) -> 'RawEvent':
        data = json.loads(json_str)
        instance = cls(**data)
        instance.validate()
        return instance

@dataclass
class FeatureVector:
    trace_id: str
    timestamp: str
    features: Dict[str, float]
    metadata: Optional[Dict[str, Any]] = None
    
    def to_json(self) -> str:
        return json.dumps(asdict(self))
    
    @classmethod
    def from_json(cls, json_str: str) -> 'FeatureVector':
        return cls(**json.loads(json_str))

@dataclass
class Prediction:
    trace_id: str
    timestamp: str
    model_version: str
    prediction: Any
    confidence: float
    latency_ms: float
    metadata: Optional[Dict[str, Any]] = None
    
    def to_json(self) -> str:
        return json.dumps(asdict(self))
    
    @classmethod
    def from_json(cls, json_str: str) -> 'Prediction':
        return cls(**json.loads(json_str))

@dataclass
class Decision:
    trace_id: str
    timestamp: str
    decision: str
    reasoning: Optional[str] = None
    confidence: float = 0.0
    metadata: Optional[Dict[str, Any]] = None
    
    def to_json(self) -> str:
        return json.dumps(asdict(self))
    
    @classmethod
    def from_json(cls, json_str: str) -> 'Decision':
        return cls(**json.loads(json_str))

@dataclass
class AgentMetric:
    agent: str
    status: str
    latency_ms: float
    timestamp: str
    cpu_percent: Optional[float] = None
    memory_mb: Optional[float] = None
    events_processed: Optional[int] = None
    
    def to_json(self) -> str:
        return json.dumps(asdict(self))
    
    @classmethod
    def from_json(cls, json_str: str) -> 'AgentMetric':
        return cls(**json.loads(json_str))

@dataclass
class Feedback:
    trace_id: str
    timestamp: str
    actual_outcome: bool
    predicted_outcome: bool
    metadata: Optional[Dict[str, Any]] = None
    
    def to_json(self) -> str:
        return json.dumps(asdict(self))
    
    @classmethod
    def from_json(cls, json_str: str) -> 'Feedback':
        return cls(**json.loads(json_str))

@dataclass
class Alert:
    alert_id: str
    alert_type: IncidentType
    severity: str
    timestamp: str
    metrics_snapshot: Dict[str, Any]
    description: str
    
    def to_json(self) -> str:
        data = asdict(self)
        data['alert_type'] = self.alert_type.value
        return json.dumps(data)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'Alert':
        data = json.loads(json_str)
        data['alert_type'] = IncidentType(data['alert_type'])
        return cls(**data)

@dataclass
class PolicyRequest:
    request_id: str
    incident_id: str
    incident_type: IncidentType
    proposed_action: Dict[str, Any]
    timestamp: str
    context: Optional[Dict[str, Any]] = None
    
    def to_json(self) -> str:
        data = asdict(self)
        data['incident_type'] = self.incident_type.value
        return json.dumps(data)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'PolicyRequest':
        data = json.loads(json_str)
        data['incident_type'] = IncidentType(data['incident_type'])
        return cls(**data)

@dataclass
class PolicyDecision:
    request_id: str
    incident_id: str
    decision: AGLDecision
    approved_action: Dict[str, Any]
    timestamp: str
    reasoning: Optional[str] = None
    
    def to_json(self) -> str:
        data = asdict(self)
        data['decision'] = self.decision.value
        return json.dumps(data)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'PolicyDecision':
        data = json.loads(json_str)
        data['decision'] = AGLDecision(data['decision'])
        return cls(**data)

@dataclass
class ConfigUpdate:
    update_id: str
    timestamp: str
    changed_by: str
    changes: Dict[str, Any]
    reason: str
    
    def to_json(self) -> str:
        return json.dumps(asdict(self))
    
    @classmethod
    def from_json(cls, json_str: str) -> 'ConfigUpdate':
        return cls(**json.loads(json_str))

@dataclass
class IncidentLog:
    incident_id: str
    incident_type: IncidentType
    status: IncidentStatus
    detected_at: str
    resolved_at: Optional[str] = None
    mttr_seconds: Optional[float] = None
    actions_taken: Optional[List[str]] = None
    metrics_snapshot: Optional[Dict[str, Any]] = None
    
    def to_json(self) -> str:
        data = asdict(self)
        data['incident_type'] = self.incident_type.value
        data['status'] = self.status.value
        return json.dumps(data)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'IncidentLog':
        data = json.loads(json_str)
        data['incident_type'] = IncidentType(data['incident_type'])
        data['status'] = IncidentStatus(data['status'])
        return cls(**data)
