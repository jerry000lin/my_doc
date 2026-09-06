# FastAPI 项目初始化流程

## 1. 目标

本文记录一个现代 Python FastAPI 后端项目从零初始化到可运行、可测试、可接数据库迁移的基本流程。

当前推荐组合：

```text
FastAPI
uv
SQLAlchemy
Alembic
PostgreSQL
pytest
```

FeatureMaker 当前后端就在这个方向上推进。

---

## 2. 推荐目录结构

一个轻量后端可以先这样放：

```text
apps/backend/
  featuremaker/
    __init__.py
    main.py
    config.py
    db.py
    models/
      __init__.py
    routers/
      __init__.py
      health.py
  tests/
    test_health.py
  alembic/
    env.py
    versions/
  alembic.ini
  pyproject.toml
  uv.lock
```

几个目录的职责：

| 路径 | 作用 |
| --- | --- |
| `featuremaker/main.py` | FastAPI 应用入口 |
| `featuremaker/config.py` | 配置对象和环境变量 |
| `featuremaker/db.py` | SQLAlchemy engine、session、Base |
| `featuremaker/models/` | ORM 模型 |
| `featuremaker/routers/` | API 路由 |
| `tests/` | 测试 |
| `alembic/` | 数据库迁移 |

---

## 3. 初始化 uv 项目

进入后端目录：

```bash
mkdir -p apps/backend
cd apps/backend
```

初始化 Python 项目：

```bash
uv init --package
```

如果项目已经有 `pyproject.toml`，不要重复初始化，直接安装依赖即可。

---

## 4. 安装依赖

基础依赖：

```bash
uv add "fastapi[standard]" uvicorn pydantic-settings sqlalchemy "psycopg[binary]" alembic
```

开发依赖：

```bash
uv add --dev pytest httpx
```

这些依赖分别解决：

| 依赖 | 作用 |
| --- | --- |
| `fastapi[standard]` | FastAPI 框架和开发命令 |
| `uvicorn` | ASGI 服务 |
| `pydantic-settings` | 环境变量配置 |
| `sqlalchemy` | ORM 和数据库访问 |
| `psycopg[binary]` | PostgreSQL 驱动 |
| `alembic` | 数据库迁移 |
| `pytest` | 测试框架 |
| `httpx` | FastAPI TestClient 依赖 |

---

## 5. 创建最小 FastAPI 应用

`featuremaker/main.py`：

```python
from fastapi import FastAPI

from featuremaker.routers.health import router as health_router

app = FastAPI(title="FeatureMaker API")

app.include_router(health_router)
```

`featuremaker/routers/health.py`：

```python
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

本地启动：

```bash
uv run uvicorn featuremaker.main:app --reload
```

访问：

```text
http://127.0.0.1:8000/health
```

---

## 6. 配置对象

`featuremaker/config.py`：

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/featuremaker"

    model_config = SettingsConfigDict(env_file=".env", env_prefix="FEATUREMAKER_")


settings = Settings()
```

这样可以通过环境变量覆盖配置：

```bash
export FEATUREMAKER_DATABASE_URL="postgresql+psycopg://user:password@127.0.0.1:5432/featuremaker"
```

---

## 7. 数据库基础设施

`featuremaker/db.py`：

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from featuremaker.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

这几个对象的含义：

| 对象 | 作用 |
| --- | --- |
| `Base` | 所有 ORM 模型的基类 |
| `engine` | 数据库连接入口 |
| `SessionLocal` | 创建数据库会话 |
| `get_db` | FastAPI 依赖注入，给 API 使用数据库 session |

---

## 8. 初始化 Alembic

在 `apps/backend` 下执行：

```bash
uv run alembic init alembic
```

会生成：

```text
alembic.ini
alembic/
  env.py
  script.py.mako
  versions/
```

然后修改 `alembic/env.py`，让 Alembic 能找到 ORM 的 `Base.metadata`。

核心思路：

```python
from featuremaker.db import Base
import featuremaker.models

target_metadata = Base.metadata
```

注意：`import featuremaker.models` 的作用是让模型类被加载，否则 Alembic 可能看不到表。

---

## 9. 创建 ORM 模型

示例：

```python
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from featuremaker.db import Base


class Workflow(Base):
    __tablename__ = "workflows"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
```

在 `featuremaker/models/__init__.py` 中导入：

```python
from featuremaker.models.workflow import Workflow

__all__ = ["Workflow"]
```

---

## 10. 生成和应用迁移

生成 migration：

```bash
uv run alembic revision --autogenerate -m "创建工作流表"
```

人工检查 `alembic/versions/*.py`：

```text
是否只包含本次想改的表
字段类型是否正确
JSONB / index / unique 是否正确
downgrade 是否能反向删除
```

应用 migration：

```bash
uv run alembic upgrade head
```

查看当前版本：

```bash
uv run alembic current
```

检查数据库是否和 ORM 一致：

```bash
uv run alembic check
```

---

## 11. 写最小测试

`tests/test_health.py`：

```python
from fastapi.testclient import TestClient

from featuremaker.main import app


def test_health() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

运行测试：

```bash
uv run python -m pytest
```

---

## 12. FeatureMaker 当前常用命令

进入后端目录：

```bash
cd FeatureMaker/apps/backend
```

安装依赖：

```bash
uv sync
```

运行测试：

```bash
uv run python -m pytest
```

启动服务：

```bash
uv run uvicorn featuremaker.main:app --reload
```

生成 migration：

```bash
bash bin/db/1-make-migration.sh "迁移说明"
```

生成离线 SQL：

```bash
bash bin/db/2-build-sql.sh
```

检查数据库版本和 ORM 一致性：

```bash
bash bin/db/3-check.sh
```

---

## 13. 常见判断

### 13.1 `python main.py` 为什么没有反应

FastAPI 项目通常不是直接执行 `main.py`，而是用 ASGI 服务启动：

```bash
uv run uvicorn featuremaker.main:app --reload
```

### 13.2 `fastapi dev` 和 `uvicorn` 怎么选

开发中两种都可以。

当前 FeatureMaker 统一用：

```bash
uv run uvicorn featuremaker.main:app --reload
```

原因是命令更直接，不依赖 FastAPI CLI 的额外行为。

### 13.3 Alembic 什么时候用

只要数据库表结构来自 ORM，就应该用 Alembic 管迁移。

基本流程：

```text
改 ORM Model
生成 migration
人工检查 migration
应用 migration 或生成离线 SQL
检查数据库版本和 ORM 是否一致
```

### 13.4 PostgreSQL 和 JSONB 怎么搭配

稳定字段用普通列：

```text
id
name
status
created_at
workflow_id
```

变化快的结构用 JSONB：

```text
workflow graph
node config
node inputs
node outputs
schema_json
```

大内容不要塞 JSONB，放文件或对象存储，只在数据库里保存 URI。

---

## 14. 最小闭环

一个 FastAPI 后端初始化完成，至少应该能做到：

```text
1. uv sync 成功
2. uv run python -m pytest 成功
3. uv run uvicorn featuremaker.main:app --reload 能启动
4. /health 能访问
5. Alembic 能 current / upgrade / check
6. ORM 模型能被 Alembic 自动发现
```
