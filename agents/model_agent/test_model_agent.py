#!/usr/bin/env python3
"""
Diagnostic script to test ModelAgent Kafka consumption
Tests the exact consumer setup that ModelAgent uses
"""

import json
import time
from kafka import KafkaConsumer
from kafka.errors import KafkaError

# Kafka configuration (matching your setup)
BOOTSTRAP_SERVERS = 'localhost:29092'
TOPIC = 'features'
GROUP_ID = 'mas-model-agent-test'

print("=" * 60)
print("🔍 ModelAgent Kafka Consumer Diagnostic")
print("=" * 60)

print(f"\n📋 Configuration:")
print(f"  - Bootstrap Servers: {BOOTSTRAP_SERVERS}")
print(f"  - Topic: {TOPIC}")
print(f"  - Group ID: {GROUP_ID}")

# Test 1: Check topic exists and has messages
print(f"\n\n1️⃣ Testing topic metadata...")
try:
    from kafka.admin import KafkaAdminClient
    admin = KafkaAdminClient(bootstrap_servers=BOOTSTRAP_SERVERS)
    topics = admin.list_topics()
    
    if TOPIC in topics:
        print(f"  ✅ Topic '{TOPIC}' exists")
    else:
        print(f"  ❌ Topic '{TOPIC}' NOT FOUND")
        print(f"  Available topics: {topics}")
        exit(1)
except Exception as e:
    print(f"  ⚠️  Could not verify topic: {e}")

# Test 2: Create consumer with auto_offset_reset='earliest'
print(f"\n\n2️⃣ Creating consumer with auto_offset_reset='earliest'...")
try:
    consumer = KafkaConsumer(
        TOPIC,
        bootstrap_servers=BOOTSTRAP_SERVERS,
        group_id=GROUP_ID,
        auto_offset_reset='earliest',  # Start from beginning
        enable_auto_commit=True,
        value_deserializer=lambda x: x.decode('utf-8')
    )
    print(f"  ✅ Consumer created successfully")
except Exception as e:
    print(f"  ❌ Failed to create consumer: {e}")
    exit(1)

# Test 3: Check partition assignment
print(f"\n\n3️⃣ Checking partition assignment...")
time.sleep(2)  # Wait for assignment
partitions = consumer.assignment()
print(f"  Assigned partitions: {partitions}")

if not partitions:
    print(f"  ⚠️  No partitions assigned yet, waiting...")
    consumer.poll(timeout_ms=5000)
    partitions = consumer.assignment()
    print(f"  After poll - Assigned partitions: {partitions}")

# Test 4: Check current offsets
print(f"\n\n4️⃣ Checking consumer offsets...")
for partition in partitions:
    try:
        current = consumer.position(partition)
        beginning = consumer.beginning_offsets([partition])[partition]
        end = consumer.end_offsets([partition])[partition]
        
        print(f"\n  Partition {partition.partition}:")
        print(f"    - Beginning offset: {beginning}")
        print(f"    - Current position: {current}")
        print(f"    - End offset: {end}")
        print(f"    - Available messages: {end - current}")
    except Exception as e:
        print(f"  ⚠️  Error getting offsets for {partition}: {e}")

# Test 5: Try to consume messages
print(f"\n\n5️⃣ Attempting to consume messages (10 second timeout)...")
print(f"  Polling...")

messages_consumed = 0
timeout = time.time() + 10  # 10 second timeout

try:
    while time.time() < timeout:
        msg_batch = consumer.poll(timeout_ms=1000, max_records=10)
        
        if msg_batch:
            for topic_partition, messages in msg_batch.items():
                for message in messages:
                    messages_consumed += 1
                    print(f"\n  📨 Message {messages_consumed}:")
                    print(f"    - Partition: {message.partition}")
                    print(f"    - Offset: {message.offset}")
                    print(f"    - Key: {message.key}")
                    
                    # Try to parse as JSON
                    try:
                        data = json.loads(message.value)
                        print(f"    - trace_id: {data.get('trace_id', 'N/A')}")
                        print(f"    - timestamp: {data.get('timestamp', 'N/A')}")
                        print(f"    - features count: {len(data.get('features', {}))}")
                    except:
                        print(f"    - Value (first 100 chars): {message.value[:100]}")
                    
                    if messages_consumed >= 5:
                        break
            
            if messages_consumed >= 5:
                break
        else:
            print(f"  ⏳ No messages in this poll...")
    
    if messages_consumed == 0:
        print(f"\n  ❌ NO MESSAGES CONSUMED")
        print(f"  \n  Possible reasons:")
        print(f"    1. Consumer group '{GROUP_ID}' has already consumed all messages")
        print(f"    2. Messages are in a different topic")
        print(f"    3. Producer hasn't sent messages yet")
        print(f"    4. Kafka consumer configuration issue")
    else:
        print(f"\n  ✅ Successfully consumed {messages_consumed} messages")
        
except KeyboardInterrupt:
    print(f"\n  ⚠️  Interrupted by user")
except Exception as e:
    print(f"\n  ❌ Error during consumption: {e}")
    import traceback
    traceback.print_exc()

# Test 6: Try with a DIFFERENT group ID (to reset offsets)
print(f"\n\n6️⃣ Testing with NEW consumer group (to verify messages exist)...")
NEW_GROUP_ID = f'diagnostic-{int(time.time())}'
print(f"  Using temporary group: {NEW_GROUP_ID}")

try:
    consumer2 = KafkaConsumer(
        TOPIC,
        bootstrap_servers=BOOTSTRAP_SERVERS,
        group_id=NEW_GROUP_ID,
        auto_offset_reset='earliest',
        enable_auto_commit=False,  # Don't commit offsets
        value_deserializer=lambda x: x.decode('utf-8'),
        consumer_timeout_ms=5000  # 5 second timeout
    )
    
    fresh_messages = 0
    for message in consumer2:
        fresh_messages += 1
        if fresh_messages >= 3:
            break
    
    print(f"  ✅ Fresh consumer consumed {fresh_messages} messages")
    print(f"  → This confirms messages ARE available in the topic")
    consumer2.close()
    
except Exception as e:
    print(f"  ❌ Fresh consumer also failed: {e}")

# Cleanup
print(f"\n\n🧹 Cleanup...")
consumer.close()

print(f"\n" + "=" * 60)
print(f"📊 DIAGNOSTIC SUMMARY")
print(f"=" * 60)
print(f"  Messages consumed (original group): {messages_consumed}")
print(f"\n  💡 RECOMMENDATIONS:")

if messages_consumed == 0:
    print(f"""
  ❌ ModelAgent is likely NOT consuming because:
  
  1. Consumer group '{GROUP_ID}' offsets are at the END
     → Solution: Reset offsets or use a new group ID
     
  2. Check your create_consumer() function:
     → Ensure auto_offset_reset='earliest' or 'latest'
     → Verify the callback is being called
     → Check for exceptions in the consumer thread
     
  3. Verify ModelAgent is actually starting the consumer:
     → Add logging BEFORE consumer.start()
     → Add logging in process_message() callback
     → Check if consumer.start() is blocking properly
""")
else:
    print(f"""
  ✅ Kafka consumption works fine!
  
  The issue is likely in ModelAgent code:
  - Check if process_message() callback is being called
  - Add logging at the START of process_message()
  - Verify consumer.start() is not throwing exceptions
""")

print("=" * 60)