# JMH 报关单项目接入 ERP 插件菜单方案

> 版本：v1.2（数据源与导出格式已确认）
>
> 盘点日期：2026-09-28
>
> 适用代码库：`D:\JMH\项目\JMH-Date-Platform`
>
> 待接入旧项目：`D:\JMH\项目\JMH\customs_declaration`
>
> 本文用途：交给开发、测试和部署人员执行。本文不代表已经部署或已经迁移数据。

## 1. 结论先行

推荐采用“**ERP 原生报关模块复用 + ERP 原生插件菜单 + 一次性数据迁移**”方案：

1. **不部署旧 Flask 服务，不把 `5000` 端口页面 iframe 到 ERP。**
2. **不在 `jmh_data_platform` 新建第二套通用 `products` 业务表。**
3. ERP 运行时只使用现有 Vue 页面、Java 接口和 `jmh_data_platform` 中现有报关表/视图。
4. 在 ERP 动态菜单中增加一级“插件菜单”和二级“报关单生成器”，由 RuoYi 动态路由直接加载现有 Vue 报关组件。
5. 已确认以旧项目的 `customsdeclaration.sql` 作为一次性权威迁移源；先进入暂存表，完成校验、去重、冲突报告和人工确认后，再保守写入 `customs_declaration_history`。
6. 默认只插入不存在的合格数据，**不得自动覆盖 ERP 已有非空字段**。
7. 已确认不要求保留旧项目的单页 Excel 格式，统一使用 ERP 现有导出模板和导出逻辑。

最终运行链路如下：

```text
ERP 用户（使用现有 ERP 域名和登录态）
  |
  +-- 插件菜单 > 报关单生成器
          |
          +-- ERP Vue 组件 operations/customs/declaration/index
                  |
                  +-- /operations/customs/declaration/**
                  |
                  +-- RuoYi Spring Boot 3（RBAC、事务、操作日志）
                          |
                          +-- jmh_data_platform
                              customs_declaration_product_view
                              customs_declaration_history
                              customs_inventory_list
```

终端用户只访问 ERP，不需要访问内网地址、Python `8010`、Flask `5000` 或旧数据库。旧 Flask、旧 `customsdeclaration` 库和 Date-Project 自身业务库均不进入报关功能的运行时链路。

## 2. 现状盘点

### 2.1 旧项目

旧项目是 Flask 3 + 原生 HTML/JavaScript + MySQL + openpyxl：

- 入口：`D:\JMH\项目\JMH\customs_declaration\app.py`
- 数据访问：`D:\JMH\项目\JMH\customs_declaration\models.py`
- 前端：`D:\JMH\项目\JMH\customs_declaration\templates\index.html`
- 前端逻辑：`D:\JMH\项目\JMH\customs_declaration\static\app.js`
- 数据导出：`D:\JMH\项目\JMH\customsdeclaration.sql`

现有接口包括：

- `GET /`
- `GET /api/search`
- `POST /api/import`
- `POST /api/update-product`
- `POST /api/batch-query`
- `POST /api/export`
- `POST /api/init-db`

不能直接作为 ERP 子服务部署的原因：

- 无 ERP 登录态和 RBAC；导入、修改、导出、建库均可匿名调用。
- `CORS(app)` 全开放。
- 服务监听 `0.0.0.0:5000`，直接暴露会扩大攻击面。
- 数据库配置保存在旧项目配置中，不符合统一密钥管理要求。
- 上传未形成完整的大小、扩展名、内容和行数限制。
- 异常详情会直接返回客户端。
- 报关模板硬编码为 `D:\JMH\报关单模版.xlsx`，无法可靠部署到服务器或容器。
- `export_excel.py` 中未被当前 Flask 入口调用的旧四联单逻辑，与当前 `models.py` 字段模型不一致。
- `seed_data.py` 与当前模型也不一致，不能作为迁移依据。

因此，旧项目只保留三种价值：**业务交互参考、旧模板参考、历史数据来源**。

### 2.2 ERP 已有报关能力

ERP 已存在更完整的原生模块：

