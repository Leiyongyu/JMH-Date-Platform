-- Only new tables and a task registration. No credentials, emails or API response bodies are stored.
CREATE TABLE IF NOT EXISTS ebay_token_health_run (
 run_id CHAR(36) NOT NULL COMMENT '健康检查批次标识',
 checked_at DATETIME NOT NULL COMMENT '北京时间检查时间',
 account_count INT UNSIGNED NOT NULL COMMENT '实际检查的有密钥店铺数',
 report_json JSON NOT NULL COMMENT '脱敏汇总和逐店健康状态，不含密钥或邮箱',
 PRIMARY KEY (run_id), KEY idx_checked_at (checked_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='eBay月末密钥健康检查历史报告';
CREATE TABLE IF NOT EXISTS ebay_token_health_state (
 browser_id VARCHAR(128) NOT NULL COMMENT '账号文件中的稳定店铺标识',
 seller_account VARCHAR(200) NOT NULL COMMENT '已核对身份的eBay用户名',
 listing_count BIGINT UNSIGNED NOT NULL COMMENT '最近一次成功核对身份并取得的在售数量，可疑数量仍为有效观测',
 checked_at DATETIME NOT NULL COMMENT '北京时间观测时间',
 run_id CHAR(36) NOT NULL COMMENT '对应健康检查批次',
 PRIMARY KEY (browser_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='eBay店铺健康检查在售数量比较基线，不含密钥';
INSERT INTO scheduler_task (task_code,task_name,cron_expression,enabled,description)
VALUES ('ebay_token_health_check','eBay店铺密钥月末健康检查','0 0 9 L * ?',1,
 'Java Quartz每月最后一天北京时间09:00调用；OAuth、Trading身份、在售数量检查；只读Excel；完整报告由Java发企微群。')
ON DUPLICATE KEY UPDATE task_name=VALUES(task_name),description=VALUES(description);
