-- =====================================================================
-- Copy existing AI assistant chat history from the business DB (Date-Project)
-- into the dedicated AI agent DB (jmh_ai_agent). One-off, run manually.
--
-- Order (copy MUST happen before the new Python code serves any chat,
-- otherwise new rows may take ids that collide with the copied ones):
--   1. Stop the Python service.
--   2. python -m backend.cli db-migrate --target agent   (creates DB + tables)
--   3. Run this file with the migrator account, check the counts at the end.
--   4. Start the Python service with the new code.
-- Old tables in Date-Project are left untouched (keep them as backup).
-- The whole copy is one transaction: any id conflict aborts with an error.
-- =====================================================================

START TRANSACTION;

INSERT INTO `jmh_ai_agent`.`ai_conversations`
    (id, conversation_uuid, erp_user_id, erp_username, title, message_count,
     last_message_preview, created_at, updated_at)
SELECT id, conversation_uuid, erp_user_id, erp_username, title, message_count,
       last_message_preview, created_at, updated_at
FROM `Date-Project`.`ai_conversations`;

INSERT INTO `jmh_ai_agent`.`ai_messages`
    (id, conversation_id, role, content, is_error, request_id, model,
     prompt_tokens, completion_tokens, total_tokens, created_at)
SELECT id, conversation_id, role, content, is_error, request_id, model,
       prompt_tokens, completion_tokens, total_tokens, created_at
FROM `Date-Project`.`ai_messages`;

COMMIT;

-- Keep AUTO_INCREMENT above the copied ids (InnoDB does this automatically
-- after explicit-id inserts; the SELECT below is only for verification).
SELECT 'ai_conversations' AS table_name,
       (SELECT COUNT(*) FROM `Date-Project`.`ai_conversations`) AS source_rows,
       (SELECT COUNT(*) FROM `jmh_ai_agent`.`ai_conversations`) AS target_rows
UNION ALL SELECT 'ai_messages',
       (SELECT COUNT(*) FROM `Date-Project`.`ai_messages`),
       (SELECT COUNT(*) FROM `jmh_ai_agent`.`ai_messages`);
