import random
import asyncio
import json
import logging
import time
import signal
from datetime import datetime
from kafka import KafkaConsumer
import sys
import os
import psutil

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(ROOT_DIR)

from dataclasses import asdict
from common.config import config
from common.schemas import Prediction, Decision, AgentMetric
from common.logger import setup_logger
from common.kafka_utils import create_producer
from backend.database.db_manager import DatabaseManager

logger = setup_logger("DecisionAgent", config.kafka)


class DecisionAgent:
    """
    Decision Agent - Consumes predictions and makes actionable decisions.
    
    Pipeline Flow:
    ModelAgent → predictions topic → DecisionAgent → decisions topic → External Systems
    
    Responsibilities:
    - Consume predictions from ModelAgent
    - Apply business rules to determine actions
    - Generate decision records with justification
    - Store decisions in database
    - Publish decisions for downstream systems
    """
    
    def __init__(self):
        self.config = config.get_agent_config("DecisionAgent", 8004)
        self.producer = create_producer(self.config.kafka)
        self.db = DatabaseManager(self.config.database.connection_string)
        
        # Agent state
        self.running = True
        self.events_processed = 0
        self.last_latency = 0.0
        self.recent_activity_count = 0
        
        # Decision statistics
        self.decisions_by_action = {
            'BLOCK': 0,
            'ALERT': 0,
            'MONITOR': 0,
            'ALLOW': 0
        }
        
        # Process metrics
        self.process = psutil.Process()
        self.process.cpu_percent()
        
        # Signal handling
        import threading
        if threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGINT, lambda signum, frame: self.handle_shutdown())
            signal.signal(signal.SIGTERM, lambda signum, frame: self.handle_shutdown())
        
        logger.info("=" * 70)
        logger.info("✓ DecisionAgent initialized - ready to consume from 'predictions' topic")
        logger.info(f"📋 Kafka bootstrap servers: {self.config.kafka.bootstrap_servers}")
        logger.info(f"📋 Database: {self.config.database.connection_string[:50]}...")
        logger.info("=" * 70)
        
    def handle_shutdown(self):
        logger.info("Shutdown signal received...")
        self.running = False
    
    def make_decision(self, prediction_data: dict):
        """
        Make decision based on prediction using business rules, with added randomness for testing.
        """
        """
        Make decision based on prediction using business rules.
        
        Business Rules:
        - HIGH_RISK (confidence > 0.7) → BLOCK
        - HIGH_RISK (confidence 0.5-0.7) → ALERT
        - MEDIUM_RISK → MONITOR
        - LOW_RISK → ALLOW
        
        Args:
            prediction_data: Dict with prediction info
            
        Returns:
            tuple: (action, reason, confidence)
        """
        start_time = time.time()
        
        prediction = prediction_data.get('prediction', 'UNKNOWN')
        confidence = prediction_data.get('confidence', 0.0)
        
        # Add randomness for testing/demo purposes
        rand = random.random()
        # 10% chance to BLOCK, 10% ALERT, 10% MONITOR, 70% ALLOW (for any prediction)
        if rand < 0.1:
            action = 'BLOCK'
            reason = f'Randomly blocked for testing ({confidence:.2%})'
        elif rand < 0.2:
            action = 'ALERT'
            reason = f'Random alert for testing ({confidence:.2%})'
        elif rand < 0.3:
            action = 'MONITOR'
            reason = f'Random monitor for testing ({confidence:.2%})'
        else:
            action = 'ALLOW'
            reason = f'Random allow for testing ({confidence:.2%})'
        
        latency = (time.time() - start_time) * 1000
        
        return action, reason, latency
    
    def process_message(self, message):
        """
        Process incoming predictions from Kafka.
        
        Args:
            message: Kafka message with prediction data
        """
        if not self.running:
            return
        
        # Log first message
        if self.events_processed == 0:
            logger.info("🎯 FIRST PREDICTION RECEIVED - DecisionAgent is processing!")
        
        try:
            # Decode message
            message_str = message.value.decode('utf-8') if isinstance(message.value, bytes) else message.value
            
            # Parse prediction
            prediction = Prediction.from_json(message_str)
            
            # Extract metadata
            metadata = prediction.metadata or {}
            features = metadata.get('features', {})
            label = metadata.get('label', 'N/A')
            
            # Make decision
            action, reason, decision_latency = self.make_decision({
                'prediction': prediction.prediction,
                'confidence': prediction.confidence,
                'features': features
            })
            
            # Update statistics
            self.decisions_by_action[action] += 1
            self.last_latency = decision_latency
            
            # Create decision object
            decision = Decision(
                trace_id=prediction.trace_id,
                timestamp=datetime.utcnow().isoformat(),
                decision=action,
                reasoning=reason,
                confidence=prediction.confidence,
                metadata={
                    'model_version': prediction.model_version,
                    'model_latency_ms': prediction.latency_ms,
                    'model_prediction': prediction.prediction,
                    'decision_latency_ms': decision_latency,
                    'label': label,
                    'features_count': len(features)
                }
            )
            
            # Show label comparison if available
            
            # Store in database
            try:
                self.db.store_decision(
                    trace_id=prediction.trace_id,
                    timestamp=decision.timestamp,
                    decision=action,
                    reasoning=reason,
                    confidence=prediction.confidence,
                    extra_data=decision.metadata
                )
            except Exception as e:
                logger.error(f"Failed to store decision in DB: {e}")
            
            # Publish to Kafka decisions topic
            try:
                self.producer.send('decisions', decision.to_json())
            except Exception as e:
                logger.error(f"Failed to send decision to Kafka: {e}")
            
            self.events_processed += 1
            self.recent_activity_count += 1
            
            # ── flush + compact one-liner log every 100 decisions ──────────
            if self.events_processed % 1000 == 0:
                try:
                    self.producer.flush()
                except Exception as e:
                    logger.error(f"Failed to flush producer: {e}")

                total       = sum(self.decisions_by_action.values())
                block_pct   = (self.decisions_by_action['BLOCK']   / total * 100) if total else 0
                alert_pct   = (self.decisions_by_action['ALERT']   / total * 100) if total else 0
                monitor_pct = (self.decisions_by_action['MONITOR'] / total * 100) if total else 0
                allow_pct   = (self.decisions_by_action['ALLOW']   / total * 100) if total else 0

                logger.info(
                    f"📊 [{self.events_processed:,} decisions] "
                    f"BLOCK: {self.decisions_by_action['BLOCK']:,} ({block_pct:.1f}%) | "
                    f"ALERT: {self.decisions_by_action['ALERT']:,} ({alert_pct:.1f}%) | "
                    f"MONITOR: {self.decisions_by_action['MONITOR']:,} ({monitor_pct:.1f}%) | "
                    f"ALLOW: {self.decisions_by_action['ALLOW']:,} ({allow_pct:.1f}%) | "
                    f"Latency: {self.last_latency:.2f}ms"
                )

            # ── detailed breakdown every 500 decisions ─────────────────────
            if self.events_processed % 1000 == 0:
                total = sum(self.decisions_by_action.values())
                logger.info("")
                logger.info("📈 " * 25)
                logger.info(f"📊 DecisionAgent Statistics (Total: {total:,})")
                logger.info("📈 " * 25)
                for action_key, count in self.decisions_by_action.items():
                    pct = (count / total * 100) if total > 0 else 0
                    logger.info(f"   {action_key:10s}: {count:6,} ({pct:5.1f}%)")
                logger.info(f"   Avg Latency: {self.last_latency:.2f}ms")
                logger.info("📈 " * 25)
                logger.info("")
                    
        except Exception as e:
            logger.error(f"[DecisionAgent] Error processing prediction: {e}", exc_info=True)
            logger.error(f"Raw message: {str(message.value)[:200]}")
    
    def _check_label_match(self, label: str, action: str) -> bool:
        """
        Check if decision action matches the ground truth label.
        
        Simple matching logic:
        - BENIGN label should → ALLOW action
        - DDoS/Attack label should → BLOCK or ALERT action
        """
        label_upper = str(label).upper()
        
        if 'BENIGN' in label_upper:
            return action == 'ALLOW'
        elif any(attack in label_upper for attack in ['DDOS', 'ATTACK', 'MALICIOUS', 'BOT']):
            return action in ['BLOCK', 'ALERT']
        else:
            # Unknown label, can't determine match
            return True  # Don't flag as mismatch
    
    async def heartbeat_loop(self):
        """Send periodic heartbeats to monitor agent health."""
        while self.running:
            try:
                is_actively_processing = self.recent_activity_count > 0
                self.recent_activity_count = 0
                
                status = "active" if is_actively_processing else "idle"
                
                metric = AgentMetric(
                    agent="DecisionAgent",
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
                    agent_name="DecisionAgent",
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
        Main consumer loop - runs in separate thread.
        Consumes predictions from 'predictions' topic.
        """
        logger.info("🔄 Starting consumer loop...")
        
        try:
            # Create Kafka consumer
            consumer = KafkaConsumer(
                'predictions',
                bootstrap_servers=self.config.kafka.bootstrap_servers,
                group_id=f'{self.config.kafka.group_id_prefix}-decision-agent',
                auto_offset_reset='latest',
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
            
            logger.info("")
            logger.info("🚀 " * 25)
            logger.info("🚀 DecisionAgent READY - Listening for predictions...")
            logger.info("🚀 " * 25)
            logger.info("")
            
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
                            logger.info(f"⏳ Waiting for predictions... (polls: {poll_count})")
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
        """Main run loop."""
        logger.info("")
        logger.info("=" * 70)
        logger.info("🚀 DecisionAgent Starting")
        logger.info("=" * 70)
        
        # Start heartbeat in background
        heartbeat_task = asyncio.create_task(self.heartbeat_loop())
        
        logger.info("📋 Consumer configuration:")
        logger.info(f"  - Topic: 'predictions'")
        logger.info(f"  - Group ID: {self.config.kafka.group_id_prefix}-decision-agent")
        logger.info(f"  - Bootstrap servers: {self.config.kafka.bootstrap_servers}")
        logger.info("  - Processing: Predictions → Decisions")
        
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
        """Clean up resources."""
        logger.info("")
        logger.info("🧹 Cleaning up resources...")
        self.running = False
        
        if hasattr(self, 'producer'):
            try:
                logger.info("  Flushing producer...")
                self.producer.flush(timeout=10)
                self.producer.close()
                logger.info("  ✓ Producer closed")
            except Exception as e:
                logger.error(f"  Error closing producer: {e}")
        
        logger.info("")
        logger.info("📊 Final Statistics:")
        logger.info("=" * 70)
        logger.info(f"  Total Decisions:  {self.events_processed:,}")
        
        total = sum(self.decisions_by_action.values())
        if total > 0:
            for action, count in sorted(self.decisions_by_action.items()):
                pct = (count / total * 100)
                logger.info(f"  {action:10s}:     {count:6,} ({pct:5.1f}%)")
        
        logger.info(f"  Last Latency:     {self.last_latency:.2f}ms")
        logger.info("=" * 70)
        logger.info("")
        logger.info("✅ DecisionAgent shutdown complete")
        logger.info("")


if __name__ == "__main__":
    agent = DecisionAgent()
    asyncio.run(agent.run())