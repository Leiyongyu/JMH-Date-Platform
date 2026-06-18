CREATE TABLE IF NOT EXISTS sys_user_column_config (
  id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  user_id BIGINT NOT NULL COMMENT '用户ID',
  user_name VARCHAR(64) DEFAULT NULL COMMENT '用户账号',
  page_key VARCHAR(100) NOT NULL COMMENT '页面标识',
  config_json TEXT NOT NULL COMMENT '列配置JSON',
  create_by VARCHAR(64) DEFAULT '' COMMENT '创建者',
  create_time DATETIME DEFAULT NULL COMMENT '创建时间',
  update_by VARCHAR(64) DEFAULT '' COMMENT '更新者',
  update_time DATETIME DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_user_page (user_id, page_key),
  KEY idx_page_key (page_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户列配置表';
