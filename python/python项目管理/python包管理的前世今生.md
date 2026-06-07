# 现代 Python 项目管理：从 `pip install` 到 `uv`

Python 项目管理负责三件事：隔离运行环境、声明项目依赖、复现安装结果。它解决的是“同一份代码在不同机器、不同成员、不同时间下能稳定运行”的问题。

`pip install` 适合临时验证一个包；`venv` 适合隔离项目环境；`requirements.txt` 适合保存安装清单；`pyproject.toml` 适合声明项目本身；`uv` 把环境创建、依赖声明、锁文件生成、环境同步和命令运行收敛到一套项目工作流中。

对于普通 Python 应用、自动化脚本、数据处理 Pipeline、Web API、小型机器学习项目，可以默认采用：

```text
pyproject.toml + uv.lock + .venv + uv
```

涉及 CUDA、MKL、复杂系统库或非 Python 二进制依赖时，Conda、Mamba 或 Pixi 仍然有使用价值。只写一次性脚本、不会提交仓库、不会跨机器运行时，直接 `pip install` 的成本更低。

---

## 1. 工具职责与边界

| 工具 / 文件 | 核心职责 | 输入 | 输出 | 边界 |
| --- | --- | --- | --- | --- |
| `pip install` | 把包装进当前 Python 环境 | 包名、版本约束 | `site-packages` 中的已安装包 | 不区分项目，不负责环境隔离 |
| `venv` | 创建项目级虚拟环境 | Python 解释器、目标目录 | `.venv` | 不记录项目依赖 |
| `requirements.txt` | 记录安装清单 | 当前环境中的包 | 包名和精确版本列表 | 容易混合直接依赖和间接依赖 |
| `pyproject.toml` | 声明项目元数据、Python 版本、直接依赖和工具配置 | 项目配置 | 可提交到 Git 的项目声明 | 不执行安装 |
| `uv.lock` | 锁定完整依赖解析结果 | `pyproject.toml`、包索引元数据 | 精确版本和依赖树 | 不手写维护 |
| `uv` | 管理项目环境、依赖、锁文件和运行命令 | 项目配置、锁文件、命令参数 | `.venv`、更新后的锁文件、运行结果 | 团队需要统一使用方式 |

推荐记住这条链路：

```text
pyproject.toml  声明项目需要什么
uv.lock         锁定最终安装什么
.venv           承载实际安装环境
uv              负责创建、解析、同步、运行
```

---

## 2. 从 `pip install` 到 `uv` 的问题演进

### 2.1 `pip install` 只管理当前环境

```bash
pip install requests
python main.py
```

这组命令可以让脚本跑起来，但依赖被安装到了“当前 Python 环境”。如果这个环境是全局 Python，所有项目都会共享同一套包。

典型冲突如下：

```text
risk-feature-pipeline 需要 pandas==2.x
legacy-report-job     需要 pandas==1.x
```

全局环境只能安装一个 `pandas` 版本。升级一个项目的依赖，可能破坏另一个项目。

### 2.2 `venv` 解决环境隔离

```bash
python -m venv .venv
source .venv/bin/activate
pip install pandas openpyxl
```

Windows PowerShell：

```bash
.venv\Scripts\Activate.ps1
```

`venv` 会在项目目录下创建独立环境：

```text
risk-feature-pipeline/
  .venv/
  main.py
```

依赖会安装到当前项目的 `.venv`，不会污染全局 Python。它的边界也很明确：`.venv` 只保存本机安装结果，不告诉别人这个项目应该安装哪些包。

### 2.3 `requirements.txt` 解决初步复现

```bash
pip freeze > requirements.txt
pip install -r requirements.txt
```

`requirements.txt` 能让别人安装同一批包，但 `pip freeze` 导出的是环境快照，常见结果如下：

```text
certifi==2025.1.31
charset-normalizer==3.4.1
idna==3.10
requests==2.32.3
urllib3==2.3.0
```

如果业务代码只写了：

```python
import requests
```

项目的直接依赖只有 `requests`。`certifi`、`urllib3` 等是 `requests` 的间接依赖。直接依赖和间接依赖混在一起后，会带来两个维护问题：

```text
无法快速判断业务代码真正依赖哪些包
删除直接依赖后，间接依赖可能残留在环境中
```

例如：

```bash
pip uninstall requests
```

该命令只卸载 `requests` 本身，不会自动清理所有由它引入且不再使用的间接依赖。