- Vue 页面：`RuoYi-Vue3-master/src/views/operations/customs/declaration/index.vue`
- Vue API：`RuoYi-Vue3-master/src/api/operations/customs/declaration.js`
- Java 控制器：`RuoYi-Vue-springboot3/ruoyi-admin/src/main/java/com/ruoyi/web/controller/operation/CustomsDeclarationController.java`
- 商品服务：`RuoYi-Vue-springboot3/ruoyi-system/src/main/java/com/ruoyi/system/service/operation/customs/CustomsProductService.java`
- 导出服务：`RuoYi-Vue-springboot3/ruoyi-system/src/main/java/com/ruoyi/system/service/operation/customs/CustomsDeclarationExportService.java`
- Mapper：`RuoYi-Vue-springboot3/ruoyi-system/src/main/resources/mapper/operation/customs/CustomsProductMapper.xml`
- 模板：`RuoYi-Vue-springboot3/ruoyi-system/src/main/resources/templates/customs/customs-declaration-template.xlsx`

已有能力覆盖并增强了旧项目：

- SKU/品名搜索、批量查询；
- SKU 文件、单个或多个历史报关单、FBA 装箱明细导入；
- 商品存在性检查和幂等保存；
- 海外备货单及 FBA 货件关联；
- 文件类型、文件大小及内容校验；
- 最多 1,000 个商品的报关文件导出；
- 生成日志、库存扣减关联；
- Spring Security RBAC、`@Log` 操作日志和事务控制。

现有后端权限：

| 权限 | 用途 |
| --- | --- |
| `customs:declaration:query` | 搜索、批量查询、关联数据源 |
| `customs:declaration:import` | SKU、历史报关单和 FBA 装箱导入 |
| `customs:declaration:export` | 导出报关单 |
| `customs:product:edit` | 检查并保存商品主数据 |

### 2.3 两个数据库的处理边界

| 数据库/数据源 | 接入后的定位 | 运行时是否访问 |
| --- | --- | --- |
| 旧 `customsdeclaration.products` / `customsdeclaration.sql` | 一次性迁移源，只读、可追溯 | 否 |
| ERP `jmh_data_platform` | 唯一权威数据源 | 是 |
| Date-Project 自身数据库 | 其他 Python 业务使用 | 本插件不使用 |

禁止让 Java 在每次请求时跨库查询旧 `customsdeclaration`。迁移验收通过后，应撤销 ERP 对旧库的运行时依赖和凭据；旧库是否归档/下线由数据负责人另行审批。

### 2.4 数据盘点快照

盘点时观察到：

- `customsdeclaration.sql`：2,665 条 `products` INSERT；存在 1 条空 SKU。
- 旧本地 `customsdeclaration.products`：仅约 25 条，属于不完整的旧运行现场，不作为迁移基线。
- ERP `customs_declaration_history`：约 469 行、468 个不同 SKU。
- ERP `customs_inventory_list`：约 3,397 行、3,374 个不同 SKU。
- SQL 导出与 ERP 精确 SKU 命中约 452 条。
- 按现有 `normalize_customs_sku_key` 归一化后累计命中约 761 条，即另有约 309 条“文本不同但业务键相同”的高风险冲突。
- 归一化后未命中候选约 1,904 条；其中可能包含空 SKU和源内归一化重复，不能把 1,904 直接当作最终插入数。

这些数字是盘点快照，不是上线常量，迁移当天必须重跑统计。业务已经确认：**以 `D:\JMH\项目\JMH\customsdeclaration.sql` 中的 2,665 条 INSERT 作为权威历史数据源**；旧运行库约 25 条记录不参与全量基线计算。执行前仍需记录源文件 SHA-256，确保测试、审批和正式迁移使用同一个文件版本。

## 3. ERP 原生插件菜单对接设计

### 3.1 插件菜单的实际落位

当前 `sys_menu` 中没有字面名称为“插件菜单”的独立父菜单，因此新增一个 ERP 原生一级目录：

```text
插件菜单（M，path=plugins）
└─ 报关单生成器（C，path=customs-declaration）
   ├─ 报关导入（F，customs:declaration:import）
   ├─ 商品编辑（F，customs:product:edit）
   └─ 报关导出（F，customs:declaration:export）
```

