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
    RESTART_AGENT = "RESTART_AGENT"

class IncidentStatus(str, Enum):
    OPEN = "OPEN"
    MITIGATING = "MITIGATING"
    RESOLVED = "RESOLVED"
    FAILED = "FAILED"

class AGLDecision(str, Enum):
    PENDING = "PENDING"
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

from typing import Optional
@dataclass
class Alert:
    alert_id: str
    alert_type: IncidentType
    severity: str
    timestamp: str
    metrics_snapshot: Dict[str, Any]
    description: str
    incident_id: Optional[str] = None

    def to_json(self) -> str:
        data = asdict(self)
        data['alert_type'] = self.alert_type.value
        # Only include incident_id if not None
        if data.get('incident_id') is None:
            data.pop('incident_id', None)
        return json.dumps(data)

    @classmethod
    def from_json(cls, json_str: str) -> 'Alert':
        data = json.loads(json_str)
        data['alert_type'] = IncidentType(data['alert_type'])
        return cls(**data)

"""
Additional schema classes for HealingAgent workflow
Add these to your existing common/schemas.py file
"""

from enum import Enum
from dataclasses import dataclass
import json


class ActionType(Enum):
    """Types of healing actions"""
    RESTART_AGENT = "RESTART_AGENT"
    ROLLBACK_MODEL = "ROLLBACK_MODEL"
    ENABLE_SAFE_MODE = "ENABLE_SAFE_MODE"
    TRIGGER_RETRAINING = "TRIGGER_RETRAINING"


@dataclass
class HealingAction:
    """Represents a proposed healing action"""
    action_type: ActionType
    target: str
    parameters: dict
    timestamp: str
    
    def to_dict(self):
        return {
            "action_type": self.action_type.value if isinstance(self.action_type, ActionType) else self.action_type,
            "target": self.target,
            "parameters": self.parameters,
            "timestamp": self.timestamp
        }
    
    def to_json(self):
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_dict(cls, data):
        return cls(
            action_type=ActionType(data["action_type"]) if isinstance(data["action_type"], str) else data["action_type"],
            target=data["target"],
            parameters=data["parameters"],
            timestamp=data["timestamp"]
        )
    
    @classmethod
    def from_json(cls, json_str):
        return cls.from_dict(json.loads(json_str))


@dataclass
class PolicyRequest:
    """Request sent from HealingAgent to AGL for approval"""
    request_id: str
    incident_id: int
    proposed_action: dict  # HealingAction as dict
    timestamp: str
    
    def to_dict(self):
        return {
            "request_id": self.request_id,
            "incident_id": self.incident_id,
            "proposed_action": self.proposed_action,
            "timestamp": self.timestamp
        }
    
    def to_json(self):
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_dict(cls, data):
        return cls(
            request_id=data["request_id"],
            incident_id=data["incident_id"],
            proposed_action=data["proposed_action"],
            timestamp=data["timestamp"]
        )
    
    @classmethod
    def from_json(cls, json_str):
        return cls.from_dict(json.loads(json_str))


class AGLDecision(Enum):
    """AGL decision outcomes"""
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    ESCALATE = "ESCALATE"


@dataclass
class PolicyDecision:
    """Decision sent from AGL back to HealingAgent"""
    request_id: str
    incident_id: int
    decision: AGLDecision
    approved_action: dict | None  # HealingAction as dict if approved
    timestamp: str
    reasoning: str
    
    def to_dict(self):
        return {
            "request_id": self.request_id,
            "incident_id": self.incident_id,
            "decision": self.decision.value if isinstance(self.decision, AGLDecision) else self.decision,
            "approved_action": self.approved_action,
            "timestamp": self.timestamp,
            "reasoning": self.reasoning
        }
    
    def to_json(self):
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_dict(cls, data):
        return cls(
            request_id=data["request_id"],
            incident_id=data["incident_id"],
            decision=AGLDecision(data["decision"]) if isinstance(data["decision"], str) else data["decision"],
            approved_action=data.get("approved_action"),
            timestamp=data["timestamp"],
            reasoning=data.get("reasoning", "")
        )
    
    @classmethod
    def from_json(cls, json_str):
        return cls.from_dict(json.loads(json_str))

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
