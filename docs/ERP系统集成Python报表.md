# Python + ERP 数据仓库、数据分析与可视化建设方案

## 1. 背景与目标

当前 ERP 系统已经承担了业务数据录入、接口同步、库存、补货、报关、权限、菜单、用户管理等核心能力。后续如果继续把所有报表计算、数据清洗、可视化分析都塞进 Java ERP 中，会逐渐出现以下问题：

- 报表逻辑和业务逻辑混在一起，代码越来越难维护。
- 数据来源越来越多，包括 ERP 业务库、领星接口、谷仓接口、飞书、固定 Excel 文件、手工上传文件。
- 报表计算通常需要大量聚合、清洗、历史快照、趋势分析，用 Java 业务接口直接计算会比较重。
- 后续如果要做销量预测、库存预警、利润分析、AI 数据解释，用 Python 生态更合适。

因此建议建设一个独立的 Python 数据分析服务，并配套一个独立的报表数据库。

最终目标：

```text
ERP 系统负责业务
Python 负责数据仓库、ETL、数据分析、报表接口
报表数据库负责存储清洗后的分析数据
ERP 前端负责展示报表页面
```

## 2. 总体架构

推荐整体架构如下：

```text
┌──────────────────────────────────────────────────────────┐
│                       数据源                              │
├──────────────────────────────────────────────────────────┤
│  1. ERP 业务库 MySQL                                      │
│  2. 领星接口                                               │
│  3. 谷仓接口                                               │
│  4. 飞书接口                                               │
│  5. 固定文件夹 Excel / CSV                                │
│  6. ERP 页面上传文件                                       │
└──────────────────────────────────────────────────────────┘
                          │
                          │ Python ETL 拉取 / 读取 / 清洗
                          ↓
┌──────────────────────────────────────────────────────────┐
│                 报表数据库 jmh_report                     │
├──────────────────────────────────────────────────────────┤
│  stg 原始层                                                │
│  ods 清洗标准层                                            │
│  dim 维度层                                                │
│  dwd 明细事实层                                            │
│  dws 汇总服务层                                            │
│  ads 报表应用层                                            │
└──────────────────────────────────────────────────────────┘
                          │
                          │ FastAPI 提供接口
                          ↓
┌──────────────────────────────────────────────────────────┐
│                   Python 报表服务                         │
├──────────────────────────────────────────────────────────┤
│  1. 报表查询 API                                           │
│  2. 图表数据 API                                           │
│  3. 明细导出 API                                           │
│  4. 指标解释 API                                           │
│  5. 任务状态 API                                           │
└──────────────────────────────────────────────────────────┘
                          │
                          │ ERP 后端转发或前端调用
                          ↓
┌──────────────────────────────────────────────────────────┐
│                    ERP 报表中心                           │
├──────────────────────────────────────────────────────────┤
│  1. 菜单权限                                               │
│  2. 页面展示                                               │
│  3. ECharts 可视化                                         │
│  4. 表格明细                                               │
│  5. Excel 导出                                             │
└──────────────────────────────────────────────────────────┘
```

## 3. 核心设计原则

### 3.1 ERP 业务库是唯一业务事实源

ERP 业务库仍然是业务数据的源头。

例如：

- 商品资料
- 库存明细
- 补货快照
- 报关商品库
- 出入库清单
- 用户、角色、菜单、权限
- 手工维护的数据

Python 报表服务不能随意反写 ERP 业务表。

建议原则：

```text
业务数据：Java ERP 写入
分析数据：Python 报表库写入
页面展示：ERP 前端展示
权限控制：ERP 控制
```

### 3.2 报表库只服务分析和展示

报表库可以存储：

- 原始接口返回数据
- Excel 原始上传数据
- 清洗后的标准数据
- 每日快照
- 聚合指标
- 报表宽表
- 可视化看板结果

报表库不应该直接替代 ERP 业务库。

### 3.3 Python 负责流程，SQL 负责计算

不要把所有逻辑写在 MySQL 存储过程里。

推荐分工：

```text
Python：
  - 调接口
  - 读 Excel
  - 文件扫描
  - 参数校验
  - 批次管理
  - 日志记录
  - 异常重试
  - 任务调度
  - 调用 SQL

SQL：
  - insert into select
  - merge/upsert
  - group by 聚合
  - join 维表
  - 去重
  - 指标计算
```

这样后期维护更清楚。

具体落地方式：

```text
Python 定时任务负责什么时候跑、跑哪一步、失败怎么处理。
SQL 文件负责具体怎么从 stg 清洗到 ods、从 ods 聚合到 dwd/dws/ads。
MySQL 只负责存储数据和执行 SQL，不使用 MySQL 自带 event scheduler 作为主调度。
```

不推荐：

```text
1. 不推荐把主 ETL 写成 MySQL 存储过程。
2. 不推荐用 MySQL event scheduler 管接口、文件、依赖和重试。
3. 不推荐把大量 SQL 直接写成 Python 字符串散落在代码里。
4. 不推荐用 Python 一行一行循环处理大批量数据库数据。
```

推荐：

```text
Python ETL 调度 + 外部 .sql 文件加工 + MySQL 批量执行。
```

一句话：

```text
Python 是总指挥，SQL 是干活的，MySQL 是仓库和执行引擎。
```

### 3.4 分层不一定分库

当前阶段建议只建一个报表库：

```sql
jmh_report
```

然后通过表名前缀区分层级：

```text
stg_
ods_
dim_
dwd_
dws_
ads_
etl_
```

不建议现在就每层一个数据库。每层一个库会增加部署、权限、备份、迁移、跨库查询成本。

## 4. 数据仓库分层设计

推荐使用轻量数仓分层：

```text
stg  原始层
ods  标准清洗层
dim  维度层
dwd  明细事实层
dws  汇总服务层
ads  应用报表层
```

### 4.1 STG 原始层

STG 层用于保存原始数据。

原则：

- 尽量保留原始字段。
- 不做复杂业务处理。
- 保留来源、批次、同步时间。
- 方便追溯接口或 Excel 原始内容。

命名规范：

```text
stg_来源_对象_raw
```

示例：

```text
stg_lingxing_listing_raw
stg_lingxing_inventory_raw
stg_lingxing_fba_shipment_raw
stg_goodcang_grn_raw
stg_feishu_approval_raw
stg_excel_sales_raw
stg_excel_customs_raw
```

建议通用字段：