二级菜单直接配置：

```text
component  = operations/customs/declaration/index
route_name = PluginCustomsDeclaration
route path = /plugins/customs-declaration
perms      = customs:declaration:query
```

它加载的是 ERP 已有 Vue 组件，不复制页面、不创建 iframe、不经过 Date-Project。原“运营/报关”入口可以在过渡期保留为同一组件的另一个入口；待权限和使用习惯稳定后，再由产品决定是否隐藏旧入口。

### 3.2 ERP 访问链路

用户使用现有 ERP 地址和账号登录。`/getRouters` 根据 `sys_menu` 返回“插件菜单”和“报关单生成器”动态路由，Vue 直接加载已有报关组件；组件通过 ERP 统一请求封装访问 Java 接口。

```text
浏览器 -> ERP HTTPS 域名 -> Vue 动态路由
       -> ERP API 网关/Java 8080
       -> jmh_data_platform
```

浏览器不得访问数据库，也不得访问 `127.0.0.1:8010`、`内网IP:8010`、`5000` 或旧项目目录。Java 后端和 MySQL 的服务器内部连接属于 ERP 基础设施，由部署网络控制，不暴露给用户。

### 3.3 前后端复用范围

前端不新增第二份报关页面，只复用：

`RuoYi-Vue3-master/src/views/operations/customs/declaration/index.vue`

后端继续复用：

`RuoYi-Vue-springboot3/ruoyi-admin/src/main/java/com/ruoyi/web/controller/operation/CustomsDeclarationController.java`

现有 `/operations/customs/declaration/**` 接口、`@PreAuthorize`、`@Log`、事务、文件校验和导出上限全部保持不变。正常接入只需要菜单 SQL和角色授权；不需要修改 Date-Project、增加 Java 代理或增加 Python 会话。

若动态路由直接复用同一组件时出现 Vue `route_name` 冲突，只给新插件入口使用唯一 `route_name=PluginCustomsDeclaration`；组件路径可以相同，路由名称不能重复。

### 3.4 ERP 菜单 SQL

迁移 SQL 建议命名：

`RuoYi-Vue-springboot3/sql/20260928_add_customs_declaration_plugin_menu.sql`

SQL 必须满足：

- 一级菜单按 `parent_id=0 AND path='plugins' AND menu_type='M'` 查找，不硬编码 ID；
- 二级页面按 `parent_id + path='customs-declaration'` 查找；
- 页面 `component='operations/customs/declaration/index'`；
- 页面 C 节点承载 `customs:declaration:query`，另外三个 F 权限按 `parent_id + perms` 幂等插入；
- `route_name` 唯一；
- 不自动给全部角色授权；
- 文件末尾核验菜单树、重复路径、重复路由名和角色授权。

示意结构：

```sql
USE jmh_data_platform;
SET NAMES utf8mb4;

-- 1. 幂等创建 ERP 一级菜单：插件菜单（M，path=plugins）
-- 2. 取得 @plugins_menu_id
-- 3. 幂等创建报关单生成器（C）
--    path='customs-declaration'
--    component='operations/customs/declaration/index'
--    route_name='PluginCustomsDeclaration'
--    perms='customs:declaration:query'
-- 4. 在该 C 菜单下幂等创建 import/edit/export 三个 F 权限
-- 5. SELECT 核验结果，不在迁移脚本中给业务角色自动授权
```

如果部署环境已经由管理员创建了其他名称的插件父菜单，只调整父菜单定位条件，不再创建第二个一级目录。该选择必须在执行 SQL 前通过查询确认。

### 3.5 角色授权包

角色必须获得完整 ERP 菜单祖先链和对应业务权限。

| 角色能力 | 需要的权限/菜单 |
| --- | --- |
| 看到插件菜单 | 一级“插件菜单”M 节点 |
| 打开并查询报关页面 | “报关单生成器”C 节点 + `customs:declaration:query` |
| 导入 | `customs:declaration:import` |
| 编辑商品 | `customs:product:edit` |
| 导出 | `customs:declaration:export` |

建议建立两种角色模板：

