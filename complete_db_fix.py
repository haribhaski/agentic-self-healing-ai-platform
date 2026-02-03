#!/usr/bin/env python3
"""
Complete Database Fix - Handles SQLAlchemy Text() Issue
Fixes schema conflicts and ensures health check works properly
"""
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

print("=" * 80)
print("COMPLETE DATABASE FIX")
print("=" * 80)
print()

from common.config import config
from sqlalchemy import create_engine, inspect, text
from backend.database.models import Base

db_config = config.database
connection_string = db_config.connection_string

print(f"Database: {db_config.database}")
print(f"Host: {db_config.host}:{db_config.port}")
print(f"User: {db_config.user}")
print()

print("⚠️  This will drop and recreate all tables (data will be lost)")
response = input("Continue? (yes/no): ")
if response.lower() != 'yes':
    print("Aborted.")
    sys.exit(0)

print()
print("=" * 80)
print("FIXING DATABASE")
print("=" * 80)
print()

# Step 1: Connect
print("Step 1: Connecting to database...")
try:
    engine = create_engine(connection_string, pool_pre_ping=True)
    # Test with proper text() wrapper for SQLAlchemy 2.0
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        result.fetchone()
    print("✅ Connected successfully")
    print()
except Exception as e:
    print(f"❌ Connection failed: {e}")
    print()
    print("Solutions:")
    print("  1. Start PostgreSQL: sudo systemctl start postgresql")
    print("  2. Or use Docker: docker-compose up -d postgres")
    print("  3. Check credentials in common/config.py")
    sys.exit(1)

# Step 2: Drop all existing tables
print("Step 2: Dropping all existing tables...")
try:
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()
    
    if existing_tables:
        print(f"   Found {len(existing_tables)} tables to drop")
        Base.metadata.drop_all(engine)
        print("   ✅ All tables dropped")
    else:
        print("   No existing tables found")
    print()
except Exception as e:
    print(f"   ❌ Error dropping tables: {e}")
    import traceback
    traceback.print_exc()
    print()

# Step 3: Create all tables from SQLAlchemy models
print("Step 3: Creating tables from models...")
try:
    Base.metadata.create_all(engine)
    
    # Verify tables were created
    inspector = inspect(engine)
    new_tables = inspector.get_table_names()
    
    print(f"   ✅ Created {len(new_tables)} tables:")
    for table in sorted(new_tables):
        print(f"      - {table}")
    print()
except Exception as e:
    print(f"   ❌ Error creating tables: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Step 4: Verify critical table schemas
print("Step 4: Verifying table schemas...")
critical_tables = {
    'incidents': ['incident_id', 'type', 'status', 'detected_at'],
    'healing_actions': ['action_id', 'incident_id', 'agl_decision'],
    'agent_health': ['agent_name', 'status', 'last_heartbeat'],
    'memory_chunks': ['memory_id', 'incident_type', 'outcome']
}

all_ok = True
for table_name, required_cols in critical_tables.items():
    try:
        columns = inspector.get_columns(table_name)
        col_names = [col['name'] for col in columns]
        
        missing = [col for col in required_cols if col not in col_names]
        if missing:
            print(f"   ❌ {table_name}: Missing columns {missing}")
            all_ok = False
        else:
            print(f"   ✅ {table_name}: All required columns present")
    except Exception as e:
        print(f"   ❌ {table_name}: Error checking columns: {e}")
        all_ok = False

print()

if not all_ok:
    print("⚠️  Some table schemas are incomplete")
    print()

# Step 5: Test database health check (with proper text())
print("Step 5: Testing database health check...")
try:
    with engine.connect() as conn:
        # Use text() wrapper for raw SQL (SQLAlchemy 2.0 requirement)
        result = conn.execute(text("SELECT 1"))
        value = result.fetchone()[0]
        
        if value == 1:
            print("   ✅ Health check PASSED")
        else:
            print("   ❌ Health check returned unexpected value")
    print()
except Exception as e:
    print(f"   ❌ Health check failed: {e}")
    import traceback
    traceback.print_exc()
    print()

# Step 6: Test DatabaseManager class
print("Step 6: Testing DatabaseManager class...")
try:
    from backend.database.db_manager import DatabaseManager
    
    db = DatabaseManager(connection_string)
    print("   ✅ DatabaseManager instantiated")
    
    # Test health check method
    is_healthy = db.check_database_health()
    if is_healthy:
        print("   ✅ DatabaseManager.check_database_health() PASSED")
    else:
        print("   ❌ DatabaseManager.check_database_health() FAILED")
    print()
except Exception as e:
    print(f"   ❌ DatabaseManager test failed: {e}")
    import traceback
    traceback.print_exc()
    print()

# Step 7: Show incidents table schema (most critical)
print("Step 7: Showing incidents table schema...")
try:
    columns = inspector.get_columns('incidents')
    print("   Columns:")
    for col in columns:
        col_type = str(col['type'])
        nullable = "NULL" if col['nullable'] else "NOT NULL"
        pk = " (PRIMARY KEY)" if col.get('primary_key') else ""
        default = f" DEFAULT {col['default']}" if col.get('default') else ""
        print(f"      {col['name']}: {col_type} {nullable}{pk}{default}")
    print()
except Exception as e:
    print(f"   ❌ Error showing schema: {e}")
    print()

print("=" * 80)
print("FIX COMPLETE")
print("=" * 80)
print()
print("✅ Database is ready!")
print()
print("Next steps:")
print("1. Start HealingAgent:")
print("   python agents/healing_agent/main.py")
print()
print("2. Start MonitoringAgent:")
print("   python agents/monitoring_agent/main.py")
print()
print("You should NOT see 'DEGRADED mode' in the logs anymore.")
print()