```sql
id              bigint primary key auto_increment,
batch_id        varchar(64) not null,
source_type     varchar(50),
source_name     varchar(100),
source_file     varchar(500),
source_api      varchar(500),
raw_json        json,
raw_text        longtext,
sync_time       datetime,
created_time    datetime default current_timestamp
```

如果 MySQL 版本或兼容性不方便使用 JSON，可以用 `longtext` 存原始 JSON。

### 4.2 ODS 标准清洗层

ODS 层用于把不同来源的数据整理成统一格式。

原则：

- 字段名标准化。
- 数据类型标准化。
- 时间格式统一。
- 国家、店铺、仓库、平台编码统一。
- SKU、MSKU、FNSKU、仓库 SKU 映射关系统一。
- 去除明显脏数据。

命名规范：

```text
ods_对象_detail
```

示例：

```text
ods_product_listing_detail
ods_inventory_detail
ods_sales_order_detail
ods_purchase_order_detail
ods_fba_shipment_box_detail
ods_customs_inventory_detail
```

ODS 层可以来自：

- STG 原始层清洗。
- ERP 业务库同步。
- Excel 文件解析。

### 4.3 DIM 维度层

DIM 层用于存储通用维度和映射。

示例：

```text
dim_date
dim_product
dim_shop
dim_country
dim_warehouse
dim_platform
dim_currency
dim_sku_mapping
```

`dim_country` 示例：

```sql
country_code     country_name_cn
US               美国
UK               英国
GB               英国
DE               德国
FR               法国
ES               西班牙
IT               意大利
PL               波兰
CA               加拿大
MX               墨西哥
```

`dim_shop` 示例：

```sql
shop_id
platform
shop_name
shop_prefix
country_code
country_name
default_warehouse
enabled
```

例如店铺 `US1-刘子洋-US`：

```text
shop_prefix = US1
country_code = US
country_name = 美国
default_warehouse = CTUAMZ-US1中转仓
```

### 4.4 DWD 明细事实层

DWD 层用于存储可以直接分析的业务明细事实。

特点：

- 粒度清楚。
- 保留明细。
- 适合后续聚合。

示例：

```text
dwd_amz_listing_detail
dwd_amz_inventory_snapshot
dwd_ebay_inventory_snapshot
dwd_sales_order_detail
dwd_purchase_order_detail
dwd_customs_product_detail
dwd_fba_box_detail
```

例如库存快照：

```text
一条记录 = 某一天 + 平台 + 店铺 + 仓库 + SKU 的库存状态
```

### 4.5 DWS 汇总服务层

DWS 层用于聚合常用分析场景。

特点：

- 面向主题。
- 面向查询效率。
- 可以按天、周、月汇总。

示例：

```text
dws_sales_sku_daily
dws_sales_shop_daily
dws_inventory_sku_daily
dws_replenishment_sku_daily
dws_customs_country_monthly
dws_profit_sku_monthly
```

例如：

```text
dws_sales_sku_daily
  report_date
  platform
  shop_name
  sku
  sales_7d
  sales_15d
  sales_30d
  return_qty
  gross_profit
  roi
```

### 4.6 ADS 应用报表层

ADS 层用于直接给页面使用。

特点：

- 一个页面尽量对应一张 ADS 表或一个接口。
- 前端不做复杂计算。
- 接口查询简单稳定。

示例：

```text
ads_amz_replenishment_dashboard
ads_ebay_replenishment_dashboard
ads_inventory_warning_dashboard
ads_customs_export_dashboard
ads_sales_profit_dashboard
ads_operation_overview_dashboard
```

ERP 页面调用 Python 接口时，优先查 ADS 层。

## 5. 推荐数据库结构

### 5.1 单库分层

建议创建一个报表库：

```sql
CREATE DATABASE jmh_report DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
```

表结构示例：

```text
jmh_report
├─ etl_job
├─ etl_job_log
├─ etl_batch
├─ etl_file_log
├─ etl_api_cursor
├─ etl_error_log
├─ stg_lingxing_listing_raw
├─ stg_excel_sales_raw
├─ ods_product_listing_detail
├─ ods_inventory_detail
├─ dim_shop
├─ dim_country
├─ dwd_sales_detail
├─ dws_sales_sku_daily
└─ ads_sales_dashboard
```

### 5.2 为什么不建议每层一个库

不推荐现在这样做：

```text
jmh_report_stg
jmh_report_ods
jmh_report_dwd
jmh_report_dws
jmh_report_ads
```

原因：

- 跨库查询更复杂。
- 权限配置更复杂。
- 本地和部署机同步更麻烦。
- Python 数据库连接配置更多。
- 备份恢复复杂。
- 开发阶段没有明显收益。

### 5.3 什么时候再拆库

后续出现以下情况，再考虑拆：

- STG 原始数据量非常大。
- ADS 查询和 ETL 写入互相影响。
- 报表查询压力明显影响 MySQL。
- 需要把报表查询迁移到 ClickHouse、Doris、StarRocks 等分析库。
- 不同层需要严格权限隔离。
- 历史冷数据需要单独归档。

## 6. ETL 任务设计

### 6.1 ETL 总流程

标准流程：

```text
1. 创建 batch_id
2. 检查数据源
3. 拉取接口 / 读取文件
4. 写入 STG
5. 清洗到 ODS
6. 生成 DIM
7. 生成 DWD
8. 汇总到 DWS
9. 生成 ADS
10. 记录任务日志
11. 异常告警
```

层级加工执行方式：

```text
stg -> ods
ods -> dim
ods -> dwd
dwd -> dws
dws -> ads
```

这些加工流程都建议由 Python ETL 定时任务统一调度。

执行方式不是把每条数据拿到 Python 里循环清洗，而是：

```text
1. Python 创建 batch_id。
2. Python 检查上游数据是否存在。
3. Python 读取对应的 .sql 文件。
4. Python 替换 SQL 参数，例如 :batch_id、:biz_date、:start_date、:end_date。
5. Python 调用 MySQL 执行批量 SQL。
6. MySQL 执行 insert into ... select ...、group by、join、upsert。
7. Python 记录处理条数、耗时、成功/失败状态。
8. 失败时 Python 记录错误日志，并按配置决定是否重试。
```

示例：

```text
build_ods_product_listing.py
  -> 读取 sql/ods/build_ods_product_listing.sql
  -> 执行 SQL
  -> 写入 etl_job_log

build_dws_sales_sku_daily.py
  -> 读取 sql/dws/build_dws_sales_sku_daily.sql
  -> 执行 SQL
  -> 写入 etl_job_log
```

