CREATE TABLE IF NOT EXISTS image_sop_draft (
    id CHAR(32) NOT NULL COMMENT 'SOP草稿UUID（无连字符）',
    owner_user_id BIGINT NOT NULL DEFAULT 0 COMMENT 'ERP用户ID，草稿数据隔离依据',
    owner_username VARCHAR(64) NOT NULL DEFAULT '' COMMENT 'ERP登录账号，便于审计',
    sku VARCHAR(200) NOT NULL COMMENT 'Amazon MSKU或eBay业务SKU',
    source_mode VARCHAR(20) NOT NULL DEFAULT 'amazon' COMMENT '数据来源：amazon或ebay',
    status VARCHAR(30) NOT NULL DEFAULT 'completed' COMMENT '草稿状态',
    store_sid BIGINT NULL COMMENT '领星店铺SID',
    data_json JSON NOT NULL COMMENT '完整SOP草稿、图片清单及生成结果',
    request_id VARCHAR(128) NULL COMMENT '跨ERP与Python的请求追踪ID',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间',
    expires_at DATETIME(3) NOT NULL COMMENT '草稿过期时间，默认7天',
    PRIMARY KEY (id),
    KEY idx_image_sop_draft_sku (sku),
    KEY idx_image_sop_draft_owner (owner_user_id, created_at),
    KEY idx_image_sop_draft_expires (expires_at),
    KEY idx_image_sop_draft_updated (updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='图片SOP生成草稿；复杂生成结果使用JSON保存，大文件仅保存路径';

CREATE TABLE IF NOT EXISTS image_sop_ai_profile_cache (
    cache_key VARCHAR(255) NOT NULL COMMENT 'Amazon为SID+SKU，eBay为商品版本键',
    listing_version VARCHAR(255) NOT NULL COMMENT 'Listing更新时间或内容哈希',
    data_json JSON NOT NULL COMMENT 'AI产品分析缓存',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间',
    expires_at DATETIME(3) NOT NULL COMMENT '缓存过期时间',
    PRIMARY KEY (cache_key),
    KEY idx_image_sop_ai_cache_expires (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='图片SOP的AI产品分析缓存';
