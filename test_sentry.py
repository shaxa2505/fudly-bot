"""Test script to verify Sentry integration is working."""
import os
from app.core.sentry_integration import init_sentry, capture_message, capture_exception

# Initialize Sentry
print("🔧 Initializing Sentry...")
sentry_enabled = init_sentry(
    environment="production",
    enable_logging=True,
    sample_rate=1.0,
    traces_sample_rate=0.1
)

if sentry_enabled:
    print("✅ Sentry initialized successfully!")
    print(f"   DSN: {os.getenv('SENTRY_DSN')[:30]}...")
    
    # Test 1: Send a test message
    print("\n📤 Sending test message to Sentry...")
    capture_message("Test message from Fudly Bot", level="info")
    print("✅ Message sent!")
    
    # Test 2: Send a test error
    print("\n📤 Sending test error to Sentry...")
    try:
        raise ValueError("This is a test error - please ignore")
    except Exception as e:
        capture_exception(e, test_data={"source": "test_script"})
        print("✅ Error sent!")
    
    print("\n🎉 Sentry integration is working!")
    print("👉 Check your Sentry dashboard: https://sentry.io/")
    print("   You should see 1 message and 1 error event")
    
else:
    print("❌ Sentry not enabled")
    print("   Make sure SENTRY_DSN environment variable is set")
