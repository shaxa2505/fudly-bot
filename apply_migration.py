#!/usr/bin/env python3
"""
Apply database migration on Railway production.
This script should be run with: railway run python apply_migration.py
"""
import subprocess
import sys
from datetime import datetime

def run_command(cmd, description):
    """Run a shell command and return its output."""
    print(f"\n{'='*60}")
    print(f"🔄 {description}")
    print(f"{'='*60}")
    print(f"Command: {cmd}")
    
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    
    return result.returncode == 0, result.stdout, result.stderr

def main():
    print("""
╔══════════════════════════════════════════════════════════════╗
║     UNIFIED OFFERS SCHEMA MIGRATION - RAILWAY DEPLOYMENT     ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"backup_before_migration_{timestamp}.sql"
    
    # Step 1: Check Alembic version
    print("\n📋 Step 1: Checking current Alembic version...")
    success, stdout, stderr = run_command("alembic current", "Check current migration")
    
    if not success:
        print("⚠️  Could not check current version. This might be the first migration.")
    else:
        print(f"✅ Current version checked")
    
    # Step 2: Create backup (optional, as Railway has automatic backups)
    print("\n💾 Step 2: Creating database backup...")
    print("ℹ️  Railway has automatic backups, but you can create manual backup via Railway dashboard")
    print("   Go to: Railway Dashboard → Postgres → Backups → Create Backup")
    input("   Press Enter when backup is created (or skip with Enter)...")
    
    # Step 3: Show migration plan
    print("\n📝 Step 3: Showing migration SQL (dry-run)...")
    success, stdout, stderr = run_command(
        "alembic upgrade 20251217_003 --sql",
        "Generate migration SQL"
    )
    
    if not success:
        print("❌ Failed to generate migration SQL")
        return False
    
    print("\n" + "="*60)
    print("⚠️  REVIEW THE SQL ABOVE!")
    print("="*60)
    response = input("\n❓ Apply this migration? (yes/no): ").lower().strip()
    
    if response not in ["yes", "y"]:
        print("❌ Migration cancelled by user")
        return False
    
    # Step 4: Apply migration
    print("\n🚀 Step 4: Applying migration...")
    success, stdout, stderr = run_command(
        "alembic upgrade head",
        "Apply migration to database"
    )
    
    if not success:
        print("\n❌ MIGRATION FAILED!")
        print("\n🔙 To rollback, run:")
        print("   railway run alembic downgrade -1")
        return False
    
    print("\n✅ MIGRATION APPLIED SUCCESSFULLY!")
    
    # Step 5: Verify
    print("\n🔍 Step 5: Verifying migration...")
    success, stdout, stderr = run_command(
        "alembic current",
        "Check new migration version"
    )
    
    if success and "20251217_003" in stdout:
        print("\n" + "="*60)
        print("🎉 MIGRATION COMPLETE!")
        print("="*60)
        print("\n✅ Database schema updated:")
        print("   - available_from/until: VARCHAR → TIME")
        print("   - expiry_date: VARCHAR → DATE")
        print("   - prices: FLOAT → INTEGER (kopeks)")
        print("   - CHECK constraints added")
        print("\n📋 Next steps:")
        print("   1. Test creating offers via bot")
        print("   2. Test creating offers via Partner Panel")
        print("   3. Test cross-system compatibility")
        print("\n💡 Rollback if needed:")
        print("   railway run python apply_migration.py --rollback")
        return True
    else:
        print("\n⚠️  Migration applied but verification unclear")
        return False

def rollback():
    """Rollback the last migration."""
    print("""
╔══════════════════════════════════════════════════════════════╗
║                    ROLLBACK MIGRATION                        ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    response = input("\n⚠️  Are you sure you want to rollback? (yes/no): ").lower().strip()
    
    if response not in ["yes", "y"]:
        print("❌ Rollback cancelled")
        return
    
    print("\n🔙 Rolling back migration...")
    success, stdout, stderr = run_command(
        "alembic downgrade -1",
        "Rollback last migration"
    )
    
    if success:
        print("\n✅ Rollback successful!")
    else:
        print("\n❌ Rollback failed!")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--rollback":
        rollback()
    else:
        success = main()
        sys.exit(0 if success else 1)
