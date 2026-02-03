import asyncio
import json
import logging
import time
import signal
from datetime import datetime
from kafka.errors import KafkaError
from kafka import KafkaConsumer
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
from common.kafka_utils import create_producer
from backend.database.db_manager import DatabaseManager

logger = setup_logger("ModelAgent", config.kafka)


class ModelAgent:
    """
    Model Agent - Consumes features and produces predictions IN PARALLEL.
    
    Pipeline Flow:
    IngestAgent → features topic → ModelAgent → predictions topic → DecisionAgent
    
    Processes messages as they arrive (streaming mode)
    
    FIXED VERSION with proper Kafka consumer implementation
    """
    def __init__(self):
        self.config = config.get_agent_config("ModelAgent", 8003)
        self.producer = create_producer(self.config.kafka)
        self.db = DatabaseManager(self.config.database.connection_string)
        
        # Model state
        self.model = None
        self.model_version = None
        self.safe_mode = False
        
        # Agent state
        self.running = True
        self.events_processed = 0
        self.last_latency = 0.0
        self.recent_activity_count = 0  # Track recent activity for stable status
        
        # Process metrics
        self.process = psutil.Process()
        self.process.cpu_percent()
        
        # Load model
        self.mlflow_uri = self.config.mlflow.tracking_uri
        mlflow.set_tracking_uri("http://localhost:5020")
        self.load_model()
        
        # Signal handling (only in main thread)
        import threading
        if threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGINT, lambda signum, frame: self.handle_shutdown())
            signal.signal(signal.SIGTERM, lambda signum, frame: self.handle_shutdown())
        
        logger.info("✓ ModelAgent initialized - ready to consume from 'features' topic")
        logger.info(f"📋 Kafka bootstrap servers: {self.config.kafka.bootstrap_servers}")
        logger.info(f"📋 Database: {self.config.database.connection_string[:50]}...")
        
    def handle_shutdown(self):
        logger.info("Shutdown signal received...")
        self.running = False

    def load_model(self):
        """Load ML model from MLflow or fallback to rule-based"""
        try:
            client = mlflow.MlflowClient()
            model_name = "credit_risk_model"
            model_versions = client.search_model_versions(f"name='{model_name}'")
            
            if model_versions:
                latest = max(model_versions, key=lambda x: int(x.version))
                self.model = mlflow.sklearn.load_model(f"models:/{model_name}/{latest.version}")
                self.model_version = latest.version
                logger.info(f"✓ Loaded model version {self.model_version}")
            else:
                logger.warning("⚠ No model found in MLflow, using rule-based mode")
                self.safe_mode = True
        except Exception as e:
            logger.error(f"Failed to load model: {e}, using rule-based mode")
            self.safe_mode = True
    
    # ─── DROP-IN REPLACEMENTS for ModelAgent ───────────────────────────
    # Replace rule_based_prediction() and the risk_class line inside predict()

    def rule_based_prediction(self, features):
        """
        Fallback rule-based prediction when model is unavailable.

        FIX: The old version used max(vals), which meant any single large
        feature (e.g. Flow_Bytes_s = 45000) instantly made EVERYTHING
        HIGH_RISK.  Network features span wildly different scales — using
        max() is meaningless here.

        New approach: normalise each feature to a 0-1 range using known
        CICIDS2017 typical-max values, then average.  The average score
        is a much more stable signal.
        """
        # Approximate upper-bounds for common CICIDS2017 / network features.
        # Values above these are clipped to 1.0; unknown keys default to
        # a conservative 10_000 so they don't dominate.
        FEATURE_SCALES = {
            "Duration":                      120.0,
            "src_bytes":                     1_500_000.0,
            "dst_bytes":                     1_500_000.0,
            "wrong_fragment":                3.0,
            "urgent":                        1.0,
            "hot":                           10.0,
            "num_failed_logins":             5.0,
            "logged_in":                     1.0,
            "num_compromised":               10.0,
            "count":                         512.0,
            "srv_count":                     512.0,
            "dst_host_count":                255.0,
            "dst_host_srv_count":            255.0,
            "Total_Length_of_Packets":       1_500_000.0,
            "Packet_Length_Max":             1_500.0,
            "Packet_Length_Mean":            1_500.0,
            "Flow_Bytes_s":                  1_000_000.0,
            "Flow_Packets_s":               10_000.0,
            "Inter_Packet_Time_Mean":        1.0,
            "Fwd_Packets_s":                10_000.0,
            "Bwd_Packets_s":                10_000.0,
            "Fwd_Bytes_s":                   500_000.0,
            "Bwd_Bytes_s":                   500_000.0,
            "PSH_flag_count":                1.0,
            "ACK_flag_count":                1.0,
            "Down_Up_ratio":                 1.0,
            "Avg_Fwd_Bytes_per_bulk":        1_500_000.0,
            "Avg_Bwd_Bytes_per_bulk":        1_500_000.0,
        }
        DEFAULT_SCALE = 10_000.0

        if isinstance(features, dict):
            items = features.items()
        else:
            # If it's a plain list we have no keys — fall back to simple mean
            vals = [float(v) for v in features if str(v).replace('.','',1).replace('-','',1).isdigit()]
            mean_val = sum(vals) / len(vals) if vals else 0.0
            # Rough heuristic on the raw mean (last resort)
            if mean_val > 5000:
                return 0.85, "HIGH_RISK"
            elif mean_val > 500:
                return 0.55, "MEDIUM_RISK"
            else:
                return 0.2,  "LOW_RISK"

        # ── normalise & average ──────────────────────────────────
        scores = []
        for key, raw in items:
            try:
                val   = float(raw)
            except (TypeError, ValueError):
                continue
            scale = FEATURE_SCALES.get(key, DEFAULT_SCALE)
            scores.append(min(val / scale, 1.0))          # clip to [0, 1]

        avg_score = sum(scores) / len(scores) if scores else 0.0

        # ── thresholds on the normalised average ─────────────────
        if avg_score > 0.6:
            return round(avg_score, 4), "HIGH_RISK"
        elif avg_score > 0.3:
            return round(avg_score, 4), "MEDIUM_RISK"
        else:
            return round(avg_score, 4), "LOW_RISK"

    # ─────────────────────────────────────────────────────────────────────
    # Also fix the ML-model thresholds inside predict().
    # Replace the three lines inside the `else` (model-loaded) branch:
    # ─────────────────────────────────────────────────────────────────────

    def predict(self, features):
        """Make prediction using model or rules"""
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

                # ── FIX: sensible thresholds ─────────────────────
                # OLD (broken):
                #   HIGH_RISK if > 0.1   ← flags 90% of traffic
                #   MEDIUM   if > 0.05
                # NEW:
                if   risk_score > 0.7:
                    risk_class = "HIGH_RISK"
                elif risk_score > 0.4:
                    risk_class = "MEDIUM_RISK"
                else:
                    risk_class = "LOW_RISK"

            except Exception as e:
                logger.error(f"Model inference failed: {e}, falling back to rules")
                risk_score, risk_class = self.rule_based_prediction(features)

        latency = (time.time() - start_time) * 1000
        return risk_score, risk_class, latency
    
    def process_message(self, message):
        """
        Process incoming feature vectors from Kafka.
        
        CRITICAL: This is called for EACH message by the consumer
        
        Args:
            message: Kafka message object with .value attribute
        """
        if not self.running:
            return
        
        # ADD LOGGING HERE TO CONFIRM THIS IS BEING CALLED
        if self.events_processed == 0:
            logger.info("🎯 FIRST MESSAGE RECEIVED - process_message() IS BEING CALLED!")
        
        try:
            # Decode message value
            message_str = message.value.decode('utf-8') if isinstance(message.value, bytes) else message.value
            
            # Parse the feature vector
            feature_vector = FeatureVector.from_json(message_str)
            trace_id = feature_vector.trace_id
            features = feature_vector.features
            
            # Extract label if present in metadata
            label = None
            if hasattr(feature_vector, 'metadata') and feature_vector.metadata:
                label = feature_vector.metadata.get('label', None)
            
            # Make prediction
            risk_score, risk_class, latency = self.predict(features)
            self.last_latency = latency
            
            # Create prediction object
            prediction = Prediction(
                trace_id=trace_id,
                timestamp=datetime.utcnow().isoformat(),
                model_version=self.model_version or "RULES",
                prediction=risk_class,
                confidence=risk_score,
                latency_ms=latency,
                metadata={"features": features, "label": label}
            )
            
            # Store in database
            try:
                self.db.store_prediction(
                    trace_id=trace_id,
                    timestamp=prediction.timestamp,
                    model_version=prediction.model_version,
                    prediction=prediction.prediction,
                    confidence=prediction.confidence,
                    latency_ms=prediction.latency_ms,
                    features=features,
                    source_file=feature_vector.metadata.get('source_file', 'unknown') if feature_vector.metadata else 'unknown'
                )
            except Exception as e:
                logger.error(f"Failed to store prediction in DB: {e}")
            
            # Send to Kafka predictions topic (IMMEDIATELY)
            try:
                self.producer.send('predictions', prediction.to_json())
            except Exception as e:
                logger.error(f"Failed to send prediction to Kafka: {e}")
            
            self.events_processed += 1
            self.recent_activity_count += 1
            
            # Log progress every 100 predictions
            if self.events_processed % 100 == 0:
                logger.info(f"✓ ModelAgent processed {self.events_processed} predictions | "
                           f"Latest: {risk_class} (confidence: {risk_score:.2%})")
                try:
                    self.producer.flush()
                except Exception as e:
                    logger.error(f"Failed to flush producer: {e}")
            
            # More detailed logging every 1000 for debugging
            if self.events_processed % 1000 == 0:
                logger.info(f"📊 ModelAgent: {self.events_processed:,} total | "
                           f"Avg latency: {self.last_latency:.2f}ms | "
                           f"Mode: {'SAFE_MODE' if self.safe_mode else f'Model v{self.model_version}'}")
                    
        except Exception as e:
            logger.error(f"[ModelAgent] Error processing feature: {e}\nRaw message: {str(message.value)[:200]}", exc_info=True)

    async def heartbeat_loop(self):
        """Send periodic heartbeats"""
        while self.running:
            try:
                # Determine status based on recent activity (stable over heartbeat window)
                # Reset activity counter each heartbeat
                is_actively_processing = self.recent_activity_count > 0
                self.recent_activity_count = 0
                
                # Set stable status
                if self.safe_mode:
                    status = "SAFE_MODE"
                elif is_actively_processing:
                    status = "active"
                else:
                    status = "OK"  # Ready but not currently processing
                
                metric = AgentMetric(
                    agent="ModelAgent",
                    status=status,
                    latency_ms=self.last_latency,
                    timestamp=datetime.utcnow().isoformat(),
                    cpu_percent=self.process.cpu_percent(),
                    memory_mb=self.process.memory_info().rss / 1024 / 1024,
                    events_processed=self.events_processed
                )
                
                # Send to Kafka
                self.producer.send('agent-metrics', metric.to_json())
                
                # Update database
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

    def consume_loop(self):
        """
        BLOCKING consumer loop - runs in separate thread
        
        This is the CRITICAL fix - directly using KafkaConsumer instead of relying on
        the create_consumer wrapper which may have issues
        """
        logger.info("🔄 Starting consumer loop...")
        
        try:
            # Create consumer directly with explicit configuration
            consumer = KafkaConsumer(
                'features',
                bootstrap_servers=self.config.kafka.bootstrap_servers,
                group_id=f'{self.config.kafka.group_id_prefix}-model-agent',
                auto_offset_reset='latest',  # Start from latest (change to 'earliest' to reprocess)
                enable_auto_commit=True,
                auto_commit_interval_ms=1000,
                value_deserializer=lambda x: x,  # Keep as bytes, decode in process_message
                max_poll_records=100,
                session_timeout_ms=30000,
                heartbeat_interval_ms=10000
            )
            
            logger.info("✓ Consumer created successfully")
            logger.info(f"  → Subscribed to: {consumer.subscription()}")
            logger.info(f"  → Group ID: {consumer.config['group_id']}")
            logger.info(f"  → Bootstrap servers: {consumer.config['bootstrap_servers']}")
            
            # Wait for partition assignment
            logger.info("⏳ Waiting for partition assignment...")
            while not consumer.assignment() and self.running:
                consumer.poll(timeout_ms=1000)
                time.sleep(0.1)
            
            logger.info(f"✓ Assigned partitions: {consumer.assignment()}")
            
            # Log current offsets
            for partition in consumer.assignment():
                try:
                    current = consumer.position(partition)
                    end = consumer.end_offsets([partition])[partition]
                    logger.info(f"  Partition {partition.partition}: position={current}, end={end}, lag={end-current}")
                except Exception as e:
                    logger.warning(f"  Could not get offset info: {e}")
            
            logger.info("🚀 Starting message consumption loop...")
            logger.info("👂 Listening for messages on 'features' topic...")
            
            # Main consumption loop
            poll_count = 0
            last_log_time = time.time()
            
            while self.running:
                try:
                    # Poll for messages
                    msg_batch = consumer.poll(timeout_ms=1000, max_records=100)
                    
                    poll_count += 1
                    
                    # Log every 10 seconds if no messages
                    if time.time() - last_log_time > 10:
                        if self.events_processed == 0:
                            logger.info(f"⏳ Still waiting for messages... (polls: {poll_count})")
                        last_log_time = time.time()
                    
                    if msg_batch:
                        for topic_partition, messages in msg_batch.items():
                            logger.debug(f"📥 Received {len(messages)} messages from {topic_partition}")
                            
                            for message in messages:
                                self.process_message(message)
                    
                except Exception as e:
                    logger.error(f"Error in consume loop: {e}", exc_info=True)
                    if not self.running:
                        break
                    time.sleep(1)  # Backoff on error
            
            logger.info("🛑 Consumer loop stopped")
            consumer.close()
            logger.info("✓ Consumer closed")
            
        except Exception as e:
            logger.error(f"FATAL: Consumer loop error: {e}", exc_info=True)

    async def run(self):
        """Main run loop"""
        logger.info("=" * 60)
        logger.info("🚀 ModelAgent Starting")
        logger.info("=" * 60)
        
        # Start heartbeat in background
        heartbeat_task = asyncio.create_task(self.heartbeat_loop())
        
        logger.info("📋 Consumer configuration:")
        logger.info(f"  - Topic: 'features'")
        logger.info(f"  - Group ID: {self.config.kafka.group_id_prefix}-model-agent")
        logger.info(f"  - Bootstrap servers: {self.config.kafka.bootstrap_servers}")
        logger.info(f"  - Mode: {'SAFE_MODE (rules)' if self.safe_mode else f'ML Model v{self.model_version}'}")
        
        logger.info("\n🔄 Starting consumer in separate thread...")
        
        try:
            # Run consumer in executor (separate thread)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self.consume_loop)
        except Exception as e:
            logger.error(f"Error in main run loop: {e}", exc_info=True)
        finally:
            self.cleanup()
            heartbeat_task.cancel()

    def cleanup(self):
        """Clean up resources"""
        logger.info("\n🧹 Cleaning up resources...")
        self.running = False
        
        if hasattr(self, 'producer'):
            try:
                logger.info("  Flushing producer...")
                self.producer.flush(timeout=10)
                self.producer.close()
                logger.info("  ✓ Producer closed")
            except Exception as e:
                logger.error(f"  Error closing producer: {e}")
        
        logger.info(f"\n📊 Final Stats:")
        logger.info(f"  - Total predictions: {self.events_processed:,}")
        logger.info(f"  - Last latency: {self.last_latency:.2f}ms")
        logger.info("\n✅ Shutdown complete")


if __name__ == "__main__":
    agent = ModelAgent()
    asyncio.run(agent.run())