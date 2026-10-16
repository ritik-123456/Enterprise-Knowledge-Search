import os
import json
import time
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from app.core.config import settings

logger = logging.getLogger(__name__)

# Fallback local file storage path if Supabase is unavailable or table not yet initialized
_STORAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_FALLBACK_FILE = os.path.join(_STORAGE_DIR, "chat_storage.json")


class ChatHistoryService:
    """
    Enterprise Chat Storing and Retrieval Service.
    Seamlessly integrates with Supabase for persistent cloud chat storage with
    local fallback caching so chat search and history are always responsive and reliable.
    """

    def __init__(self):
        self._supabase_client = None
        self._init_supabase()

    def _init_supabase(self):
        url = settings.active_supabase_url
        key = settings.active_supabase_key

        if url and key:
            try:
                from supabase import create_client
                self._supabase_client = create_client(url, key)
                logger.info("Supabase client initialized successfully for chat storage.")
            except Exception as e:
                logger.warning(f"Could not initialize Supabase client: {e}")
                self._supabase_client = None
        else:
            logger.info("Supabase credentials not fully specified yet; using secure local storage.")

    @property
    def is_supabase_connected(self) -> bool:
        if self._supabase_client is None:
            self._init_supabase()
        return self._supabase_client is not None

    def _read_local_store(self) -> List[Dict[str, Any]]:
        if not os.path.exists(_FALLBACK_FILE):
            return []
        try:
            with open(_FALLBACK_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception as e:
            logger.warning(f"Error reading local chat store: {e}")
            return []

    def _write_local_store(self, chats: List[Dict[str, Any]]):
        try:
            with open(_FALLBACK_FILE, "w", encoding="utf-8") as f:
                json.dump(chats, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error writing to local chat store: {e}")

    def save_chat(self, chat_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Saves or updates a chat session in Supabase (or fallback storage).
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        chat_id = chat_payload.get("id") or f"chat_{int(time.time()*1000)}"
        user_id = chat_payload.get("user_id", "guest")
        user_email = chat_payload.get("user_email")
        title = chat_payload.get("title") or "New Conversation"
        messages = chat_payload.get("messages", [])
        created_at = chat_payload.get("created_at") or now_iso
        updated_at = now_iso

        record = {
            "id": chat_id,
            "user_id": str(user_id),
            "user_email": user_email,
            "title": title[:200],
            "messages": messages,
            "created_at": created_at,
            "updated_at": updated_at
        }

        # 1. Try Supabase cloud persistence
        saved_to_supabase = False
        if self.is_supabase_connected:
            try:
                res = self._supabase_client.table("user_chats").upsert(record).execute()
                if res.data:
                    saved_to_supabase = True
                    logger.debug(f"Chat {chat_id} persisted to Supabase.")
            except Exception as e:
                logger.warning(
                    f"Supabase upsert failed (ensure 'user_chats' table exists in Supabase): {e}"
                )

        # 2. Always maintain local store cache for lightning-fast retrieval
        local_chats = self._read_local_store()
        existing_idx = next((i for i, c in enumerate(local_chats) if c.get("id") == chat_id), None)
        if existing_idx is not None:
            local_chats[existing_idx] = record
        else:
            local_chats.insert(0, record)
        self._write_local_store(local_chats)

        record["saved_to_cloud"] = saved_to_supabase
        return record

    def get_user_chats(
        self,
        user_id: str,
        user_email: Optional[str] = None,
        search_query: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieves user chats ordered from most recent to oldest.
        Filters strictly by the verified user_id.
        """
        if not user_id or not isinstance(user_id, str) or not user_id.strip():
            return []

        results = []

        # Try fetching from Supabase first
        if self.is_supabase_connected:
            try:
                query = self._supabase_client.table("user_chats").select("*").eq("user_id", str(user_id)).order("updated_at", desc=True)
                resp = query.execute()
                if resp.data is not None:
                    results = resp.data
            except Exception as e:
                logger.warning(f"Supabase select failed; falling back to local cache: {e}")
                results = []

        # If Supabase returned nothing or errored, use local store
        if not results:
            local_chats = self._read_local_store()
            results = [c for c in local_chats if str(c.get("user_id")) == str(user_id)]

        # Sort by updated_at descending
        results.sort(key=lambda x: x.get("updated_at", ""), reverse=True)

        # Apply search query filtering if provided
        if search_query and search_query.strip():
            sq = search_query.strip().lower()
            filtered = []
            for c in results:
                title_match = sq in (c.get("title") or "").lower()
                # Check message text contents
                msg_match = False
                for m in c.get("messages", []):
                    if isinstance(m, dict) and sq in (m.get("text") or "").lower():
                        msg_match = True
                        break
                    # Also check assistant answer text inside data
                    if isinstance(m, dict) and isinstance(m.get("data"), dict):
                        answer_text = m.get("data", {}).get("answer") or ""
                        if sq in answer_text.lower():
                            msg_match = True
                            break
                if title_match or msg_match:
                    filtered.append(c)
            return filtered

        return results

    def get_chat_by_id(self, chat_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Retrieves full chat conversation thread by ID.
        If user_id is provided, enforces that the conversation belongs to that user.
        """
        chat = None
        if self.is_supabase_connected:
            try:
                q = self._supabase_client.table("user_chats").select("*").eq("id", chat_id)
                if user_id:
                    q = q.eq("user_id", str(user_id))
                resp = q.execute()
                if resp.data and len(resp.data) > 0:
                    chat = resp.data[0]
            except Exception as e:
                logger.warning(f"Supabase fetch by ID failed: {e}")

        if not chat:
            local_chats = self._read_local_store()
            chat = next((c for c in local_chats if c.get("id") == chat_id), None)

        if chat and user_id:
            if str(chat.get("user_id")) != str(user_id):
                return None

        return chat

    def delete_chat(self, chat_id: str, user_id: Optional[str] = None) -> bool:
        """
        Deletes a chat conversation ensuring caller ownership.
        """
        success = False
        if self.is_supabase_connected:
            try:
                q = self._supabase_client.table("user_chats").delete().eq("id", chat_id)
                if user_id:
                    q = q.eq("user_id", str(user_id))
                q.execute()
                success = True
            except Exception as e:
                logger.warning(f"Supabase delete failed: {e}")

        local_chats = self._read_local_store()
        filtered = [
            c for c in local_chats
            if not (c.get("id") == chat_id and (not user_id or str(c.get("user_id")) == str(user_id)))
        ]
        if len(filtered) != len(local_chats):
            self._write_local_store(filtered)
            success = True

        return success

    def clear_user_chats(self, user_id: str) -> bool:
        """
        Deletes all chats belonging to a user.
        """
        success = False
        if self.is_supabase_connected:
            try:
                self._supabase_client.table("user_chats").delete().eq("user_id", str(user_id)).execute()
                success = True
            except Exception as e:
                logger.warning(f"Supabase clear user chats failed: {e}")

        local_chats = self._read_local_store()
        filtered = [c for c in local_chats if str(c.get("user_id")) != str(user_id)]
        self._write_local_store(filtered)
        return True


# Global singleton
chat_service = ChatHistoryService()
