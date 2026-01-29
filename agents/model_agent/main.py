import asyncio
import json
import logging
import time
import signal
from datetime import datetime
from kafka.errors import KafkaError
import mlflow
import mlflow.sklearn
import numpy as np
import sys
import os
import uuid
import psutil

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(ROOT_DIR)

from dataclasses import asdict
from common.config import config
from common.schemas import FeatureVector, Prediction, AgentMetric
from common.logger import setup_logger
from common.kafka_utils import create_producer, create_consumer
from backend.database.db_manager import DatabaseManager

logger = setup_logger("ModelAgent", config.kafka)

class ModelAgent:
    def __init__(self):
        self.config = config.get_agent_config("ModelAgent", 8003)
        self.producer = create_producer(self.config.kafka)
        self.db = DatabaseManager(self.config.database.connection_string)
        self.model = None
        self.model_version = None
        self.safe_mode = False
        self.running = True
        self.events_processed = 0
        self.last_latency = 0.0
        
        self.mlflow_uri = self.config.mlflow.tracking_uri
        mlflow.set_tracking_uri(self.mlflow_uri)
        self.load_model()
        
        # Signal handling
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop = asyncio.get_event_loop()
                loop.add_signal_handler(sig, self.handle_shutdown)
            except NotImplementedError:
                # Fallback for Windows if needed, but we are on Darwin
                pass
        
    def handle_shutdown(self):
        logger.info("Shutdown signal received...")
        self.running = False

    def load_model(self):
        try:
            client = mlflow.MlflowClient()
            model_name = "credit_risk_model"
            model_versions = client.search_model_versions(f"name='{model_name}'")
            
            if model_versions:
                latest = max(model_versions, key=lambda x: int(x.version))
                self.model = mlflow.sklearn.load_model(f"models:/{model_name}/{latest.version}")
                self.model_version = latest.version
                logger.info(f"Loaded model version {self.model_version}")
            else:
                logger.warning("No model found in MLflow, using safe mode")
                self.safe_mode = True
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            self.safe_mode = True
    
    def rule_based_prediction(self, features):
        if isinstance(features, dict):
            val = features.get('feature_1', 0)
        else:
            val = features[0] if len(features) > 0 else 0
            
        if val > 1500:
            return 0.95, "HIGH_RISK"
        elif val > 1000:
            return 0.8, "HIGH_RISK"
        elif val > 500:
            return 0.5, "MEDIUM_RISK"
        else:
            return 0.2, "LOW_RISK"
    
    def predict(self, features):
        start_time = time.time()
        
        if self.safe_mode or self.model is None:
            risk_score, risk_class = self.rule_based_prediction(features)
        else:
            try:
                if isinstance(features, dict):
                    X = np.array(list(features.values())).reshape(1, -1)
                else:
                    X = np.array(features).reshape(1, -1)
                
                risk_score = float(self.model.predict_proba(X)[0][1])
                risk_class = "HIGH_RISK" if risk_score > 0.7 else "MEDIUM_RISK" if risk_score > 0.4 else "LOW_RISK"
            except Exception as e:
                logger.error(f"Model inference failed: {e}, falling back to rules")
                risk_score, risk_class = self.rule_based_prediction(features)
        
        latency = (time.time() - start_time) * 1000
        return risk_score, risk_class, latency
    
    def process_message(self, topic: str, message: str):
        if not self.running:
            return
            
        try:
            feature_vector = FeatureVector.from_json(message)
            trace_id = feature_vector.trace_id
            features = feature_vector.features
            
            risk_score, risk_class, latency = self.predict(features)
            self.last_latency = latency
            
            prediction = Prediction(
                trace_id=trace_id,
                timestamp=datetime.utcnow().isoformat(),
                model_version=self.model_version or "RULES",
                prediction=risk_class,
                confidence=risk_score,
                latency_ms=latency,
                metadata={"features": features}
            )
            
            self.producer.send('predictions', prediction.to_json())
            self.events_processed += 1
            
            if self.events_processed % 100 == 0:
                logger.info(f"Processed {self.events_processed} predictions")
            
        except Exception as e:
            logger.error(f"Error processing feature: {e}", exc_info=True)

    async def heartbeat_loop(self):
        while self.running:
            try:
                process = psutil.Process()
                metric = AgentMetric(
                    agent="ModelAgent",
                    status="SAFE_MODE" if self.safe_mode else "OK",
                    latency_ms=self.last_latency,
                    timestamp=datetime.utcnow().isoformat(),
                    cpu_percent=process.cpu_percent(),
                    memory_mb=process.memory_info().rss / 1024 / 1024,
                    events_processed=self.events_processed
                )
                self.producer.send('agent-metrics', metric.to_json())
                
                self.db.update_agent_health(
                    agent_name="ModelAgent",
                    status=metric.status,
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
        
        self.consumer = create_consumer(
            self.config.kafka,
            ['features'],
            f'{self.config.kafka.group_id_prefix}-model-agent',
            self.process_message
        )
        
        logger.info("ModelAgent starting consumer...")
        try:
            # Note: common.kafka_utils.KafkaConsumerWrapper.start() is blocking.
            # In an async context, we should probably run it in a thread or use aiokafka.
            # But let's stick to the current architecture and just run it.
            await asyncio.get_event_loop().run_in_executor(None, self.consumer.start)
        finally:
            self.cleanup()
            heartbeat_task.cancel()

    def cleanup(self):
        logger.info("Cleaning up resources...")
        self.running = False
        if hasattr(self, 'consumer'):
            self.consumer.close()
        if hasattr(self, 'producer'):
            self.producer.flush()
            self.producer.close()
        logger.info("Shutdown complete")

if __name__ == "__main__":
    agent = ModelAgent()
    asyncio.run(agent.run())