这样可以让 ETL 具备：

```text
可版本管理
可手动重跑
可记录日志
可控制依赖
可失败重试
可迁移到 Airflow / DolphinScheduler
```

### 6.2 文件类任务流程

用于固定文件夹 Excel。

```text
1. 扫描固定文件夹
2. 判断是否有新文件
3. 根据文件名、大小、hash 判断是否处理过
4. 没有新文件则跳过
5. 有新文件则读取
6. 解析 sheet
7. 写入 stg_excel_xxx_raw
8. 清洗到 ods
9. 移动文件到 processed 文件夹
10. 失败文件移动到 failed 文件夹
11. 写入 etl_file_log
```

建议目录：

```text
D:/JMH_Report_Files/
├─ input/
│  ├─ sales/
│  ├─ customs/
│  └─ inventory/
├─ processed/
├─ failed/
└─ archive/
```

### 6.3 接口类任务流程

用于领星、谷仓、飞书等接口。

```text
1. 读取 etl_api_cursor
2. 生成请求参数
3. 调接口
4. 分页拉取
5. 接口重试
6. 写入 STG
7. 更新 cursor
8. 清洗到 ODS
9. 生成下游表
10. 写入任务日志
```

接口任务必须支持：

- 分页
- 限流
- 重试
- 超时
- token 刷新
- 失败记录
- 增量游标
- 全量初始化

### 6.4 ERP 业务库同步任务

Python 可以只读 ERP 业务库，把 ERP 中需要分析的数据同步到报表库。

例如：

```text
customs_inventory_list
customs_products_list
amz_product_listing
amz_fba_shipment_box
ebay_replenishment_snapshot
warehouse_inventory_detail
purchase_order
shop_list
```

同步方式：

```text
小表：全量覆盖
大表：按 update_time 增量同步
快照表：按 report_date 或 batch_id 同步
```

## 7. ETL 元数据表设计

### 7.1 etl_job 任务定义表