- **报关只读**：插件菜单 + 页面查询，不含导入、编辑、导出。
- **报关操作员**：插件菜单 + 查询 + 导入 + 编辑 + 导出。

前端隐藏按钮只改善体验，真正授权仍由 Java `@PreAuthorize` 执行。

## 4. 数据迁移设计

### 4.1 目标表选择

目标使用现有：

- `customs_declaration_history`：报关商品当前值及来源追溯；
- `customs_declaration_product_view`：库存清单优先、历史报关补齐的统一查询视图；
- `customs_inventory_list`：ERP 库存/商品主数据。

不新建正式 `products` 表，避免出现两套商品主数据和两套更新规则。

### 4.2 字段映射

| 旧 `products` | ERP `customs_declaration_history` | 处理规则 |
| --- | --- | --- |
| `id` | `source_row_no` | 记录旧主键用于追溯；在迁移说明中明确它不是 Excel 行号 |
| `sku` | `sku` | `TRIM` 后不能为空；保留完整 SKU |
| `sku` | `sku_key` | 调用现有 `normalize_customs_sku_key(sku)`，禁止另写一套规则 |
| 无 | `product_code` | 置空字符串 `''`；旧库没有可靠商品编码 |
| `description_cn` | `description_cn` | 空值转空字符串 |
| `model` | `model` | 空值转空字符串，不强行补“无型号” |
| `unit` | `unit` | 空值转空字符串；业务确认后才补默认单位 |
| `unit_price_usd` | `unit_price_usd` | 保持精度，不转字符串 |
| `currency` | `currency` | 空值才补 `USD` |
| `single_weight` | `single_weight` | 保持 kg 语义和精度 |
| 无 | 装箱重量/体积/尺寸/箱号 | 置 NULL，不伪造 |
| `hs_code` | `hs_code` | 作为字符串保存，保留前导零 |
| `hs_description` | `hs_description` | 保留内容，必要时只统一换行符 |
| `origin_country` | `origin_country` | 空值才补“中国” |
| `destination_country` | `destination_country` | 保留原值，不统一强改美国 |
| `source_location` | `source_location` | 去除首尾空白；内部换行需进入异常报告或规范为空格 |
| `exemption` | `exemption` | 保留原值 |
| 无 | `is_tax` | 暂置 `0`，并在迁移说明中标明“旧源无此字段”，不得由“照章”反推含税 |
| 无 | `source_type` | `JMH_PLUGIN_MIGRATION`（长度刚好 20） |
| 无 | `source_file_name` | `customsdeclaration.sql` |
| 无 | `source_sheet` | `products` |
| 无 | `updated_by` | `migration:jmh-customs:<batch-id>`，总长度不超过 64 |
| `created_at` | `created_at` | 合法时保留原时间 |
| `updated_at` | `updated_at` | 合法时保留原时间 |

### 4.3 迁移文件和批次

建议开发工程师交付：

- `RuoYi-Vue-springboot3/sql/20260928_jmh_customs_stage.sql`
- `RuoYi-Vue-springboot3/sql/20260928_jmh_customs_validate.sql`
- `RuoYi-Vue-springboot3/sql/20260928_jmh_customs_apply.sql`
- `RuoYi-Vue-springboot3/sql/20260928_jmh_customs_rollback.sql`
- `RuoYi-Vue-springboot3/sql/20260928_add_customs_declaration_script_tool.sql`
- 迁移报告 CSV：总量、拒绝、源内冲突、ERP 冲突、待插入、实际插入。

批次标识示例：`20260928-jmh-customs-v1`。实际执行时应使用当天不可重复的批次号。

### 4.4 暂存和校验

先将旧 SQL 的数据导入专用暂存表，例如：

`stg_jmh_customs_products_20260928`

暂存表要保留所有原字段，并额外保存：

- `migration_batch_id`
- `legacy_id`
- `raw_sku`
- `normalized_sku_key`
- `validation_status`
- `conflict_type`
- `conflict_detail`

不得直接把旧 dump 对着 `jmh_data_platform` 执行，因为原文件包含旧表结构/库上下文，可能误建或覆盖对象。应生成一份只写暂存表的派生 SQL，或用一次性受控加载程序写入暂存表；源文件必须记录 SHA-256。

