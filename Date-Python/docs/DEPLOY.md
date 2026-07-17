# JMH 退税数据服务 — 部署指南

## 环境要求

| 组件 | 版本 | 必须 |
|------|------|------|
| Python | **3.12**（不要用 3.14 预发布版） | ✅ |
| MySQL | 8.0+ | ✅ |
| Java | 17+（若依 ERP 后端） | 可选 |
| Node | 18+（Vue3 前端） | 可选 |

> Python 服务是核心，Java 和 Vue 是若依 ERP 的配套项目，如果只用测试页面可以不要。

---

## 1. 部署 Python 服务

### 1.1 复制项目
```powershell
# 把 Date-Python 整个目录复制到目标机器
xcopy /E /I D:\JMH\项目\JMH-Date-Platform\Date-Python D:\Deploy\Date-Python
```

### 1.2 安装 Python 依赖
```powershell
cd D:\Deploy\Date-Python
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 1.3 配置数据库
```powershell
# 1. 在目标机器 MySQL 中创建数据库
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS export_tax_refund DEFAULT CHARACTER SET utf8mb4"

# 2. 导入表结构
mysql -u root -p export_tax_refund < sql\init_database.sql

# 3. 执行增量迁移
mysql -u root -p export_tax_refund < sql\20260716_task_reliability.sql

# 4. 添加进货表的申报字段
mysql -u root -p export_tax_refund -e "
  ALTER TABLE purchase_inventory
    ADD COLUMN IF NOT EXISTS declaration_month CHAR(6) NULL AFTER inventory_status,
    ADD COLUMN IF NOT EXISTS declaration_batch CHAR(3) NULL AFTER declaration_month,
    ADD COLUMN IF NOT EXISTS sequence_no CHAR(8) NULL AFTER declaration_batch,
    ADD COLUMN IF NOT EXISTS relation_no VARCHAR(40) NULL AFTER sequence_no;
"
```

### 1.4 配置环境变量
```powershell
# 复制配置模板
copy .env.example .env

# 编辑 .env，填入真实密码
notepad .env
```

`.env` 内容：
```
JMH_DB_PASSWORD=你的数据库密码
JMH_JMH_DB_PASSWORD=你的数据库密码
```

### 1.5 启动服务
```powershell
# 开发模式（文件修改自动重载）
.venv\Scripts\python app.py

# 或指定端口
$env:PORT=5001; .venv\Scripts\python app.py
```

### 1.6 设为 Windows 服务（开机自启）
```powershell
# 使用 NSSM（https://nssm.cc/）
nssm install JMH-TaxRefund D:\Deploy\Date-Python\.venv\Scripts\python.exe
nssm set JMH-TaxRefund AppDirectory D:\Deploy\Date-Python
nssm set JMH-TaxRefund AppParameters app.py
nssm start JMH-TaxRefund
```

---

## 2. 验证

```powershell
# 健康检查
curl http://127.0.0.1:5000/api/v1/tasks?page_size=1

# Swagger 文档
start http://127.0.0.1:5000/docs

# 测试页面
start http://127.0.0.1:5000/test-ui
```

---

## 3. 可选：部署 Java ERP + Vue 前端

如果已在另一台机器部署了若依 ERP，只需在 Java 配置文件中指向 Python 服务：

```yaml
# application.yml
tax-refund:
  python:
    base-url: http://<python-host>:5000/api/v1
    connect-timeout: 5000
    read-timeout: 300000
```

---

## 4. 注意事项

- **Python 版本**：务必用 3.12.x，3.14 预发布版有兼容问题
- **防火墙**：确保 5000 端口对 ERP 服务器开放
- **文件路径**：`.env` 中的 `JMH_UPLOAD_DIR` 如果改过，目标机器也需要对应目录
- **退税输出目录**：汇总生成时的 `output_parent_dir` 需要是 Python 服务所在机器可写的路径