```sql
CREATE TABLE etl_job (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  job_code VARCHAR(100) NOT NULL UNIQUE COMMENT '任务编码',
  job_name VARCHAR(200) NOT NULL COMMENT '任务名称',
  job_type VARCHAR(50) NOT NULL COMMENT 'api/file/sql/build',
  cron_expr VARCHAR(100) NULL COMMENT 'cron 表达式',
  enabled TINYINT DEFAULT 1 COMMENT '是否启用',
  timeout_seconds INT DEFAULT 3600 COMMENT '超时时间',
  max_retry INT DEFAULT 3 COMMENT '最大重试次数',
  remark VARCHAR(500),
  created_time DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

### 7.2 etl_job_log 任务日志表

```sql
CREATE TABLE etl_job_log (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  job_code VARCHAR(100) NOT NULL,
  batch_id VARCHAR(64) NOT NULL,
  status VARCHAR(20) NOT NULL COMMENT 'running/success/failed/skipped',
  start_time DATETIME NOT NULL,
  end_time DATETIME NULL,
  duration_seconds DECIMAL(12,2) NULL,
  read_count INT DEFAULT 0,
  insert_count INT DEFAULT 0,
  update_count INT DEFAULT 0,
  delete_count INT DEFAULT 0,
  skip_count INT DEFAULT 0,
  error_count INT DEFAULT 0,
  error_message TEXT,
  created_time DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_job_time(job_code, start_time),
  INDEX idx_batch(batch_id)
);
```

### 7.3 etl_batch 批次表

```sql
CREATE TABLE etl_batch (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  batch_id VARCHAR(64) NOT NULL UNIQUE,
  batch_type VARCHAR(50),
  business_date DATE,
  status VARCHAR(20),
  start_time DATETIME,
  end_time DATETIME,
  remark VARCHAR(500),
  created_time DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 7.4 etl_file_log 文件处理日志

```sql
CREATE TABLE etl_file_log (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  file_path VARCHAR(1000) NOT NULL,
  file_name VARCHAR(500) NOT NULL,
  file_hash VARCHAR(128),
  file_size BIGINT,
  file_type VARCHAR(50),
  business_type VARCHAR(100),
  batch_id VARCHAR(64),
  status VARCHAR(20) COMMENT 'success/failed/skipped',
  message TEXT,
  processed_time DATETIME,
  created_time DATETIME DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_file_hash(file_hash),
  INDEX idx_file_name(file_name)
);
```

### 7.5 etl_api_cursor 接口游标

```sql
CREATE TABLE etl_api_cursor (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  source_code VARCHAR(100) NOT NULL,
  api_code VARCHAR(100) NOT NULL,
  cursor_key VARCHAR(100) NOT NULL,
  cursor_value VARCHAR(500),
  last_sync_time DATETIME,
  updated_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_api_cursor(source_code, api_code, cursor_key)
);
```

### 7.6 etl_error_log 错误明细

```sql
CREATE TABLE etl_error_log (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  job_code VARCHAR(100),
  batch_id VARCHAR(64),
  source_type VARCHAR(50),
  source_key VARCHAR(500),
  error_type VARCHAR(100),
  error_message TEXT,
  raw_data LONGTEXT,
  created_time DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_job_batch(job_code, batch_id)
);
```

## 8. Python 项目结构建议

建议单独创建一个 Python 项目，例如：

```text
jmh-report-service/
├─ app/
│  ├─ main.py
│  ├─ api/
│  │  ├─ health.py
│  │  ├─ reports/
│  │  │  ├─ sales.py
│  │  │  ├─ inventory.py
│  │  │  ├─ customs.py
│  │  │  └─ replenishment.py
│  │  └─ jobs.py
│  ├─ core/
│  │  ├─ config.py
│  │  ├─ security.py
│  │  ├─ logging.py
│  │  └─ exceptions.py
│  ├─ db/
│  │  ├─ mysql.py
│  │  ├─ report_db.py
│  │  └─ erp_db.py
│  ├─ etl/
│  │  ├─ scheduler.py
│  │  ├─ runner.py
│  │  ├─ context.py
│  │  ├─ jobs/
│  │  │  ├─ sync_lingxing_listing.py
│  │  │  ├─ sync_lingxing_inventory.py
│  │  │  ├─ sync_excel_sales.py
│  │  │  ├─ build_ods.py
│  │  │  ├─ build_dwd.py
│  │  │  ├─ build_dws.py
│  │  │  └─ build_ads.py
│  │  └─ sql/
│  │     ├─ ods/
│  │     ├─ dwd/
│  │     ├─ dws/
│  │     └─ ads/
│  ├─ integrations/
│  │  ├─ lingxing/
│  │  │  ├─ client.py
│  │  │  └─ auth.py
│  │  ├─ goodcang/
│  │  ├─ feishu/
│  │  └─ erp/
│  ├─ services/
│  │  ├─ report_service.py
│  │  ├─ export_service.py
│  │  └─ chart_service.py
│  └─ utils/
│     ├─ excel.py
│     ├─ date.py
│     ├─ hash.py
│     └─ retry.py
├─ scripts/
│  ├─ init_db.py
│  ├─ run_job.py
│  └─ backfill.py
├─ tests/
├─ requirements.txt
├─ .env
└─ README.md
```

## 9. Python 技术选型

### 9.1 Web 框架

推荐：

```text
FastAPI
```

原因：

- 性能好。
- 接口文档自动生成。
- 类型提示清楚。
- 适合做报表 API。
- 后续接 AI 接口也方便。

### 9.2 数据库访问

推荐：

```text
SQLAlchemy Core / SQLModel / pymysql
```

实际建议：

- 简单 SQL 和 ETL：`pymysql` 或 `mysql-connector-python`
- API 查询：SQLAlchemy Core
- 不建议早期引入太复杂 ORM

### 9.3 Excel 处理

推荐：

```text
pandas
openpyxl
```

用途：

- 读取 Excel。
- 校验 sheet。
- 清洗字段。
- 处理日期、数字、空值。

### 9.4 定时任务

前期推荐：

```text
APScheduler
```

后期任务复杂后可升级：

```text
Apache Airflow
DolphinScheduler
Prefect
```

当前不建议一开始上 Airflow，维护成本偏高。

### 9.5 可视化

ERP 前端推荐：

```text
ECharts
Element Plus Table
```

Python 后端返回 JSON，不直接生成复杂前端页面。

Python 可以提供：

- 图表数据
- 指标卡片数据
- 明细表格数据
- 导出文件

### 9.6 正式报表的前后端分工

经过当前 ERP 项目结构评估，正式报表模块建议采用：

```text
Python 负责数据
Vue 负责页面
ECharts 负责图表
Element Plus / vxe-table 负责表格
```

也就是说，Python 不作为正式报表页面的渲染端，只提供数据接口。

推荐分工如下：

```text
Python 报表服务：
  - 拉取接口数据
  - 读取 Excel 文件
  - 清洗数据
  - 建设 stg / ods / dim / dwd / dws / ads 分层
  - 计算报表指标
  - 提供 JSON API
  - 提供导出文件接口
  - 提供任务状态接口

ERP Vue 前端：
  - 报表菜单
  - 页面布局
  - 筛选条件
  - 排序分页
  - 指标卡片
  - ECharts 图表
  - 明细表格
  - 导出按钮
  - 权限控制后的展示
```

不建议把正式报表页面长期放在 Python 的 Streamlit、Dash 或 Matplotlib 页面里。

原因：

- ERP 已经有统一登录、菜单、权限、角色体系。
- ERP 前端已经使用 Element Plus，页面风格更统一。
- 当前前端已经安装 `echarts 5.6.0`，具备丰富图表能力。
- Vue 页面更适合和现有业务页面放在一起维护。
- 权限、路由、菜单、按钮权限都可以继续沿用若依体系。

Python 页面工具的定位：

```text
Streamlit / Dash：
  可以用于内部快速验证指标、做临时报表原型。
  不建议作为正式 ERP 报表入口。

Matplotlib：
  适合生成静态图片、分析脚本、离线报告。
  不适合作为 ERP 交互式报表主图表方案。

Plotly：
  交互能力强，但包体较大，页面风格和 ERP 不一定统一。
  如无特殊需求，优先使用 ECharts。
```

前端图表性能建议：

```text
1. 图表只请求聚合后的 DWS / ADS 数据，不直接拉明细大表。
2. 明细表格必须分页，不一次性返回几万行。
3. 首页看板不要同时加载过多重图表，优先懒加载。
4. 趋势图默认展示最近 30 / 90 天，超长时间范围按月聚合。
5. 排名图默认展示 Top 10 / Top 20。
6. 大表格如果出现卡顿，可以引入 vxe-table 做虚拟滚动。
7. Python 接口返回结构化 JSON，避免前端重复复杂计算。
```

图表数据接口建议返回前端友好的结构：

```json
{
  "summary": {
    "salesAmount": 123456.78,
    "orderCount": 830,
    "skuCount": 260
  },
  "trend": {
    "xAxis": ["07-01", "07-02"],
    "series": [
      {
        "name": "销售额",
        "type": "line",
        "data": [12000, 15000]
      }
    ]
  },
  "table": {
    "total": 100,
    "pageNum": 1,
    "pageSize": 20,
    "rows": []
  }
}
```

最终标准：

```text
Python 是数据发动机。
ERP Vue 是正式报表界面。
ECharts 是主要图表引擎。
```

## 10. ERP 与 Python 报表服务对接方式

有两种方式。

### 10.1 方式一：ERP 前端直接调用 Python

```text
ERP 前端 Vue -> Python FastAPI
```

优点：

- 简单。
- 开发快。
- 少一层转发。

缺点：

- 权限控制复杂。
- Token 校验要在 Python 里做。
- 跨域配置要处理。

### 10.2 方式二：ERP 后端转发 Python 接口

```text
ERP 前端 Vue -> Java ERP 后端 -> Python FastAPI
```

优点：

- 权限仍然走 ERP。
- 前端只访问 ERP 后端。
- Python 服务不直接暴露给用户。
- 安全性更好。

缺点：

- 多一层 Java 转发接口。

### 10.3 推荐方式

推荐使用方式二：

```text
Vue 报表页面调用 Java ERP 接口
Java 校验菜单/按钮权限
Java 调用 Python 报表接口
Python 返回报表数据
Java 返回给前端
```

这样最符合你现在若依系统的权限结构。

## 11. 权限设计

### 11.1 菜单权限仍在 ERP

报表菜单仍然建在 ERP 中。

例如：

```text
运营中心
  ├─ 报表中心
  │  ├─ 经营总览
  │  ├─ 销售报表
  │  ├─ 库存报表
  │  ├─ 补货报表
  │  ├─ 报关报表
  │  └─ 任务监控
```

权限标识示例：

```text
report:overview:view
report:sales:view
report:inventory:view
report:customs:view
report:job:list
report:job:run
report:export
```

### 11.2 Python 接口鉴权

Java 调用 Python 时建议使用内部签名。

请求头示例：

```text
X-JMH-App: erp
X-JMH-Timestamp: 1780000000
X-JMH-Nonce: random-string
X-JMH-Signature: sha256(app + timestamp + nonce + secret + body)
```

Python 校验：

- 时间戳不能超过 5 分钟。
- nonce 防重复请求。
- signature 必须正确。

### 11.3 数据权限

如果后续报表需要按用户、店铺、平台隔离数据，建议由 ERP 后端处理用户权限后，把授权范围传给 Python。

例如：

```json
{
  "userId": 101,
  "platforms": ["AMZ", "EBAY"],
  "shops": ["US1-刘子洋-US", "EU-伶斯勋-DE"],
  "warehouses": ["CTUAMZ-US1中转仓"]
}
```

Python 根据授权范围拼接查询条件。

## 12. API 设计规范

### 12.1 接口路径规范

```text
/api/v1/reports/overview
/api/v1/reports/sales/summary
/api/v1/reports/sales/trend
/api/v1/reports/inventory/warning
/api/v1/reports/replenishment/amz
/api/v1/reports/replenishment/ebay
/api/v1/reports/customs/summary
/api/v1/etl/jobs
/api/v1/etl/jobs/{job_code}/run
/api/v1/etl/logs
```

### 12.2 通用返回格式

```json
{
  "code": 200,
  "message": "success",
  "data": {},
  "traceId": "202607021500000001"
}
```

### 12.3 图表接口返回格式

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "title": "销售趋势",
    "xAxis": ["2026-07-01", "2026-07-02"],
    "series": [
      {
        "name": "销售额",
        "type": "line",
        "data": [1234.56, 2345.67]
      }
    ]
  }
}
```

### 12.4 表格接口返回格式

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "total": 100,
    "pageNum": 1,
    "pageSize": 20,
    "rows": []
  }
}
```

