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
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))
from common.config import Config
from common.schemas import FeatureEvent, PredictionEvent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ModelAgent")

class ModelAgent:
    def __init__(self):
        self.config = Config()
        self.consumer = KafkaConsumer(
            'feature-vectors',
            bootstrap_servers=self.config.KAFKA_BOOTSTRAP_SERVERS,
            value_deserializer=lambda v: json.loads(v.decode('utf-8')),
            group_id='model-agent-group'
        )
        self.producer = KafkaProducer(
            bootstrap_servers=self.config.KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
        self.model = None
        self.model_version = None
        self.safe_mode = False
        self.mlflow_uri = self.config.MLFLOW_TRACKING_URI
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
        if features[0] < 600:  # credit_score
            return 0.8, "HIGH_RISK"
        elif features[0] < 700:
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
        logger.info("ModelAgent started, consuming from feature-vectors")
        
        heartbeat_task = asyncio.create_task(self.heartbeat_loop())
        
        try:
            for message in self.consumer:
                try:
                    feature_event = message.value
                    event_id = feature_event['event_id']
                    features = feature_event['features']
                    
                    risk_score, risk_class, inference_time = self.predict(features)
                    
                    prediction_event = {
                        "event_id": event_id,
                        "trace_id": feature_event.get('trace_id', event_id),
                        "risk_score": risk_score,
                        "risk_class": risk_class,
                        "model_version": self.model_version or "RULES",
                        "inference_time_ms": inference_time,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                    
                    self.producer.send('predictions', prediction_event)
                    
                    logger.info(f"Prediction: {event_id} -> {risk_class} ({risk_score:.3f}) in {inference_time:.1f}ms")
                    
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