迁移前必须完成以下检查：

1. 总行数、不同完整 SKU、空 SKU。
2. 完整 SKU 重复。
3. **源数据内部的归一化键重复。** 例如带 `JMH` 前缀和不带前缀的两个 SKU 可能归一化到同一键；即使完整 SKU 唯一，也不能自动插入两条业务重复数据。
4. `normalize_customs_sku_key` 函数存在并通过代表性样例。
5. 价格/重量为负数、异常大值、币种异常、HS 编码非字符串、控制字符和非法时间。
6. 与 `customs_declaration_history` 的完整 SKU 和归一化 SKU 冲突。
7. 与 `customs_inventory_list` 的非空商品名、单位、HS 编码等差异。
8. 所有分类数量相加必须等于暂存总量，不允许“未分类”行。

### 4.5 冲突分类

建议每条暂存数据只能进入以下一个最终分类：

| 分类 | 条件 | 自动动作 |
| --- | --- | --- |
| `REJECT_EMPTY_SKU` | SKU 为空或仅空白 | 拒绝 |
| `REJECT_INVALID` | 数值、长度、时间等校验失败 | 拒绝 |
| `SOURCE_NORMALIZED_DUPLICATE` | 源内多个完整 SKU 归一化为同一键 | 生成报告，人工选主记录 |
| `EXACT_SAME` | ERP 已有完整 SKU，关键字段完全一致 | 跳过 |
| `EXACT_CONFLICT` | ERP 已有完整 SKU，但关键字段不同 | 跳过并报告 |
| `NORMALIZED_CONFLICT` | 完整 SKU 不同，但归一化键已存在 | 跳过并报告 |
| `NEW_VALID` | 校验通过，源内唯一，ERP 无归一化匹配 | 允许插入 |

盘点中的 452 条精确命中和约 309 条归一化非精确命中都必须进入报告；不得用 `ON DUPLICATE KEY UPDATE` 静默覆盖。

### 4.6 写入原则

写入脚本必须使用显式字段列表，并满足：

```sql
INSERT INTO customs_declaration_history (...明确列名...)
SELECT ...
FROM stg_jmh_customs_products_20260928 s
WHERE s.migration_batch_id = @batch_id
  AND s.validation_status = 'NEW_VALID'
  AND NOT EXISTS (
    SELECT 1
    FROM customs_declaration_history h
    WHERE h.sku_key = normalize_customs_sku_key(s.sku)
  );
```

附加规则：

- 在事务内执行，写入前后记录行数。
- 不使用 `REPLACE INTO`。
- 不使用会覆盖现有字段的 `ON DUPLICATE KEY UPDATE`。
- 插入数必须精确等于执行前已审批的 `NEW_VALID` 数；否则回滚事务。
- 迁移账号只需目标表的最小权限，禁止应用账号拥有建库权限。
- 冲突数据后续若要修改，优先通过 ERP 受权限控制的商品保存接口完成，保留真实操作人和操作日志。

### 4.7 备份与回滚

执行前：

1. 对 `customs_declaration_history` 做带时间戳备份并核对行数。
2. 保存源 SQL 的 SHA-256、暂存总量和六类结果数量。
3. 暂停同表批量导入窗口，避免迁移过程中基线变化。

由于默认方案不更新旧行，正常回滚只删除本批新增记录：

```sql
DELETE FROM customs_declaration_history
WHERE source_type = 'JMH_PLUGIN_MIGRATION'
  AND source_file_name = 'customsdeclaration.sql'
  AND updated_by = @migration_updated_by;
```

只有在确认这些记录迁移后未被业务继续编辑时才能直接删除；否则按备份和迁移清单逐行恢复。暂存表和备份至少保留到业务验收完成，之后按公司的数据保留策略处理。

## 5. 导出格式决策

业务已经确认：**不要求保留旧项目的单页 Excel 格式。**

接入后统一使用 ERP 现有：

- `CustomsDeclarationExportService`；
- classpath 模板 `templates/customs/customs-declaration-template.xlsx`；
- `customs:declaration:export` 权限；
- ERP 操作日志、1,000 商品上限和现有字段校验。

