import os
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(backend_dir))

from app.core.config import settings

def main():
    url = settings.active_supabase_url
    key = settings.active_supabase_key

    print("=" * 60)
    print("SUPABASE INJECTION CHECK")
    print("=" * 60)
    print(f"Supabase URL: {url}")
    print(f"Supabase Key: {key[:8]}... (len={len(key)})" if key else "Supabase Key: None")

    if not url or not key:
        print("[ERROR] Credentials missing.")
        return

    from supabase import create_client
    print("\nInitializing Supabase client...")
    client = create_client(url, key)

    test_chat = {
        "id": "chat_test_injection_001",
        "user_id": "test_user_admin",
        "user_email": "admin@example.com",
        "title": "Test Supabase Injection",
        "messages": [
            {
                "id": "msg_001",
                "role": "user",
                "text": "Hello, is Supabase database storing this chat?",
                "timestamp": "12:00 PM"
            },
            {
                "id": "msg_002",
                "role": "assistant",
                "text": "Yes, successfully connected and persisted to Supabase!",
                "timestamp": "12:00 PM"
            }
        ]
    }

    print("\nAttempting upsert to 'user_chats' table...")
    try:
        res = client.table("user_chats").upsert(test_chat).execute()
        print("\n[SUCCESS] Response from Supabase:")
        print(res.data)
    except Exception as e:
        print(f"\n[ERROR] Supabase upsert failed: {type(e).__name__}: {e}")

if __name__ == "__main__":
    main()
