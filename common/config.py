import os
from dataclasses import dataclass
from typing import Optional

@dataclass
class KafkaConfig:
    bootstrap_servers: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "127.0.0.1:29092")
    auto_offset_reset: str = "earliest"
    enable_auto_commit: bool = True
    group_id_prefix: str = "agentic-platform-v3"

@dataclass
class DatabaseConfig:
    host: str = os.getenv("DB_HOST", "localhost")
    port: int = int(os.getenv("DB_PORT", "5433"))
    user: str = os.getenv("DB_USER", "agentic_user")
    password: str = os.getenv("DB_PASSWORD", "agentic_pass")
    database: str = os.getenv("DB_NAME", "agentic_db")
    
    @property
    def connection_string(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"

@dataclass
class MLflowConfig:
    tracking_uri: str = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5020")
    experiment_name: str = "agentic-ai-models"
    model_registry_name: str = "production-model"

@dataclass
class MonitoringConfig:
    latency_slo_ms: int = 300
    latency_window_size: int = 100
    heartbeat_timeout_seconds: int = 30
    drift_threshold: float = 0.2
    performance_threshold: float = 0.75
    feedback_window_size: int = 200
    alert_cooldown_seconds: int = 60

@dataclass
class HealingConfig:
    verification_window_seconds: int = 20
    verification_event_count: int = 200
    max_retries: int = 3
    safe_mode_enabled: bool = False
    
    playbooks: dict = None
    
    def __post_init__(self):
        if self.playbooks is None:
            self.playbooks = {
                "DATA_DRIFT": {
                    "actions": ["reduce_threshold", "trigger_retraining"],
                    "priority": "high"
                },
                "PERF_DROP": {
                    "actions": ["rollback_model"],
                    "priority": "critical"
                },
                "LATENCY_SLO_BREACH": {
                    "actions": ["enable_safe_mode", "switch_to_light_model"],
                    "priority": "high"
                },
                "AGENT_DOWN": {
                    "actions": ["restart_agent", "route_around"],
                    "priority": "critical"
                }
            }

@dataclass
class AgentConfig:
    name: str
    kafka: KafkaConfig
    database: DatabaseConfig
    mlflow: MLflowConfig
    monitoring: MonitoringConfig
    healing: HealingConfig
    metrics_port: int
    heartbeat_interval_seconds: int = 5

class Config:
    def __init__(self):
        self.kafka = KafkaConfig()
        self.database = DatabaseConfig()
        self.mlflow = MLflowConfig()
        self.monitoring = MonitoringConfig()
        self.healing = HealingConfig()
    
    def get_agent_config(self, agent_name: str, metrics_port: int) -> AgentConfig:
        return AgentConfig(
            name=agent_name,
            kafka=self.kafka,
            database=self.database,
            mlflow=self.mlflow,
            monitoring=self.monitoring,
            healing=self.healing,
            metrics_port=metrics_port
        )

config = Config()
