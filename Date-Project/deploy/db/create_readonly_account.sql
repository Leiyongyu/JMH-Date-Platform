-- ops_ro: read-only account for ops verification. SELECT + SHOW VIEW only, no DDL, no writes.
-- Replace <OPS_RO_PASSWORD> before running. Steps and rationale: README_ops_ro.md (same folder).
--
-- This file is deliberately ASCII-only. Windows PowerShell 5.1 decodes files with the ANSI
-- codepage (936 here), so a UTF-8 full-width character at end of line can swallow the following
-- line break and merge two lines into one. That silently merged a comment with the Date-Project
-- GRANT below, and a comment-stripping filter then dropped the GRANT without any error.
-- Keep this file ASCII and the failure mode cannot come back.

CREATE USER IF NOT EXISTS 'ops_ro'@'localhost' IDENTIFIED BY '<OPS_RO_PASSWORD>';
CREATE USER IF NOT EXISTS 'ops_ro'@'127.0.0.1' IDENTIFIED BY '<OPS_RO_PASSWORD>';

GRANT SELECT, SHOW VIEW ON `Date-Project`.*      TO 'ops_ro'@'localhost', 'ops_ro'@'127.0.0.1';
GRANT SELECT, SHOW VIEW ON `jmh_data_platform`.* TO 'ops_ro'@'localhost', 'ops_ro'@'127.0.0.1';
GRANT SELECT, SHOW VIEW ON `jmh_ai_agent`.*      TO 'ops_ro'@'localhost', 'ops_ro'@'127.0.0.1';

FLUSH PRIVILEGES;
