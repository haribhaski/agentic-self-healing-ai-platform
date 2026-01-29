import asyncio
import json
import logging
import time
from datetime import datetime
from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaError
import mlflow
import mlflow.sklearn
import numpy as np
import sys
import os
import uuid

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(ROOT_DIR)

from dataclasses import asdict
from common.config import config
from common.schemas import FeatureVector, Prediction
from common.logger import setup_logger

logger = setup_logger("ModelAgent", config.kafka)

class ModelAgent:
    def __init__(self):
        self.config = config
        self.consumer = KafkaConsumer(
            'features',
            bootstrap_servers=self.config.kafka.bootstrap_servers,
            value_deserializer=lambda v: json.loads(v.decode('utf-8')),
            group_id='model-agent-group'
        )
        self.producer = KafkaProducer(
            bootstrap_servers=self.config.kafka.bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
        self.model = None
        self.model_version = None
        self.safe_mode = False
        self.mlflow_uri = self.config.mlflow.tracking_uri
        mlflow.set_tracking_uri(self.mlflow_uri)
        self.load_model()
        
    def load_model(self):
        """Load model from MLflow registry"""
        try:
            mlflow.set_tracking_uri(self.mlflow_uri)
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
        """Fallback rule-based decision for safe mode"""
        # Handle dict or list features
        if isinstance(features, dict):
            val = features.get('feature_1', 0)
        else:
            val = features[0] if len(features) > 0 else 0
            
        if val > 1500:  # High transaction value
            return 0.95, "HIGH_RISK"
        elif val > 1000:
            return 0.8, "HIGH_RISK"
        elif val > 500:
            return 0.5, "MEDIUM_RISK"
        else:
            return 0.2, "LOW_RISK"
    
    def predict(self, features):
        """Make prediction using model or rules"""
        start_time = time.time()
        
        if self.safe_mode or self.model is None:
            risk_score, risk_class = self.rule_based_prediction(features)
        else:
            try:
                # Convert dict to array if needed
                if isinstance(features, dict):
                    X = np.array(list(features.values())).reshape(1, -1)
                else:
                    X = np.array(features).reshape(1, -1)
                
                risk_score = float(self.model.predict_proba(X)[0][1])
                risk_class = "HIGH_RISK" if risk_score > 0.7 else "MEDIUM_RISK" if risk_score > 0.4 else "LOW_RISK"
            except Exception as e:
                logger.error(f"Model inference failed: {e}, falling back to rules")
                risk_score, risk_class = self.rule_based_prediction(features)
        
        inference_time = (time.time() - start_time) * 1000  # ms
        return risk_score, risk_class, inference_time
    
    def send_heartbeat(self):
        """Send agent health metrics"""
        heartbeat = {
            "agent": "ModelAgent",
            "status": "SAFE_MODE" if self.safe_mode else "OK",
            "model_version": self.model_version,
            "timestamp": datetime.utcnow().isoformat()
        }
        self.producer.send('agent-metrics', heartbeat)
        logger.info(f"Heartbeat sent: {heartbeat['status']}")
    
    async def process_features(self):
        """Process feature vectors and make predictions"""
        logger.info("ModelAgent started, consuming from features")
        
        heartbeat_task = asyncio.create_task(self.heartbeat_loop())
        
        try:
            for message in self.consumer:
                try:
                    feature_data = message.value
                    if isinstance(feature_data, str):
                        feature_data = json.loads(feature_data)
                    
                    trace_id = feature_data.get('trace_id', str(uuid.uuid4()))
                    features = feature_data.get('features', {})
                    
                    risk_score, risk_class, inference_time = self.predict(features)
                    
                    prediction = Prediction(
                        trace_id=trace_id,
                        timestamp=datetime.utcnow().isoformat(),
                        model_version=self.model_version or "RULES",
                        prediction=risk_class,
                        confidence=risk_score,
                        latency_ms=inference_time,
                        metadata={"features": features}
                    )
                    
                    self.producer.send('predictions', asdict(prediction))
                    
                    logger.info(f"Prediction: {trace_id} -> {risk_class} ({risk_score:.3f}) in {inference_time:.1f}ms")
                    
                except Exception as e:
                    logger.error(f"Error processing feature: {e}")
                    
        except KeyboardInterrupt:
            logger.info("Shutting down ModelAgent")
        finally:
            heartbeat_task.cancel()
            self.consumer.close()
            self.producer.close()
    
    async def heartbeat_loop(self):
        """Send periodic heartbeats"""
        while True:
            self.send_heartbeat()
            await asyncio.sleep(10)

if __name__ == "__main__":
    agent = ModelAgent()
    asyncio.run(agent.process_features())
