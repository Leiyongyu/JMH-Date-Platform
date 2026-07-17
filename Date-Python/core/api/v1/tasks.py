"""任务型 API 路由 — POST /api/v1/tasks + GET /api/v1/tasks/{id}

当前委托给旧 api/v1_router.py，新任务类型可优先在此文件注册。
"""
# 兼容期：所有任务路由仍由 api/v1_router.py 处理
# 新模块的任务处理器注册入口：
from api.v1_router import router  # noqa: F401 — 保持旧路由在主应用中可用