旧 `D:\JMH\报关单模版.xlsx`、旧 Flask `/api/export` 和旧 `export_excel.py` 均不迁移、不部署、不作为验收基准。

上线测试仍需覆盖单 SKU、多 SKU、多箱、长申报要素、小数精度和空字段，验收目标是 ERP 导出内容正确、Excel 可正常打开、汇总公式正确，而不是与旧文件的版式逐单元格一致。

## 6. 开发任务拆分

### PR 1：ERP 原生插件菜单

责任范围：ERP 菜单 SQL；正常情况下不需要修改 Vue、Java 或 Date-Project。

- 幂等创建一级“插件菜单”M 节点。
- 幂等创建“报关单生成器”C 节点，直接复用现有 Vue 组件。
- C 节点使用 query 权限，并在其下创建 import/edit/export 三个 F 权限。
- 增加菜单核验 SQL：父子关系、component、path、route_name、权限和角色授权。
- 在测试角色上验证 `/getRouters` 和 `/getInfo` 返回结果。

完成标准：授权用户登录 ERP 后，可直接从“插件菜单”进入报关页面；用户浏览器不访问任何 Python、Flask、内网 IP 或额外端口。

### PR 2：数据迁移包

责任范围：只新增迁移脚本、核验查询和报告模板，不在合并代码时自动执行生产迁移。

- 暂存表脚本。
- 源文件加载说明和 SHA-256 记录。
- 数据质量校验和分类 SQL。
- 冲突差异报告。
- 保守插入脚本、事务数量门禁和回滚脚本。
- 迁移前后统计 SQL。

完成标准：测试库可重复演练；第二次执行不新增重复数据；所有 2,665 条候选均有唯一分类；空 SKU 和冲突不会进入正式表。

## 7. 测试与验收清单

### 7.1 菜单与 RBAC

| 编号 | 场景 | 预期 |
| --- | --- | --- |
| RBAC-01 | 未授权一级“插件菜单” | ERP 侧栏不显示插件菜单 |
| RBAC-02 | 有一级菜单、无报关 C 菜单 | 看不到“报关单生成器” |
| RBAC-03 | 有页面菜单、无 `customs:declaration:query` | 查询接口返回 403，角色配置判定不完整 |
| RBAC-04 | 只读角色 | 可查询；导入、编辑、导出按钮不可用，直调接口仍为 403 |
| RBAC-05 | 操作员角色 | 查询、导入、编辑、导出均按授权工作 |
| RBAC-06 | 未登录直接请求报关 API | 返回 401，不泄露业务数据 |
| RBAC-07 | 通过正式 ERP 域名访问 | 页面和 API 均走 ERP 网关，不请求内网 IP 或额外端口 |

### 7.2 数据迁移

| 编号 | 场景 | 预期 |
| --- | --- | --- |
| MIG-01 | 源总量 | 暂存行数与已确认源文件一致，当前候选基线为 2,665 |
| MIG-02 | 空 SKU | 当前至少 1 条进入 `REJECT_EMPTY_SKU`，正式表零写入 |
| MIG-03 | 完整 SKU 冲突 | 当前约 452 条被区分为相同或字段冲突，均不自动覆盖 |
| MIG-04 | 归一化冲突 | 当前约 309 条单独报告，不重复插入 |
| MIG-05 | 源内归一化重复 | 每组只允许人工确认后的主记录进入候选 |
| MIG-06 | 新数据 | 实际插入数等于审批后的 `NEW_VALID`，不是硬编码 1,904 |
| MIG-07 | 幂等 | 同一批次重复运行，新增 0 行，旧数据不变 |
| MIG-08 | 回滚 | 只移除本批插入行；迁移前数据和其他来源数据不受影响 |
| MIG-09 | 视图查询 | 新数据可经 `customs_declaration_product_view` 搜索；库存优先规则不变 |
| MIG-10 | 抽样 | 至少 30 条随机记录和所有高风险样本逐字段比对 |

### 7.3 功能回归

