"""LangChain Text Splitter 的 Streamlit 交互式学习页面。"""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from splitters import (
    Chunk,
    parse_separator,
    parse_separators,
    split_character,
    split_markdown_headers,
    split_markdown_then_recursive,
    split_recursive,
)

ROOT = Path(__file__).parent
SAMPLE_MARKDOWN = (ROOT / "sample.md").read_text(encoding="utf-8")

SPLITTER_HELP = {
    "RecursiveCharacterTextSplitter": "按分隔符优先级递归尝试，适合作为通用文本切分默认方案。",
    "CharacterTextSplitter": "只按一个分隔符切分，便于观察 chunk_size 并不等于强制截断。",
    "MarkdownHeaderTextSplitter": "按标题结构切分，并将标题层级保存到 metadata。",
    "MarkdownHeader + Recursive": "先保留章节结构，再限制章节内 chunk 长度，并为每个 chunk 补全标题路径。",
}

st.set_page_config(page_title="Text Splitter 实验台", page_icon="✂️", layout="wide")
st.markdown(
    """
    <style>
    .block-container {padding-top: 2rem; max-width: 1500px;}
    [data-testid="stMetric"] {background: #f7f8fa; border: 1px solid #e6e8eb;
        border-radius: 12px; padding: 12px 16px;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("✂️ LangChain Text Splitter 实验台")
st.caption("输入 Markdown、调整参数，并立即观察不同切分策略的 chunk 与 metadata。")

with st.sidebar:
    st.header("切分配置")
    splitter_name = st.selectbox("Splitter", options=list(SPLITTER_HELP))
    st.info(SPLITTER_HELP[splitter_name])

    options: dict[str, object] = {}
    if splitter_name in {
        "RecursiveCharacterTextSplitter",
        "CharacterTextSplitter",
        "MarkdownHeader + Recursive",
    }:
        options["chunk_size"] = st.number_input(
            "chunk_size（字符数）", min_value=1, max_value=10000, value=300, step=50
        )
        options["chunk_overlap"] = st.number_input(
            "chunk_overlap（字符数）", min_value=0, max_value=9999, value=50, step=10
        )
        options["keep_separator"] = st.checkbox("保留分隔符", value=True)

    if splitter_name in {"RecursiveCharacterTextSplitter", "MarkdownHeader + Recursive"}:
        separator_text = st.text_area(
            "分隔符优先级（每行一个）",
            value="\\n\\n\n\\n\n。\n！\n？\n空格\n<EMPTY>",
            help="从上到下依次尝试；“空格”代表空格，<EMPTY> 是逐字符兜底。",
            height=190,
        )
        options["separators"] = [
            " " if item == "空格" else item for item in parse_separators(separator_text)
        ]
    if splitter_name == "CharacterTextSplitter":
        separator = st.text_input(
            "separator", value="\\n\\n", help=r"可使用 \n、\t、\r 转义符。"
        )
        options["separator"] = parse_separator(separator)
    if splitter_name in {"MarkdownHeaderTextSplitter", "MarkdownHeader + Recursive"}:
        selected_headers = st.multiselect(
            "参与切分的标题层级",
            options=list(range(1, 7)),
            default=[1, 2, 3],
            format_func=lambda level: f"H{level}（{'#' * level}）",
        )
        options["header_levels"] = selected_headers
        options["strip_headers"] = st.checkbox("从 chunk 正文移除标题", value=True)
        if splitter_name == "MarkdownHeaderTextSplitter":
            options["return_each_line"] = st.checkbox("每个内容行单独返回", value=False)
        else:
            options["header_path_separator"] = st.text_input(
                "标题路径分隔符", value=" > "
            )
            options["prepend_header_path"] = st.checkbox(
                "把标题路径前置到每个 chunk 正文",
                value=False,
                help="适合让 Embedding 感知章节语境；前置文本不计入 chunk_size。",
            )

left, right = st.columns([1, 1.15], gap="large")

with left:
    st.subheader("Markdown 输入")
    markdown = st.text_area(
        "在这里修改内容",
        value=SAMPLE_MARKDOWN,
        height=650,
        label_visibility="collapsed",
    )


def run_splitter() -> list[Chunk]:
    if not markdown.strip():
        return []
    if splitter_name == "RecursiveCharacterTextSplitter":
        return split_recursive(markdown, **options)  # type: ignore[arg-type]
    if splitter_name == "CharacterTextSplitter":
        return split_character(markdown, **options)  # type: ignore[arg-type]
    if splitter_name == "MarkdownHeader + Recursive":
        return split_markdown_then_recursive(markdown, **options)  # type: ignore[arg-type]
    if not options["header_levels"]:
        raise ValueError("请至少选择一个 Markdown 标题层级")
    return split_markdown_headers(markdown, **options)  # type: ignore[arg-type]


with right:
    st.subheader("切分结果")
    try:
        chunks = run_splitter()
    except ValueError as exc:
        st.error(str(exc))
        chunks = []

    total_chars = sum(chunk.char_count for chunk in chunks)
    max_chars = max((chunk.char_count for chunk in chunks), default=0)
    metric_cols = st.columns(3)
    metric_cols[0].metric("Chunk 数", len(chunks))
    metric_cols[1].metric("结果总字符", total_chars)
    metric_cols[2].metric("最大 Chunk", max_chars)

    if chunks:
        export_data = [chunk.to_dict() for chunk in chunks]
        st.download_button(
            "下载 JSON 结果",
            data=json.dumps(export_data, ensure_ascii=False, indent=2),
            file_name="chunks.json",
            mime="application/json",
        )
        for chunk in chunks:
            label = f"Chunk {chunk.index} · {chunk.char_count} 字符"
            if chunk.metadata:
                label += f" · metadata: {chunk.metadata}"
            with st.expander(label, expanded=chunk.index <= 3):
                st.code(chunk.content, language="markdown", wrap_lines=True)
                if chunk.metadata:
                    st.json(chunk.metadata)
    elif markdown.strip():
        st.warning("当前配置没有生成 chunk。")

with st.expander("如何理解四种切分方式？"):
    st.markdown(
        """
        - **RecursiveCharacterTextSplitter**：依次尝试“段落 → 换行 → 句子 → 空格 → 字符”，尽量保留语义完整性。
        - **CharacterTextSplitter**：只认一个分隔符；如果一个段落本身很长，结果可能超过 `chunk_size`。
        - **MarkdownHeaderTextSplitter**：关注文档结构而不是固定长度，标题路径会进入 `metadata`，适合结构清晰的知识库文档。
        - **MarkdownHeader + Recursive**：先得到章节和标题 metadata，再限制章节内部长度；递归产生的每个子 chunk 都继承完整标题路径。

        组合策略更适合结构清晰但章节较长的 RAG 文档。`start_index` 表示 chunk 在章节正文中的相对位置；如果开启标题路径前置，新增前缀不参与 `chunk_size` 计算。
        """
    )
