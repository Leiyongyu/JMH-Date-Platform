# 报关单生成系统（Date-Project 子应用）

本目录由原 `D:\JMH\项目\JMH\customs_declaration` 迁入，页面、导入、批量查询、
商品编辑和 Excel 导出逻辑保持原样。正式环境由 `backend.main` 挂载到：

`/customs-declaration/`

## 数据与配置

- 数据表固定使用 `${SHOP_SOURCE_DATABASE:-jmh_data_platform}.products`。
- 数据库主机、端口、账号和密码统一读取 Date-Project 根目录 `.env` 中的
  `MYSQL_HOST`、`MYSQL_PORT`、`MYSQL_USER`、`MYSQL_PASSWORD`。
- 不包含旧项目硬编码数据库密码。
- Excel 模板位于 `assets/customs-declaration-template.xlsx`，不依赖外部绝对路径。

## 启动

正式环境随 Date-Project 一起启动，无需单独启动 5000 端口：

```powershell
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8010
```

`启动.bat` 和 `server.py` 仅保留给本机独立调试，并只监听 `127.0.0.1:5000`。
ERP 用户通过 Java 白名单代理访问，不能直接调用此子应用。
