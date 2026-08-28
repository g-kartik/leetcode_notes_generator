-- Adds id/title/difficulty to pending_cache, so a solved-but-not-yet-fetched
-- slug can be labeled consistently in the CLI picker (offline included)
-- without needing a full `problems` table record yet. Populated by
-- LeetCodeSyncManager.sync_pending_cache() from the same bulk
-- solved-questions response that already refreshes the cache's slug list —
-- see PendingCacheStore.refresh_pending_cache's `meta` argument.
ALTER TABLE pending_cache ADD COLUMN id INTEGER;
ALTER TABLE pending_cache ADD COLUMN title TEXT;
ALTER TABLE pending_cache ADD COLUMN difficulty TEXT;