## 13. 报表页面设计建议

### 13.1 ERP 前端页面结构

建议新增：

```text
src/views/report/
├─ overview/
│  └─ index.vue
├─ sales/
│  └─ index.vue
├─ inventory/
│  └─ index.vue
├─ replenishment/
│  ├─ amz.vue
│  └─ ebay.vue
├─ customs/
│  └─ index.vue
└─ job/
   └─ index.vue
```

### 13.2 页面组件建议

通用组件：

```text
ReportFilterBar
MetricCard
TrendChart
RankChart
ReportTable
DateRangePicker
ShopSelector
PlatformSelector
WarehouseSelector
ExportButton
```

### 13.3 报表页面交互原则

- 页面默认展示最近 7 天或最近 30 天。
- 所有筛选条件都能重置。
- 图表和表格联动。
- 明细数据支持导出。
- 指标旁边支持说明 tooltip。
- 加载慢的报表显示 loading。
- 接口失败显示明确错误信息。

## 14. 数据同步策略

### 14.1 全量同步

适合：

- 店铺表
- 仓库表
- 国家映射
- 类目映射
- 小型维表

方式：

```text
truncate + insert
```

或：

```text
replace into
```

### 14.2 增量同步

适合：

- 订单
- 库存
- 采购单
- 货件
- 出入库记录

方式：

```text
按 update_time
按 create_time
按业务单号
按接口游标
按文件 hash
```

### 14.3 快照同步

适合：

- 库存快照
- 补货快照
- 每日销量快照
- 每日利润快照

建议字段：

```text
snapshot_date
batch_id
platform
shop_name
warehouse_name
sku
```

### 14.4 幂等设计

所有 ETL 任务必须支持重复执行不产生脏数据。

常见唯一键：

```text
source + business_id
source + business_id + line_no
snapshot_date + platform + shop + sku
batch_id + source_key
file_hash
```

写入方式：

```sql
INSERT INTO ... ON DUPLICATE KEY UPDATE ...
```

## 15. 调度设计

### 15.1 初期调度

使用 Python APScheduler。

示例：

```text
00:30 拉取领星商品
01:00 拉取领星库存
01:30 拉取销售数据
02:00 读取固定文件夹
02:30 构建 ODS
03:00 构建 DWD
03:30 构建 DWS
04:00 构建 ADS
04:30 报表质量检查
```

### 15.2 任务分组

建议分组：

```text
source_api_group       接口拉取组
source_file_group      文件处理组
ods_build_group        ODS 清洗组
dwd_build_group        DWD 明细组
dws_build_group        DWS 汇总组
ads_build_group        ADS 应用组
quality_check_group    数据质量检查组
```

### 15.3 并发规则

建议：

- 不同数据源任务可以并发。
- 同一张目标表的任务不要并发写。
- 上游未完成时，下游不能开始。
- 每个 job_code 同一时间只能运行一个实例。
- 任务失败后可以重试，但不能无限重试。

### 15.4 依赖关系

示例：

```text
sync_lingxing_listing
sync_lingxing_inventory
sync_excel_sales
        ↓
build_ods_product
build_ods_inventory
build_ods_sales
        ↓
build_dwd_sales_detail
build_dwd_inventory_snapshot
        ↓
build_dws_sales_sku_daily
build_dws_inventory_daily
        ↓
build_ads_operation_dashboard
```

初期可以在 Python 代码里维护依赖关系。

后期任务多了可以迁移到 Airflow 或 DolphinScheduler。

## 16. 数据质量检查

建议每次 ETL 后做质量检查。

### 16.1 常见检查

- 主键是否重复。
- SKU 是否为空。
- 日期是否为空。
- 金额是否为负。
- 库存是否异常。
- 订单数量是否突增或突降。
- 今天数据量是否明显低于昨天。
- 国家代码是否能映射。
- 店铺是否能映射。
- 仓库是否能映射。

### 16.2 质量检查表

