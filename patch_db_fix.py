#!/usr/bin/env python3
"""
Automated Patch for db_manager.py
Fixes the SQLAlchemy 2.0 text() requirement in check_database_health()
"""
import os
import sys

# Find db_manager.py
db_manager_path = "backend/database/db_manager.py"

if not os.path.exists(db_manager_path):
    print(f"❌ Cannot find {db_manager_path}")
    print("   Make sure you're running this from the project root directory")
    sys.exit(1)

print("=" * 80)
print("PATCHING db_manager.py")
print("=" * 80)
print()

# Read the file
print(f"Reading {db_manager_path}...")
with open(db_manager_path, 'r') as f:
    content = f.read()

# Create backup
backup_path = db_manager_path + ".backup"
print(f"Creating backup at {backup_path}...")
with open(backup_path, 'w') as f:
    f.write(content)

# Check if already has text import
has_text_import = "from sqlalchemy import text" in content or "sqlalchemy import text" in content

if not has_text_import:
    print("Adding 'from sqlalchemy import text' import...")
    # Find the sqlalchemy.orm import line and add text import after it
    lines = content.split('\n')
    new_lines = []
    import_added = False
    
    for line in lines:
        new_lines.append(line)
        if not import_added and line.startswith('from sqlalchemy.orm import'):
            new_lines.append('from sqlalchemy import text')
            import_added = True
    
    content = '\n'.join(new_lines)
else:
    print("✓ Already has text import")

# Fix the check_database_health method
print("Patching check_database_health() method...")

# Pattern 1: session.execute("SELECT 1")
if 'session.execute("SELECT 1")' in content:
    content = content.replace(
        'session.execute("SELECT 1")',
        'session.execute(text("SELECT 1"))'
    )
    print("✓ Fixed: session.execute(\"SELECT 1\") → session.execute(text(\"SELECT 1\"))")

# Pattern 2: session.execute('SELECT 1')
if "session.execute('SELECT 1')" in content:
    content = content.replace(
        "session.execute('SELECT 1')",
        "session.execute(text('SELECT 1'))"
    )
    print("✓ Fixed: session.execute('SELECT 1') → session.execute(text('SELECT 1'))")

# Check for other potential issues
other_executes = []
lines = content.split('\n')
for i, line in enumerate(lines, 1):
    if 'execute("' in line and 'text(' not in line and 'session.execute' in line:
        other_executes.append((i, line.strip()))
    if "execute('" in line and 'text(' not in line and 'session.execute' in line:
        other_executes.append((i, line.strip()))

if other_executes:
    print("\n⚠️  Warning: Found other potential execute() calls that may need text():")
    for line_num, line in other_executes:
        print(f"   Line {line_num}: {line}")
    print("   Please review these manually if you see text() errors")

# Write the patched file
print(f"\nWriting patched file to {db_manager_path}...")
with open(db_manager_path, 'w') as f:
    f.write(content)

print()
print("=" * 80)
print("PATCH COMPLETE")
print("=" * 80)
print()
print(f"✅ Patched {db_manager_path}")
print(f"✅ Backup saved to {backup_path}")
print()
print("Next steps:")
print("1. Restart your HealingAgent:")
print("   python agents/healing_agent/main.py")
print()
print("2. You should now see:")
print("   ✅ Database connection successful")
print("   ✅ Database health check passed")
print("   (NO 'DEGRADED mode' warning)")
print()