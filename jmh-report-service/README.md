# JMH Report Service

Python FastAPI 报表服务，负责 jmh_report 报表库、ETL、数据分析接口和任务监控接口。

## Dev Start

```bash
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 9000 --reload
```

## Health

```text
GET /health
GET /health/db
```
