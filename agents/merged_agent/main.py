import sys
import os
import signal
import uuid
from datetime import datetime, timezone
import time
import random
import threading
import psutil
import json
import io

# ========== CRITICAL: Install zstandard if not present ==========
try:
    import zstandard
except ImportError:
    print("✗ zstandard not found. Installing...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "zstandard"])
    import zstandard

if not hasattr(zstandard, "__version__"):
    zstandard.__version__ = "0.22.0"

# Import pandas AFTER ensuring zstandard is available
import pandas as pd
from hdfs import InsecureClient
from kafka import KafkaProducer


class StandaloneIngestionAgent:
    """
    Standalone ingestion agent that runs on host machine and connects to:
    - HDFS running in Docker (namenode:9870 exposed as localhost:9870)
    - Kafka running in Docker (kafka:9092 exposed as localhost:29092)
    
    FIXED: Now sends to BOTH raw-events AND features topics to match IngestAgent behavior
    Processes and sends each row IMMEDIATELY (not batched)
    """
    
    def __init__(self):
        # HDFS Configuration
        self.hdfs_url = 'http://localhost:9870'
        self.hdfs_path = '/datasets/cicids2017/'
        self.hdfs_user = 'root'
        
        # DataNode ports
        self.datanode_port_map = {
            9864: 9864,
            9865: 9865,
        }
        
        # Save original socket.getaddrinfo for cleanup
        import socket
        self.original_getaddrinfo = socket.getaddrinfo
        
        # Kafka Configuration
        self.kafka_bootstrap_servers = 'localhost:29092'
        
        # Agent state
        self.events_processed = 0
        self.running = True
        self.last_send_latency = 0.0
        self.process = psutil.Process()
        self.process.cpu_percent()
        
        # Initialize Kafka producer
        self.producer = self._create_kafka_producer()
        
        # Signal handling
        signal.signal(signal.SIGINT, self.handle_shutdown)
        signal.signal(signal.SIGTERM, self.handle_shutdown)

        # Start metrics heartbeat thread (5s interval to match other agents)
        self._metrics_thread = threading.Thread(target=self._metrics_heartbeat_loop, daemon=True)
        self._metrics_thread.start()
        
        print(f"✓ StandaloneIngestionAgent initialized")
        print(f"  - HDFS: {self.hdfs_url}")
        print(f"  - Kafka: {self.kafka_bootstrap_servers}")
        print(f"  - Sends to: raw-events AND features topics")
        print(f"  - Mode: STREAMING (sends each row immediately)")

    def _send_metrics_heartbeat(self):
        """Send agent-metrics heartbeat to Kafka"""
        metric = {
            "agent": "IngestAgent",  # Changed to match other agents
            "status": "active" if self.running else "idle",
            "events_processed": self.events_processed,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "cpu_percent": self.process.cpu_percent(),
            "memory_mb": self.process.memory_info().rss / 1024 / 1024,
            "latency_ms": self.last_send_latency * 1000,
        }
        try:
            self.producer.send("agent-metrics", value=metric)
            self.producer.flush()  # Ensure metrics are sent immediately
        except Exception as e:
            print(f"  ✗ Error sending agent-metrics heartbeat: {e}")

    def _metrics_heartbeat_loop(self):
        """Background thread to send metrics heartbeat every 5s (standardized)"""
        while True:
            if not self.running:
                break
            self._send_metrics_heartbeat()
            time.sleep(5)  # Changed from 10s to 5s to match other agents
    
    def _create_kafka_producer(self):
        """Create Kafka producer with retry logic"""
        max_retries = 5
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                producer = KafkaProducer(
                    bootstrap_servers=self.kafka_bootstrap_servers,
                    value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                    key_serializer=lambda k: k.encode('utf-8') if k else None,
                    acks='all',
                    retries=3,
                    max_in_flight_requests_per_connection=5,  # Allow some batching
                    linger_ms=10,  # Small linger for micro-batching
                    batch_size=16384,  # Default batch size
                    request_timeout_ms=30000,
                    max_block_ms=60000
                )
                print(f"✓ Connected to Kafka at {self.kafka_bootstrap_servers}")
                return producer
            except Exception as e:
                print(f"✗ Kafka connection attempt {attempt + 1}/{max_retries} failed: {e}")
                if attempt < max_retries - 1:
                    print(f"  Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    print("\n❌ Could not connect to Kafka. Please ensure:")
                    print("  1. Kafka container is running: docker ps | grep kafka")
                    print("  2. Port 29092 is exposed: docker port kafka")
                    raise
    
    def handle_shutdown(self, signum, frame):
        print(f"\n⚠ Received signal {signum}, shutting down gracefully...")
        self.running = False
    
    def _setup_datanode_routing(self):
        """Setup custom DNS resolution for DataNodes"""
        import socket
        
        original_getaddrinfo = socket.getaddrinfo
        
        def custom_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
            if host and len(host) == 12 and all(c in '0123456789abcdef' for c in host):
                mapped_port = self.datanode_port_map.get(port, port)
                return original_getaddrinfo('localhost', mapped_port, family, type, proto, flags)
            
            if host and 'datanode' in host.lower():
                mapped_port = self.datanode_port_map.get(port, port)
                return original_getaddrinfo('localhost', mapped_port, family, type, proto, flags)
            
            return original_getaddrinfo(host, port, family, type, proto, flags)
        
        socket.getaddrinfo = custom_getaddrinfo
    
    def _cleanup_datanode_routing(self):
        """Restore original socket.getaddrinfo"""
        import socket
        socket.getaddrinfo = self.original_getaddrinfo
    
    def test_hdfs_connection(self):
        """Test HDFS connectivity and list available files"""
        try:
            client = InsecureClient(self.hdfs_url, user=self.hdfs_user, timeout=10)
            
            print(f"\n📁 Testing HDFS connection to {self.hdfs_url}...")
            status = client.status('/')
            print(f"✓ HDFS connection successful")
            
            print(f"\n📂 Listing files in {self.hdfs_path}...")
            try:
                files = client.list(self.hdfs_path)
                csv_files = [f for f in files if f.endswith('.csv')]
                
                if csv_files:
                    print(f"✓ Found {len(csv_files)} CSV files:")
                    for f in csv_files[:5]:
                        file_status = client.status(f"{self.hdfs_path}{f}")
                        size_mb = file_status['length'] / (1024 * 1024)
                        print(f"  - {f} ({size_mb:.2f} MB)")
                    if len(csv_files) > 5:
                        print(f"  ... and {len(csv_files) - 5} more files")
                    return csv_files
                else:
                    print(f"⚠ No CSV files found in {self.hdfs_path}")
                    return []
            except Exception as e:
                print(f"✗ Error listing directory: {e}")
                return []
                
        except Exception as e:
            print(f"✗ HDFS connection failed: {e}")
            print("\nPlease ensure:")
            print("  1. HDFS namenode is running: docker ps | grep namenode")
            print("  2. Port 9870 is exposed: docker port namenode")
            return []
    
    def read_hdfs_csv_streaming(self, file_path, chunk_size=1000):
        """
        Read CSV file from HDFS in chunks and yield rows immediately
        This allows streaming processing instead of loading entire file
        """
        client = None
        try:
            self._setup_datanode_routing()
            
            client = InsecureClient(self.hdfs_url, user=self.hdfs_user, timeout=60)
            
            file_status = client.status(file_path)
            file_size_mb = file_status['length'] / (1024 * 1024)
            print(f"  File size: {file_size_mb:.2f} MB")
            
            print(f"  Reading file in streaming mode (chunk_size={chunk_size})...")
            
            # Read file content into memory
            with client.read(file_path, encoding='utf-8', chunk_size=65536) as reader:
                if hasattr(reader, 'read'):
                    content = reader.read()
                else:
                    content = ''.join(reader)
            
            csv_buffer = io.StringIO(content)
            
            # Process in chunks but yield rows immediately
            chunk_count = 0
            for chunk in pd.read_csv(csv_buffer, chunksize=chunk_size, low_memory=False):
                chunk_count += 1
                
                # Yield each row immediately from this chunk
                for idx, row in chunk.iterrows():
                    yield row
                    
        except Exception as e:
            print(f"  ✗ Error reading {file_path}: {e}")
            import traceback
            traceback.print_exc()
            raise
        finally:
            self._cleanup_datanode_routing()
    
    def extract_features(self, row):
        """
        Extract numeric features from a row (matches IngestAgent behavior)
        
        Args:
            row: Pandas Series representing a CSV row
            
        Returns:
            dict: Dictionary of numeric features only
        """
        features = {}
        for key, value in row.items():
            # Only include numeric values
            if pd.notna(value) and isinstance(value, (int, float, np.int64, np.float64)):
                features[key] = float(value)
        return features
    
    def process_csv_files(self, csv_files, max_events_per_file=None, max_files=None):
        """
        Process CSV files from HDFS and send to Kafka ROW-BY-ROW (streaming)
        SENDS TO BOTH raw-events AND features topics IMMEDIATELY for each row
        """
        if max_files:
            csv_files = csv_files[:max_files]
        
        print(f"\n🔄 Starting to process {len(csv_files)} CSV files...")
        if max_events_per_file:
            print(f"  Max events per file: {max_events_per_file:,}")
        else:
            print(f"  Processing all rows in each file")
        
        for idx, csv_file in enumerate(csv_files, 1):
            if not self.running:
                print("\n⚠ Shutdown requested, stopping processing...")
                break
            
            file_path = f"{self.hdfs_path}{csv_file}"
            print(f"\n{'='*60}")
            print(f"📄 FILE [{idx}/{len(csv_files)}]: {csv_file}")
            print(f"{'='*60}")
            
            try:
                events_from_file = 0
                start_time = time.time()
                last_log_time = start_time
                
                # Stream rows from HDFS
                for row in self.read_hdfs_csv_streaming(file_path, chunk_size=1000):
                    if not self.running:
                        break
                    
                    if max_events_per_file and events_from_file >= max_events_per_file:
                        print(f"  ⚠ Reached max events limit ({max_events_per_file:,}) for this file")
                        break
                    
                    # Create trace_id for this event
                    trace_id = f"{csv_file}-{events_from_file}"
                    timestamp = datetime.now(timezone.utc).isoformat()
                    
                    # SEND TO KAFKA IMMEDIATELY (not batched)
                    self._send_to_kafka(trace_id, timestamp, row, csv_file)
                    
                    events_from_file += 1
                    self.events_processed += 1
                    
                    # Progress update every 1000 rows
                    current_time = time.time()
                    if events_from_file % 1000 == 0:
                        elapsed = current_time - start_time
                        interval_elapsed = current_time - last_log_time
                        rate = events_from_file / elapsed if elapsed > 0 else 0
                        interval_rate = 1000 / interval_elapsed if interval_elapsed > 0 else 0
                        
                        print(f"  ✓ {events_from_file:,} rows | "
                              f"Overall: {rate:.1f} rows/sec | "
                              f"Last 1k: {interval_rate:.1f} rows/sec | "
                              f"Total: {self.events_processed:,}")
                        
                        last_log_time = current_time
                        
                        # Flush Kafka producer every 1000 rows to ensure delivery
                        try:
                            self.producer.flush(timeout=5)
                        except Exception as e:
                            print(f"  ⚠ Warning: Kafka flush error: {e}")
                
                elapsed = time.time() - start_time
                rate = events_from_file / elapsed if elapsed > 0 else 0
                print(f"\n  ✅ COMPLETED FILE: {csv_file}")
                print(f"     Rows processed: {events_from_file:,}")
                print(f"     Time elapsed: {elapsed:.2f}s")
                print(f"     Average rate: {rate:.1f} rows/sec")
                print(f"     Total processed so far: {self.events_processed:,}")
                
                # Final flush for this file
                self.producer.flush(timeout=10)
                
            except Exception as e:
                print(f"  ✗ Error processing file {csv_file}: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        print(f"\n{'='*60}")
        print(f"✅ ALL FILES COMPLETED")
        print(f"{'='*60}")
        print(f"   Total events processed: {self.events_processed:,}")
    
    def _create_event_from_row(self, row, source_file):
        """Create raw event dictionary from DataFrame row"""
        data_dict = {}
        for key, value in row.items():
            if pd.isna(value):
                data_dict[key] = None
            elif isinstance(value, (int, float, str, bool)):
                data_dict[key] = value
            else:
                data_dict[key] = str(value)
        
        return data_dict
    
    def _send_to_kafka(self, trace_id, timestamp, row, source_file):
        """
        Send BOTH raw event and features to Kafka IMMEDIATELY
        This matches the IngestAgent behavior
        """
        try:
            send_start = time.time()
            
            # 1. Create and send raw event to raw-events topic
            data_dict = self._create_event_from_row(row, source_file)
            raw_event = {
                'trace_id': trace_id,
                'timestamp': timestamp,
                'event_type': 'cicids2017_row',
                'data': data_dict
            }
            
            # Send immediately (producer will micro-batch internally)
            self.producer.send(
                'raw-events',
                key=trace_id,
                value=raw_event
            )
            
            # 2. Extract features and send to features topic
            features = self.extract_features(row)
            
            if features:  # Only send if we have numeric features
                feature_vector = {
                    'trace_id': trace_id,
                    'timestamp': timestamp,
                    'features': features,
                    'metadata': {
                        'source_file': source_file
                    }
                }
                
                # Send immediately (producer will micro-batch internally)
                self.producer.send(
                    'features',
                    key=trace_id,
                    value=feature_vector
                )
            
            self.last_send_latency = time.time() - send_start
            
        except Exception as e:
            print(f"  ✗ Error sending event to Kafka: {e}")
            raise
    
    def get_metrics(self):
        """Get current agent metrics"""
        return {
            'events_processed': self.events_processed,
            'cpu_percent': self.process.cpu_percent(),
            'memory_mb': self.process.memory_info().rss / 1024 / 1024,
            'last_send_latency_ms': self.last_send_latency * 1000,
            'running': self.running
        }
    
    def print_metrics(self):
        """Print current metrics"""
        metrics = self.get_metrics()
        print(f"\n📊 Final Metrics:")
        print(f"  - Events Processed: {metrics['events_processed']:,}")
        print(f"  - CPU Usage: {metrics['cpu_percent']:.1f}%")
        print(f"  - Memory Usage: {metrics['memory_mb']:.1f} MB")
        print(f"  - Last Send Latency: {metrics['last_send_latency_ms']:.2f} ms")
    
    def run(self, max_events_per_file=None, max_files=None):
        """Main run loop"""
        print("\n" + "="*60)
        print("🚀 Starting Standalone Ingestion Agent")
        print("="*60)
        
        # Test connections
        csv_files = self.test_hdfs_connection()
        
        if not csv_files:
            print("\n❌ No CSV files found. Exiting...")
            return
        
        # Process files
        try:
            self.process_csv_files(csv_files, max_events_per_file, max_files)
        except KeyboardInterrupt:
            print("\n⚠ Interrupted by user")
        except Exception as e:
            print(f"\n❌ Error during processing: {e}")
            import traceback
            traceback.print_exc()
        
        # Cleanup
        print("\n🧹 Cleaning up...")
        print("  Flushing remaining messages to Kafka...")
        self.producer.flush(timeout=30)
        self.producer.close()
        
        # Final metrics
        self.print_metrics()
        
        print("\n✅ Shutdown complete")


# Import numpy for feature extraction
import numpy as np


def main():
    """Main entry point with argument parsing"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Standalone HDFS to Kafka Ingestion Agent (STREAMING MODE)')
    parser.add_argument('--events-per-file', type=int, default=None,
                        help='Maximum events to process per file (default: all rows)')
    parser.add_argument('--max-files', type=int, default=None,
                        help='Maximum number of files to process (default: all)')
    parser.add_argument('--test-only', action='store_true',
                        help='Only test connections, do not process files')
    
    args = parser.parse_args()
    
    try:
        agent = StandaloneIngestionAgent()
        
        if args.test_only:
            print("\n✓ Test mode - connections verified, exiting...")
        else:
            agent.run(max_events_per_file=args.events_per_file, max_files=args.max_files)
            
    except KeyboardInterrupt:
        print("\n⚠ Interrupted by user")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()