### 2.4 `pyproject.toml` 声明项目本身

`pyproject.toml` 描述项目需要什么，而不是当前环境装了什么。

```toml
[project]
name = "risk-feature-pipeline"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "pandas>=2.2.0",
    "openpyxl>=3.1.0",
    "requests>=2.32.0"
]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"
```

`dependencies` 只放项目直接依赖。代码直接使用 `pandas`、`openpyxl`、`requests`，就把它们写进去；这些包自身依赖的包交给解析工具处理。

工具配置也可以放到同一个文件：

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.ruff]
line-length = 100

[tool.mypy]
python_version = "3.10"
```

`pyproject.toml` 只负责声明。创建环境、解析依赖、安装依赖和运行代码，需要由 `uv`、`pip`、`build` 等工具执行。

### 2.5 `uv.lock` 锁定精确版本

`pyproject.toml` 通常写版本范围：

```toml
dependencies = [
    "requests>=2.32.0"
]
```

真正安装时，需要确定 `requests` 的具体版本，以及它依赖的 `urllib3`、`certifi` 等包的具体版本。`uv.lock` 记录最终解析结果：

```text
直接依赖的精确版本
间接依赖的精确版本
完整依赖树
可复现安装所需的元数据
```

团队协作项目应提交 `uv.lock`。这样新成员、CI 环境、部署机器执行 `uv sync` 时，可以得到一致的依赖环境。

---

## 3. 推荐项目工作流

### 3.1 初始化项目

```bash
uv init risk-feature-pipeline
cd risk-feature-pipeline
```

初始结构通常类似：

```text
risk-feature-pipeline/
  README.md
  pyproject.toml
  main.py
```

长期维护项目可以采用 `src` 布局：

```text
risk-feature-pipeline/
  README.md
  pyproject.toml
  uv.lock
  src/
    risk_feature_pipeline/
      __init__.py
      main.py
  tests/
    test_main.py
```

### 3.2 添加运行依赖

```bash
uv add pandas openpyxl requests
```

这个命令会同时完成四件事：

```text
把依赖写入 pyproject.toml
解析直接依赖和间接依赖
更新 uv.lock
同步项目 .venv
```

不要先 `pip install`，再手动补 `pyproject.toml`。这种流程容易造成项目声明、锁文件和本地环境不一致。

### 3.3 添加开发依赖

```bash
uv add --dev pytest ruff mypy
```

开发依赖用于测试、格式化、静态检查，不属于运行时业务依赖。它们应该和业务依赖分开管理，避免部署环境安装不必要工具。

### 3.4 同步环境

```bash
uv sync
```

适用场景：

```text
刚 clone 仓库
切换分支后依赖变化
别人提交了新的 uv.lock
CI 安装依赖
编辑器识别不到依赖
```

`uv sync` 根据 `pyproject.toml` 和 `uv.lock` 同步 `.venv`，让本地环境回到项目声明的状态。

### 3.5 运行命令

```bash
uv run python main.py
uv run pytest
uv run ruff check .
```

`uv run` 在项目环境中执行命令，减少误用全局 Python 或其他虚拟环境的概率。

### 3.6 删除依赖

```bash
uv remove requests
```

该命令会从项目依赖声明中删除包，并重新同步锁文件和环境。相比手动卸载，它更容易保持 `pyproject.toml`、`uv.lock`、`.venv` 三者一致。

---

## 4. 一个可维护项目的最小配置

### 4.1 `pyproject.toml`

```toml
[project]
name = "risk-feature-pipeline"
version = "0.1.0"
description = "Build offline risk features from Excel and API sources."
requires-python = ">=3.10"
dependencies = [
    "pandas>=2.2.0",
    "openpyxl>=3.1.0",
    "requests>=2.32.0"
]

[dependency-groups]
dev = [
    "pytest>=8.0.0",
    "ruff>=0.5.0",
    "mypy>=1.10.0"
]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.ruff]
line-length = 100