```sql
CREATE TABLE etl_quality_check_log (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  batch_id VARCHAR(64),
  check_code VARCHAR(100),
  check_name VARCHAR(200),
  table_name VARCHAR(200),
  status VARCHAR(20),
  expected_value VARCHAR(200),
  actual_value VARCHAR(200),
  message TEXT,
  created_time DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 16.3 异常处理

异常级别：

```text
INFO     提示
WARN     可继续
ERROR    当前任务失败
FATAL    阻断下游任务
```

例如：

```text
接口无数据：WARN，跳过
文件不存在：WARN，跳过
字段缺失：ERROR
数据库连接失败：FATAL
```

## 17. 日志与监控

### 17.1 Python 日志

日志建议同时输出到：

- 控制台
- 日志文件
- etl_job_log 表

日志目录：

```text
logs/
├─ app.log
├─ etl.log
├─ api.log
└─ error.log
```

### 17.2 ERP 任务监控页面

建议 ERP 中新增“报表任务监控”页面。

字段：

```text
任务名称
任务编码
最近执行时间
执行状态
读取条数
新增条数
更新条数
失败条数
耗时
错误信息
操作：重跑 / 查看日志
```

这个页面可以通过 Java 后端调用 Python 的任务日志接口。

## 18. 部署方案

### 18.1 服务组成

最终部署包含：

```text
Java ERP 后端
Vue ERP 前端
MySQL 业务库
MySQL 报表库
Python FastAPI 报表服务
Python ETL 调度进程
Nginx
```

Python 报表服务和 ETL 可以先放在同一个项目中。

### 18.2 Windows 部署建议

如果部署机是 Windows：

```text
D:/JMH_Project/jmh-report-service
D:/JMH_Report_Files/input
D:/JMH_Report_Files/processed
D:/JMH_Report_Files/failed
D:/JMH_Report_Logs
```

启动方式：

- 开发阶段：命令行启动。
- 部署阶段：NSSM 注册为 Windows 服务。

示例：

```text
nssm install JMHReportService
nssm install JMHReportScheduler
```

### 18.3 Linux 部署建议

如果后续迁移 Linux：

```text
/opt/jmh/report-service
/data/jmh-report-files
/var/log/jmh-report
```

使用：

```text
systemd
supervisor
docker compose
```

## 19. 配置管理

使用 `.env` 管理配置。

示例：

```env
APP_ENV=prod
APP_PORT=9000

ERP_DB_HOST=127.0.0.1
ERP_DB_PORT=3306
ERP_DB_USER=readonly_user
ERP_DB_PASSWORD=******
ERP_DB_NAME=jmh_data_platform

REPORT_DB_HOST=127.0.0.1
REPORT_DB_PORT=3306
REPORT_DB_USER=report_user
REPORT_DB_PASSWORD=******
REPORT_DB_NAME=jmh_report

LINGXING_APP_ID=******
LINGXING_APP_SECRET=******

FEISHU_APP_ID=******
FEISHU_APP_SECRET=******

INTERNAL_API_SECRET=******
FILE_INPUT_DIR=D:/JMH_Report_Files/input
FILE_PROCESSED_DIR=D:/JMH_Report_Files/processed
FILE_FAILED_DIR=D:/JMH_Report_Files/failed
```

注意：

- 不要把 `.env` 提交到 Git。
- 可以提交 `.env.example`。

## 20. 安全建议

### 20.1 数据库账号

ERP 业务库给 Python 使用只读账号：

```text
erp_readonly_user
```

报表库给 Python 使用读写账号：

```text
report_rw_user
```

ERP 后端查询报表库或调用 Python 时使用只读权限。

### 20.2 接口安全

Python 服务不建议直接暴露公网。

推荐：

```text
只允许 ERP 后端所在机器访问 Python 端口
```

如果必须跨机器访问：

- 使用内网。
- 使用 Nginx 白名单。
- 使用接口签名。
- 使用 HTTPS。

### 20.3 敏感数据

敏感配置：

- 飞书 App Secret
- 领星 App Secret
- 数据库密码
- 内部接口签名密钥

必须放到 `.env` 或服务器环境变量。

## 21. 报表主题规划

### 21.1 经营总览

指标：

- 今日销售额
- 本月销售额
- 订单数
- SKU 数
- 库存金额
- 待补货数量
- 报关金额
- 异常商品数量

表：

```text
ads_operation_overview_dashboard
```

### 21.2 销售报表

维度：

- 日期
- 平台
- 店铺
- 国家
- SKU
- 产品分类
- 负责人

指标：

- 销售数量
- 销售金额
- 毛利
- ROI
- 退货率
- 7 天销量
- 15 天销量
- 30 天销量

表：

```text
dws_sales_sku_daily
ads_sales_dashboard
```

### 21.3 库存报表

维度：

- 平台
- 店铺
- 仓库
- SKU
- 国家

指标：

- 可售库存
- 在途库存
- 总库存
- 库龄
- 周转天数
- 缺货风险
- 滞销风险

表：

```text
dwd_inventory_snapshot
dws_inventory_sku_daily
ads_inventory_dashboard
```

### 21.4 补货报表

AMZ 和 eBay 可以分别建主题。

指标：

- 销量预测
- 最大月销补货量
- 建议采购量
- 当前库存
- 在途数量
- 采购未交付
- 产品性质
- 退货等级
- 负责人

表：

```text
ads_amz_replenishment_dashboard
ads_ebay_replenishment_dashboard
```

### 21.5 报关报表

指标：

- 报关商品数量
- 报关金额
- 箱数
- 毛重
- 净重
- 体积
- 目的国
- 货源地
- 含税 / 不含税

表：

```text
dwd_customs_product_detail
dws_customs_country_monthly
ads_customs_dashboard
```

## 22. 和现有 ERP 功能的关系

### 22.1 Java ERP 继续保留

这些功能继续留在 Java ERP：

- 用户登录
- 菜单权限
- 角色权限
- 数据录入
- 商品维护
- 出入库清单
- 报关单制作
- 补货页面
- 定时任务配置
- 业务接口同步

### 22.2 Python 新增职责

Python 新增：

- 报表数据仓库
- 数据清洗
- 历史快照
- 跨来源数据聚合
- 图表数据 API
- 报表导出
- 数据质量检查
- 后续 AI 分析

### 22.3 不建议迁移的内容

不建议把这些迁到 Python：

- ERP 权限体系
- 业务增删改
- 报关单制作业务操作
- 补货人工维护
- 用户角色菜单

## 23. 开发阶段路线图

### 阶段一：基础框架

目标：跑起来。

任务：

```text
1. 创建 jmh_report 数据库
2. 创建 etl 元数据表
3. 创建 Python FastAPI 项目
4. 配置 ERP 业务库只读连接
5. 配置报表库读写连接
6. 实现 health 接口
7. 实现一个测试报表接口
8. ERP 新增报表中心菜单
9. ERP 页面调用 Python 测试接口
```

### 阶段二：文件 ETL

目标：固定文件夹 Excel 自动入仓。

任务：

```text
1. 建 stg_excel_xxx_raw
2. 扫描 input 文件夹
3. 识别新文件
4. 读取 Excel
5. 写入 STG
6. 清洗到 ODS
7. 写入文件处理日志
8. 做失败文件隔离
```

### 阶段三：ERP 业务库同步

目标：把 ERP 业务数据同步到报表库。

任务：

```text
1. 同步 shop_list
2. 同步商品表
3. 同步库存表
4. 同步补货快照
5. 同步报关相关表
6. 建 dim_shop、dim_country、dim_warehouse
```

### 阶段四：领星接口同步

目标：报表系统独立拉取领星数据。

任务：

```text
1. 封装领星 client
2. 实现 token / 签名
3. 实现分页
4. 实现失败重试
5. 写入 STG
6. 清洗到 ODS
7. 记录 api cursor
```

### 阶段五：第一批报表

目标：做出可用报表。

优先做：

```text
1. 经营总览
2. 库存看板
3. 销售趋势
4. AMZ 补货分析
5. eBay 补货分析
```

### 阶段六：任务监控

目标：能看到任务状态。

任务：

```text
1. Python 提供任务日志接口
2. ERP 新增任务监控页面
3. 支持手动重跑任务
4. 支持查看失败原因
```

### 阶段七：高级分析

目标：加入预测和 AI。

可做：

```text
1. 销量预测
2. 库存预警
3. 利润异常检测
4. 商品分层
5. AI 自动解释报表
6. 飞书推送日报
```

## 24. 示例 ETL 任务伪代码

### 24.1 文件读取任务

```python
def sync_excel_sales():
    batch = create_batch("sync_excel_sales")
    files = scan_new_files("D:/JMH_Report_Files/input/sales")

    if not files:
        write_job_log(batch, status="skipped", message="没有新文件")
        return

    for file in files:
        try:
            df = read_excel(file)
            rows = normalize_raw_rows(df)
            insert_stg_excel_sales_raw(batch.batch_id, file, rows)
            mark_file_success(file, batch.batch_id)
        except Exception as e:
            mark_file_failed(file, str(e))
            write_error_log(batch, file, e)

    run_sql("sql/ods/build_ods_sales_detail.sql", batch_id=batch.batch_id)
    run_sql("sql/dwd/build_dwd_sales_detail.sql", batch_id=batch.batch_id)
    run_sql("sql/dws/build_dws_sales_sku_daily.sql", batch_id=batch.batch_id)
    run_sql("sql/ads/build_ads_sales_dashboard.sql", batch_id=batch.batch_id)

    finish_batch(batch, status="success")
