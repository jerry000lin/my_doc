# LangChain Text Splitter 交互式案例

这个目录用同一份 Markdown 对比三种 `langchain-text-splitters` 集成和一种组合策略：

| 切分器 | 核心思路 | 适合场景 | 关键观察点 |
| --- | --- | --- | --- |
| `RecursiveCharacterTextSplitter` | 按分隔符优先级递归切分 | 通用文本、RAG 默认起点 | 尽量不破坏段落和句子，空字符串用于最终兜底 |
| `CharacterTextSplitter` | 只使用单个分隔符 | 格式非常固定的文本 | `chunk_size` 是合并目标，不保证能拆开超长段落 |
| `MarkdownHeaderTextSplitter` | 按 H1～H6 标题结构切分 | 技术文档、知识库文档 | 标题路径进入 `metadata`，它本身不按固定字符数切分 |
| `MarkdownHeader + Recursive` | 先按标题拆章节，再在章节内递归切分 | 结构清晰但章节较长的 RAG 文档 | 每个最终 chunk 都继承完整标题路径，同时限制正文长度 |

## 运行页面

本项目使用 uv 管理依赖：

```bash
cd doc/个人复习文档/大模型/langchain/TextSplitter
uv sync
uv run streamlit run app.py
```

浏览器打开终端显示的地址（通常是 <http://localhost:8501>）。修改左侧参数或 Markdown 内容后，Streamlit 会自动重新执行并刷新结果。

运行测试：

```bash
uv run pytest
```

## 参数怎么理解

### chunk_size 与 chunk_overlap

- `chunk_size`：目标 chunk 的最大长度，这里用 Python 的 `len` 统计字符数。
- `chunk_overlap`：相邻 chunk 尽量保留的重复内容，用来降低关键信息恰好落在边界处的风险。
- `chunk_overlap` 必须小于 `chunk_size`，重叠过大会增加向量库容量和召回结果冗余。

`CharacterTextSplitter` 先在指定分隔符处切开，再尝试把相邻短片段合并到接近 `chunk_size`；因此“遇到分隔符”不代表最终一定产生一个独立 chunk。假如一整个段落都没有分隔符，即使它超过 `chunk_size`，切分器也不会从段落中间强行截断。`RecursiveCharacterTextSplitter` 的默认分隔符列表最后包含空字符串，因此最终可以退化到逐字符切分。

### Markdown 标题 metadata

按标题切分时，以下内容：

```markdown
# 用户指南
## 安装
安装步骤……
```

会得到类似结果：

```json
{
  "page_content": "安装步骤……",
  "metadata": {"H1": "用户指南", "H2": "安装"}
}
```

metadata 可以参与过滤、引用展示或混合检索。标题切分后的章节仍可能太长，因此本案例实现了两阶段策略：

1. 先用 `MarkdownHeaderTextSplitter` 保留章节结构和标题 metadata。
2. 再用 `RecursiveCharacterTextSplitter.split_documents()` 对超长章节做二次切分，让 metadata 继续传递。

组合切分入口是 `split_markdown_then_recursive()`。最终 metadata 示例：

```json
{
  "H1": "用户指南",
  "H2": "安装",
  "header_path": "用户指南 > 安装",
  "section_index": 2,
  "section_chunk_index": 1,
  "start_index": 0
}
```

- `header_path`：按 H1～H6 顺序拼接的完整标题路径。
- `section_index`：标题切分后章节的序号。
- `section_chunk_index`：当前 chunk 在章节内部的序号。
- `start_index`：当前 chunk 在章节正文中的相对起点，不是原始 Markdown 的绝对位置。

界面还可以把 `标题路径：用户指南 > 安装` 前置到每个 chunk 正文，让 Embedding 模型直接感知章节语境。因为前置发生在递归切分之后，所以前缀长度不计入 `chunk_size`。

## 代码结构

- `app.py`：Streamlit 页面与交互参数。
- `splitters.py`：三种切分器的独立封装，可脱离页面复用。
- `sample.md`：页面默认加载的 Markdown 示例。
- `tests/test_splitters.py`：核心行为测试。

## 建议练习

1. 给页面增加“按 token 计数”选项，对比字符长度与 token 长度的区别。
2. 尝试让标题路径前缀也计入 `chunk_size`，比较实现复杂度和最终召回效果。
3. 给每个 chunk 生成稳定 ID（如文档 ID、标题路径和 chunk 序号的哈希），思考文档更新后的增量索引策略。
