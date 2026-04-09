import sys
import os
import time
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent))

def verify_integration():
    print("🚀 Starting Evolution API Integration Verification...")
    
    # 1. Check Configuration
    print("\n--- 1. Configuration Check ---")
    try:
        from app.core.evolution_config import evolution_settings
        print(f"✅ Config Loaded: URL={evolution_settings.API_URL}")
        print(f"✅ Config Loaded: KEY={evolution_settings.GLOBAL_API_KEY[:5]}...{evolution_settings.GLOBAL_API_KEY[-5:]}")
    except Exception as e:
        print(f"❌ Config Error: {e}")
        return

    # 2. Check API Client
    print("\n--- 2. API Connectivity Check ---")
    try:
        from app.services.evolution_api_client import EvolutionAPIClient
        client = EvolutionAPIClient(evolution_settings.API_URL, evolution_settings.GLOBAL_API_KEY)
        
        print(f"Testing connection to {evolution_settings.API_URL}...")
        instances = client.fetch_instances()
        print(f"✅ API Reachable! Found {len(instances)} instances.")
    except Exception as e:
        print(f"❌ API Connection Failed: {e}")
        print("   TIP: Is your Docker container running on port 8082?")

    # 3. Check Service Layer
    print("\n--- 3. Service Layer Check ---")
    try:
        from app.services.whatsapp_service import whatsapp_service
        print("✅ Service Layer Initialized.")
    except Exception as e:
        print(f"❌ Service Layer Error: {e}")

    # 4. Check UI Components
    print("\n--- 4. UI Components Check ---")
    try:
        from app.qt_ui.whatsapp_widget import WhatsAppWidget
        from app.qt_ui.whatsapp_campaign_widget import WhatsAppCampaignWidget
        print("✅ WhatsApp UI components found.")
    except Exception as e:
        print(f"❌ UI Component Error: {e}")

    # 5. Check Excel Service
    print("\n--- 5. Excel Service Check ---")
    try:
        from app.services.excel_service import excel_service
        import openpyxl  # noqa: F401
        print("✅ Excel service and openpyxl loaded.")
    except Exception as e:
        print(f"❌ Excel Service Error: {e}")

    print("\n🎉 Verification Complete! If 1-5 are green, your campaign backend is ready.")
    print("   To see the UI, open the application and go to Settings > SMS & WhatsApp.")

if __name__ == "__main__":
    verify_integration()