- SKU 和中文品名搜索。
- 多 SKU 批量查询及未命中提示。
- 海外备货单、FBA 货件关联。
- `.xlsx` 合法文件导入；错误扩展名、超限文件、空文件、损坏文件拒绝。
- 已有商品保存时的覆盖确认流程。
- 1、100、1,000 个商品导出；1,001 个必须明确拒绝。
- 导出文件能被 Excel 打开，金额、重量、箱数和总计正确。
- 操作日志记录操作人、业务类型、成功/失败结果；日志中不得出现数据库密码或敏感令牌。

### 7.4 非功能验收建议

- 通过正式 ERP 访问链路时，商品搜索服务端 P95 不高于 200 ms；端到端指标按现有 ERP SLO 验收。
- 1,000 商品导出在测试环境不超过 30 秒，内存无持续增长。
- Java 服务不可用时页面显示统一错误；不得回退直连旧 Flask。
- 迁移后对 `sku_key` 查询执行计划使用现有索引，不能全表扫描。
- 只通过 ERP 域名暴露功能；防火墙不开放 Flask `5000`。

## 8. 上线顺序

1. 产品/业务确认插件名称和角色范围；数据源固定为 `customsdeclaration.sql`，导出固定使用 ERP 现有格式。
2. 在测试库恢复 `jmh_data_platform` 脱敏副本，完整演练迁移和回滚。
3. 合并 PR 1，执行幂等 ERP 菜单 SQL，并只给测试角色授权。
4. 重新登录或刷新权限缓存，验证 `/getRouters`、ERP 动态路由和四个业务权限标识。
5. 生成正式迁移冲突报告，由数据负责人签字确认 `NEW_VALID` 数量。
6. 备份正式表，在维护窗口执行 PR 2 的 apply 脚本。
7. 完成功能、导出、权限和数据抽样验收。
8. 扩大角色授权；观察操作日志、错误率和导出耗时至少一个工作日。
9. 验收通过后归档暂存表、备份和旧项目；下线旧服务监听和旧库运行时凭据。

## 9. 回滚范围

### 菜单回滚

- 先删除新插件菜单树对应的 `sys_role_menu` 关系。
- 再按“F 子权限 -> 报关单生成器 C 菜单 -> 空的插件菜单 M 目录”顺序删除本次新增菜单。
- 如果一级“插件菜单”中已经存在其他插件，不得删除一级目录。
- 不删除原“运营/报关”入口、现有 Vue 组件、Java 接口或业务数据。

### 数据回滚

- 使用唯一批次 `updated_by` 删除本批新增行。
- 对迁移后被业务编辑的行，必须走备份差异恢复，禁止批量直接删除。
- 重新核对正式表总量、源类型分布、视图查询和随机样本。

## 10. 明确禁止项

- 不将旧 Flask 页面以 iframe 方式直接接入 ERP。
- 不开放 `5000` 端口给终端用户。
- 不保留匿名 `/api/init-db`、导入、修改接口。
- 不把数据库账号、密码或模板绝对路径写入代码/SQL文档。
- 不在 `jmh_data_platform` 新建正式泛化 `products` 表。
- 不让 ERP 运行时跨库查询旧 `customsdeclaration`。
- 不用 `REPLACE INTO` 或无审批的 `ON DUPLICATE KEY UPDATE` 覆盖存量。
- 不按固定 `menu_id` 写菜单迁移。
- 不自动给所有角色授予导入、编辑或导出权限。
- 不把盘点时的 1,904 候选数当成固定插入数量。

## 11. 最终验收口径

只有同时满足以下条件，才算完成接入：

1. 授权用户可从 ERP `插件菜单 > 报关单生成器` 直接进入原生页面。
2. 未授权用户在菜单、按钮和直接 API 三层均被拒绝。
3. 用户访问链路只经过正式 ERP，不依赖内网页面、Python、旧 Flask、旧数据库或硬编码本机路径。
4. 迁移数据每行有分类、来源和批次追溯；空 SKU、源内重复和 ERP 冲突没有被静默写入。
5. 迁移前后数量可核对，脚本可重跑、可回滚。
6. 搜索、关联、导入、编辑、导出和审计日志全部通过测试。
7. ERP 现有 Excel 导出内容通过业务验收，并对至少 30 条迁移数据抽样签字确认；不要求旧单页版式一致。