```

### 24.2 接口同步任务

```python
def sync_lingxing_listing():
    batch = create_batch("sync_lingxing_listing")
    cursor = get_api_cursor("lingxing", "listing", "update_time")

    page = 1
    total_count = 0

    while True:
        result = lingxing_client.listing(page=page, update_time_start=cursor.value)
        items = result.get("data", [])

        if not items:
            break

        insert_stg_lingxing_listing_raw(batch.batch_id, items)
        total_count += len(items)

        if not result.get("has_more"):
            break

        page += 1

    run_sql("sql/ods/build_ods_product_listing_detail.sql", batch_id=batch.batch_id)
    update_api_cursor("lingxing", "listing", "update_time", now())
    finish_batch(batch, status="success", read_count=total_count)
```

## 25. SQL 文件组织方式

建议 SQL 不要散落在 Python 代码字符串中。

SQL 应该直接写成 `.sql` 文件，由 Python ETL 自动读取并执行。

不使用 MySQL 自带定时任务作为主调度。

推荐执行模型：

```text
Python 定时任务
  ↓
读取 .sql 文件
  ↓
替换参数
  ↓
连接 MySQL
  ↓
执行 SQL
  ↓
提交事务
  ↓
记录 etl_job_log
```

推荐：

```text
app/etl/sql/
├─ ods/
│  ├─ build_ods_product_listing_detail.sql
│  ├─ build_ods_inventory_detail.sql
│  └─ build_ods_sales_detail.sql
├─ dwd/
│  ├─ build_dwd_sales_detail.sql
│  └─ build_dwd_inventory_snapshot.sql
├─ dws/
│  ├─ build_dws_sales_sku_daily.sql
│  └─ build_dws_inventory_sku_daily.sql
└─ ads/
   ├─ build_ads_operation_dashboard.sql
   └─ build_ads_sales_dashboard.sql
