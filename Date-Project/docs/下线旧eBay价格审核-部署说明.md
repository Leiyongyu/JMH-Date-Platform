# 下线旧SOP eBay SP价格批量审核

## 执行范围

2026-09-15：用户要求“先推送，再删除”。

- 删除前已推送上一轮谷仓接入，GitHub main提交：`d6da26e6e7c464ccf8256597b4b46b80942f9219`。
- 本轮删除旧ERP页面及其专属API、Java控制器、审核/查询/导出/导入服务、
  DTO、Mapper和独立线程池，共20个源文件，并清理7个专属配置项。
- 移除旧安装SQL的菜单/权限初始化部分，避免再次执行旧脚本恢复废弃入口。
- 删除改动与本说明一起提交发布；删除前版本已在Git中，可恢复代码。
- 不改Python eBay工具、脚本注册表、Java `/sop/ebay-tool/proxy`、新脚本权限。
- 竞品分析仍使用的 `EbayBrowseApiClient`、`EbayOAuthTokenProvider` 及共享凭证、超时、
  详情重试配置保留，不能一起删。
- 旧审核业务表和数据全部保留：
  `ebay_price_audit_task`、`ebay_price_audit_oe`、`ebay_price_audit_item`、
  `dim_ebay_sku_oe_mapping`。本轮没有删除业务数据。

## 部署SQL

仓库文件：`RuoYi-Vue-springboot3/sql/20260915_remove_legacy_ebay_sp_price_menu.sql`。

部署副本：`D:\JMH\项目\部署sql\14_删除旧eBay_SP价格审核菜单.sql`。
本说明同步为 `部署说明_删除旧eBay_SP价格审核菜单.md`。

脚本在 `jmh_data_platform` 执行，仅撤销旧权限：

- `scripts:ebayPrice:list`
- `scripts:ebayPrice:query`
- `scripts:ebayPrice:import`
- `scripts:ebayPrice:export`

同时识别旧路由 `ebay-sp-price`、组件 `scripts/ebayPrice/index`、
路由名 `EbaySpPrice`。不依赖本地menu_id，不按含“eBay”的菜单名模糊删除。
父级SOP目录、脚本菜单及 `sop:ebayTool:use` 明确保留。

删除前在同库备份到：

- `bak_sys_menu_ebay_sp_20260915`
- `bak_sys_role_menu_ebay_sp_20260915`

重复执行不会覆盖原备份，也不会重复删除其他权限。
如果旧菜单下面出现未知子菜单，安全检查会产生Duplicate entry错误并阻止删除；
需要先人工确认、迁移未知子菜单，不能忽略该错误强行清理。
后续DELETE另有safe条件，即使客户端继续执行也不会越过这一保护。

## 上线顺序

1. 备份并部署本轮代码。
2. 执行上述14号菜单清理SQL，确认输出目标仅为旧SP页面和按钮。
3. Java必须clean后重新打包，替换JAR并重启；不能仅增量打包留下已删除的class或Mapper。
4. 构建并发布ERP前端dist，退出登录后重新登录，以刷新路由和用户权限缓存。
5. 检查脚本菜单中的“eBay价格查询”仍可打开。
6. Python脚本组件没有修改，不需要因本次下线重新部署Python前端。

清理SQL只改数据库菜单，不会热卸载已启动Java进程里的旧控制器；
彻底关闭旧 `/operation/ebay-price/**` 接口需部署新JAR并重启。
不要通过放宽新脚本权限来解决旧缓存；新权限始终为 `sop:ebayTool:use`。

## 只读检查

```sql
SELECT menu_id,parent_id,menu_name,perms
FROM jmh_data_platform.sys_menu
WHERE perms IN ('scripts:ebayPrice:list','scripts:ebayPrice:query',
                'scripts:ebayPrice:import','scripts:ebayPrice:export');
-- 预期0行。

SELECT menu_id,parent_id,menu_name,perms
FROM jmh_data_platform.sys_menu
WHERE perms IN ('sop:scriptTools:view','sop:ebayTool:use');
-- 新脚本入口应保留；其原有sys_role_menu分配不变。

SELECT COUNT(*) FROM jmh_data_platform.bak_sys_menu_ebay_sp_20260915;
SELECT COUNT(*) FROM jmh_data_platform.bak_sys_role_menu_ebay_sp_20260915;
```

## 本地执行记录

已执行同一份SQL：删除4条旧菜单（本地2124—2127）、8条角色授权，
备份分别为4行和8行。旧权限剩余0条。
新脚本菜单和角色授权执行前后逐行一致。
未删除业务表、历史任务、图片或Excel文件，未重启服务。
Java clean compile及ERP前端生产构建均通过，未运行测试；已确认构建产物不含旧审核控制器/Mapper。

## 恢复说明

代码可从删除前提交d6da26e恢复。数据库菜单可从上述两张备份表恢复，
但恢复前必须核对menu_id未被占用、父目录仍存在；不要直接覆盖后续新菜单。
还原菜单时需同时还原旧前端和Java，否则会形成可见但不可用的入口。
无需恢复历史业务数据，因为本轮未删除这些数据。
