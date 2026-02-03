#!/usr/bin/env python3
"""
Database Quick Fix Script
Automatically fixes common database issues
"""
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

print("=" * 80)
print("DATABASE QUICK FIX TOOL")
print("=" * 80)
print()

from common.config import config
import psycopg2

db_config = config.database

print("Connecting to database...")
try:
    conn = psycopg2.connect(db_config.connection_string)
    conn.autocommit = True
    cursor = conn.cursor()
    print("✅ Connected")
    print()
except Exception as e:
    print(f"❌ Cannot connect: {e}")
    print()
    print("MANUAL FIX REQUIRED:")
    print("1. Start PostgreSQL:")
    print("   sudo systemctl start postgresql")
    print("   OR: docker-compose up -d postgres")
    print()
    print("2. Create database if it doesn't exist:")
    print(f"   createdb -U {db_config.user} {db_config.database}")
    print()
    sys.exit(1)

# Fix 1: Create tables if they don't exist
print("Fix 1: Creating tables if missing...")
try:
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS incidents (
            incident_id SERIAL PRIMARY KEY,
            incident_type VARCHAR(50) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'OPEN',
            metrics_snapshot JSONB,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMP,
            resolution_details JSONB
        )
    """)
    print("   ✅ incidents table ready")
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS incident_logs (
            log_id SERIAL PRIMARY KEY,
            incident_id INTEGER REFERENCES incidents(incident_id),
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            action VARCHAR(50),
            details JSONB,
            agent VARCHAR(50)
        )
    """)
    print("   ✅ incident_logs table ready")
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_health (
            agent_name VARCHAR(50) PRIMARY KEY,
            status VARCHAR(20),
            last_heartbeat TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            latency_ms FLOAT,
            cpu_percent FLOAT,
            memory_mb FLOAT,
            events_processed INTEGER
        )
    """)
    print("   ✅ agent_health table ready")
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS policy_decisions (
            decision_id SERIAL PRIMARY KEY,
            incident_id INTEGER REFERENCES incidents(incident_id),
            policy_type VARCHAR(50),
            decision JSONB,
            confidence FLOAT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("   ✅ policy_decisions table ready")
    
    print()
    
except Exception as e:
    print(f"   ❌ Error creating tables: {e}")
    print()

# Fix 2: Grant permissions
print("Fix 2: Granting permissions...")
try:
    cursor.execute(f"""
        GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO {db_config.user}
    """)
    cursor.execute(f"""
        GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO {db_config.user}
    """)
    print("   ✅ Permissions granted")
    print()
except Exception as e:
    print(f"   ⚠️  Could not grant permissions: {e}")
    print("   You may need to run this as a superuser")
    print()

# Fix 3: Create indexes for performance
print("Fix 3: Creating indexes...")
try:
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_incidents_status 
        ON incidents(status)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_incidents_type 
        ON incidents(incident_type)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_incident_logs_incident_id 
        ON incident_logs(incident_id)
    """)
    print("   ✅ Indexes created")
    print()
except Exception as e:
    print(f"   ⚠️  Could not create indexes: {e}")
    print()

# Test the fix
print("Testing database health...")
try:
    cursor.execute("SELECT 1")
    result = cursor.fetchone()
    if result and result[0] == 1:
        print("✅ Database health check PASSED")
    else:
        print("❌ Database health check FAILED")
    print()
except Exception as e:
    print(f"❌ Health check failed: {e}")
    print()

conn.close()

print("=" * 80)
print("FIX COMPLETE")
print("=" * 80)
print()
print("Try running your HealingAgent again:")
print("   python agents/healing_agent/main.py")
print()