[tool.mypy]
python_version = "3.10"
ignore_missing_imports = true

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"
```

### 4.2 `.gitignore`

```gitignore
.venv/
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
.mypy_cache/
```

### 4.3 应提交和不应提交的文件

应提交：

```text
README.md
pyproject.toml
uv.lock
src/ 或 main.py
tests/
```

不应提交：

```text
.venv/
__pycache__/
.pytest_cache/
.ruff_cache/
.mypy_cache/
```

---

## 5. 常见问题与排查

### 5.1 手动改了 `pyproject.toml`，但代码仍然报 `ModuleNotFoundError`

原因通常是本地 `.venv` 没有同步。

处理方式：

```bash
uv sync
uv run python main.py
```

### 5.2 运行时使用了错误的 Python

检查当前命令使用的解释器：

```bash
uv run python -c "import sys; print(sys.executable)"
```

输出路径应指向项目 `.venv`。

### 5.3 编辑器识别不到依赖

先同步环境：

```bash
uv sync
```

然后在 VS Code 或 PyCharm 中选择项目 `.venv` 里的 Python 解释器。

### 5.4 `requirements.txt` 还能不能用

可以保留在以下场景：

```text
老项目迁移期
某些部署平台只识别 requirements.txt
需要给外部系统提供兼容安装清单
```

新项目不建议把它作为核心依赖声明。核心声明应放在 `pyproject.toml`，精确安装结果应放在锁文件。

### 5.5 什么时候不适合 uv

以下场景需要评估 Conda、Mamba、Pixi 或容器方案：

```text
依赖 CUDA、cuDNN、GPU 驱动
依赖复杂系统库或 C/C++ 二进制包
需要同时管理 Python、R、系统命令行工具
公司已有统一 Conda 镜像和发布规范
```

uv 主要解决 Python 项目依赖和环境工作流。系统级运行时、驱动和复杂二进制依赖不应该强行交给 uv 兜底。

---

## 6. 面试和复盘可用回答

### `pip install` 的主要问题是什么

`pip install` 把包装进当前环境。当前环境如果是全局 Python，不同项目会共享依赖版本，容易出现版本冲突和环境污染。它解决装包问题，不解决项目级依赖管理。

### 为什么需要 `venv`

`venv` 为每个项目创建独立 Python 环境。项目 A 的依赖安装到项目 A 的 `.venv`，项目 B 的依赖安装到项目 B 的 `.venv`，两个项目不会因为同名依赖版本不同而互相影响。

### `requirements.txt` 的局限是什么

`pip freeze` 生成的 `requirements.txt` 是环境快照，会记录直接依赖和间接依赖。项目迭代后，开发者很难判断某个包来自业务代码，还是历史依赖残留。

### `pyproject.toml` 解决什么问题

`pyproject.toml` 用标准格式声明项目名称、版本、Python 版本要求、直接依赖、构建系统和工具配置。它让依赖管理从“保存当前环境”转向“声明项目需求”。

### `pyproject.toml` 和 `uv.lock` 有什么区别

`pyproject.toml` 写项目依赖范围，例如 `requests>=2.32.0`。`uv.lock` 写最终解析出的精确版本和完整依赖树。前者面向项目声明，后者面向环境复现。

### `uv add` 和 `pip install` 有什么区别

`pip install requests` 主要把 `requests` 安装到当前环境。`uv add requests` 会把依赖写入 `pyproject.toml`，更新 `uv.lock`，并同步项目 `.venv`。

### `uv sync` 什么时候用

刚 clone 项目、切换分支、依赖文件变更、CI 安装依赖、编辑器识别不到包时，执行：

```bash
uv sync
```

它会根据项目声明和锁文件同步本地环境。

### 为什么推荐 `uv run`

`uv run` 在项目环境里执行命令，能减少误用全局 Python 或错误虚拟环境的问题。团队协作时，统一使用 `uv run` 也能降低“我本地能跑、你本地不能跑”的概率。

---

## 7. 最小命令速查

新项目：

```bash
uv init risk-feature-pipeline
cd risk-feature-pipeline
uv add pandas openpyxl requests
uv run python main.py
```

团队协作：

```bash
git clone <repo>
cd <repo>
uv sync
uv run python main.py
```

依赖变更：

```bash
uv add package-name
uv remove package-name
uv sync
```

质量检查：

```bash
uv add --dev pytest ruff mypy
uv run pytest
uv run ruff check .
uv run mypy src
```

最终判断标准：项目依赖写在 `pyproject.toml`，精确版本锁在 `uv.lock`，本地环境由 `.venv` 承载，所有安装和运行动作通过 `uv` 收敛。这样维护成本集中在项目文件上，而不是分散在每个开发者的本机环境里。

---

## 参考资料

- Python Packaging User Guide: Writing your `pyproject.toml`
- Astral uv Docs: Working on projects
- Astral uv Docs: Locking and syncing