```

Python 负责读取 SQL 文件并替换参数：

```text
:batch_id
:business_date
:start_date
:end_date
```

### 25.1 SQL 文件命名规范

推荐命名：

```text
build_层级_主题.sql
```

示例：

```text
build_ods_product_listing_detail.sql
build_ods_inventory_detail.sql
build_dwd_sales_detail.sql
build_dws_sales_sku_daily.sql
build_ads_sales_dashboard.sql
```

如果同一个主题分多个步骤，可以加序号：

```text
01_clear_temp_sales.sql
02_build_temp_sales.sql
03_merge_dws_sales_sku_daily.sql
```

### 25.2 SQL 文件参数规范

常用参数：

```text
:batch_id       当前批次 ID
:biz_date       业务日期
:start_date     开始日期
:end_date       结束日期
:job_code       任务编码
```

SQL 文件中不要写死日期。

不推荐：

```sql
WHERE report_date = '2026-07-01'
```

推荐：

```sql
WHERE report_date = :biz_date
```

### 25.3 SQL 文件示例

示例：`app/etl/sql/ods/build_ods_product_listing_detail.sql`

```sql
INSERT INTO ods_product_listing_detail (
  batch_id,
  platform,
  shop_name,
  seller_sku,
  local_sku,
  price,
  country_code,
  country_name,
  created_time
)
SELECT
  :batch_id AS batch_id,
  'AMZ' AS platform,
  TRIM(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.store_name'))) AS shop_name,
  TRIM(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.seller_sku'))) AS seller_sku,
  TRIM(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.local_sku'))) AS local_sku,
  CAST(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.price')) AS DECIMAL(18,2)) AS price,
  TRIM(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.country_code'))) AS country_code,
  CASE TRIM(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.country_code')))
    WHEN 'US' THEN '美国'
    WHEN 'UK' THEN '英国'
    WHEN 'GB' THEN '英国'
    WHEN 'DE' THEN '德国'
    WHEN 'FR' THEN '法国'
    WHEN 'ES' THEN '西班牙'
    WHEN 'IT' THEN '意大利'
    WHEN 'PL' THEN '波兰'
    ELSE TRIM(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.country_code')))
  END AS country_name,
  NOW() AS created_time
FROM stg_lingxing_listing_raw
WHERE batch_id = :batch_id;
```

如果 MySQL 版本不适合大量 JSON 解析，也可以在 Python 写入 STG 时就拆成普通列，ODS SQL 直接清洗普通列。

### 25.4 Python 调用 SQL 文件示例

伪代码：

```python
def run_sql_file(path: str, params: dict):
    sql = read_text(path)
    sql = render_sql(sql, params)

    with report_db.transaction() as conn:
        affected_rows = conn.execute(sql)

    return affected_rows
```

任务代码：

```python
def build_ods_product_listing(batch_id: str):
    start_job_log("build_ods_product_listing", batch_id)

    try:
        rows = run_sql_file(
            "app/etl/sql/ods/build_ods_product_listing_detail.sql",
            {
                "batch_id": batch_id
            }
        )
        finish_job_log(
            job_code="build_ods_product_listing",
            batch_id=batch_id,
            status="success",
            insert_count=rows
        )
    except Exception as e:
        fail_job_log(
            job_code="build_ods_product_listing",
            batch_id=batch_id,
            error_message=str(e)
        )
        raise
```

### 25.5 为什么不用 MySQL 自带定时任务

MySQL Event Scheduler 只适合数据库内部非常简单的固定 SQL。

本项目不建议用它作为主 ETL 调度，原因：

```text
1. 不能方便地拉取外部接口。
2. 不能方便地扫描固定文件夹。
3. 不适合处理 Excel 文件。
4. 不适合做失败重试。
5. 不适合管理复杂任务依赖。
6. 不适合做批次日志和文件归档。
7. 不方便手动重跑指定日期、指定批次。
8. 不方便后续迁移到 Airflow / DolphinScheduler。
```

因此定时任务统一放在 Python。

推荐：

```text
APScheduler / 后续 Airflow / DolphinScheduler
```

不推荐：

```text
MySQL Event Scheduler 作为主调度
```

### 25.6 存储过程使用边界

存储过程不是完全不能用，但不要作为主方案。

可以使用的场景：

```text
1. 极少数非常稳定的纯 SQL 汇总。
2. 需要数据库内部封装的固定计算。
3. 性能上明确需要数据库端复用执行计划的场景。
```

不建议使用的场景：

```text
1. 调接口。
2. 读 Excel。
3. 文件归档。
4. 复杂异常处理。
5. 多任务依赖调度。
6. 需要频繁调整的业务清洗规则。
```

当前项目默认规范：

```text
优先 .sql 文件 + Python 调度。
只有明确必要时才使用存储过程。
```

## 26. 数据生命周期

### 26.1 STG 原始层保留周期

建议：

```text
最近 3-6 个月保留在线
更早数据可归档
```

如果原始数据很重要，可以长期保留。

### 26.2 ODS / DWD 保留周期

建议长期保留。

### 26.3 DWS / ADS 保留周期

建议长期保留，或者按业务需要重建。

如果 ADS 可以由 DWS 快速生成，也可以只保留最近结果。

## 27. 性能建议

### 27.1 索引

常用字段必须建索引：

```text
report_date
snapshot_date
platform
shop_name
warehouse_name
sku
seller_sku
batch_id
source_order_no
created_time
updated_time
```

### 27.2 分区

如果数据量变大，可以按日期分区。

适合分区的表：

```text
dwd_sales_detail
dwd_inventory_snapshot
dws_sales_sku_daily
etl_job_log
```

### 27.3 预聚合

报表页面不要直接查明细大表做复杂 group by。

推荐：

```text
明细在 DWD
常用聚合在 DWS
页面查询 ADS
```

## 28. 备份与恢复

### 28.1 报表库备份

建议：

```text
每天凌晨备份 jmh_report
保留最近 7 天
每周保留一个周备份
每月保留一个月备份
```

### 28.2 文件备份

固定文件夹中的原始文件建议归档。

```text
processed 文件至少保留 3-6 个月
重要文件长期归档
```

### 28.3 可重跑能力

ETL 设计必须支持通过 batch 或日期重跑。

例如：

```bash
python scripts/backfill.py --job build_ads_sales_dashboard --date 2026-07-01
```

## 29. 未来可升级方向

### 29.1 引入分析型数据库

当 MySQL 报表查询变慢，可以考虑：

```text
ClickHouse
Apache Doris
StarRocks
PostgreSQL
```

升级方式：

```text
MySQL 继续作为业务库
报表库部分迁移到分析库
Python ETL 写入分析库
ERP 调用 Python 查询分析库
```

### 29.2 引入消息队列

当实时性要求提高，可以引入：

```text
RabbitMQ
Kafka
Redis Stream
```

### 29.3 引入专业调度器

任务很多后，可以升级：

```text
DolphinScheduler
Airflow
Prefect
```

### 29.4 引入 AI 报表解释

Python 可以基于 ADS 层数据生成：

- 今日经营总结
- 库存异常解释
- 销量异常解释
- 补货建议解释
- 飞书日报

## 30. 最终推荐方案

当前最适合你的方案是：

```text
1. 保留 Java ERP 作为业务系统。
2. 新建一个独立 Python 报表服务。
3. 新建一个报表数据库 jmh_report。
4. 在一个库内用表名前缀实现 stg / ods / dim / dwd / dws / ads 分层。
5. Python 负责 ETL、调度、接口、文件读取、数据清洗。
6. SQL 负责聚合、去重、落表和指标计算。
7. FastAPI 只提供报表数据接口、任务状态接口和导出接口。
8. ERP 后端负责权限校验，并按需转发 Python 报表接口。
9. ERP 前端使用 Vue + ECharts + Element Plus 完成正式可视化展示。
10. 后续数据量变大，再升级调度器和分析型数据库。
```

这个方案的优点：

- 不破坏现有 ERP。
- 报表逻辑和业务逻辑解耦。
- Python 更适合数据处理和分析。
- 分层清楚，便于维护。
- 前期开发成本低。
- 后期可以平滑升级。

## 31. 一句话结论

建议将报表体系设计为：

```text
Java ERP = 业务系统
Python FastAPI = 报表数据服务
Python ETL = 数据处理中心
jmh_report = 轻量数据仓库
ERP 报表中心 = 可视化入口
Vue + ECharts = 正式图表展示
```

先用一个报表库完成 `stg / ods / dim / dwd / dws / ads` 分层，等数据规模和团队复杂度真正上来后，再考虑拆库、引入调度平台和分析型数据库。
