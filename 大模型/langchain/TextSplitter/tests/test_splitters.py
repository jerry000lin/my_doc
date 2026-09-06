import pytest

from splitters import (
    parse_separator,
    parse_separators,
    split_character,
    split_markdown_headers,
    split_markdown_then_recursive,
    split_recursive,
)


MARKDOWN = """# 产品文档

产品介绍内容。

## 安装

第一步安装依赖。第二步启动服务。

## 使用

输入数据后运行工作流。
"""


def test_recursive_splitter_按优先级拆分并记录起始位置() -> None:
    chunks = split_recursive(MARKDOWN, chunk_size=35, chunk_overlap=5)

    assert len(chunks) > 1
    assert all(chunk.char_count <= 35 for chunk in chunks)
    assert all("start_index" in chunk.metadata for chunk in chunks)


def test_character_splitter_只使用指定分隔符() -> None:
    chunks = split_character(
        "第一段。\n\n第二段。\n\n第三段。",
        chunk_size=6,
        chunk_overlap=0,
        separator="\n\n",
    )

    assert [chunk.content for chunk in chunks] == ["第一段。", "第二段。", "第三段。"]


def test_markdown_header_splitter_生成标题路径元数据() -> None:
    chunks = split_markdown_headers(MARKDOWN, header_levels=[1, 2])

    assert chunks[0].metadata == {"H1": "产品文档"}
    assert chunks[1].metadata == {"H1": "产品文档", "H2": "安装"}
    assert chunks[2].metadata == {"H1": "产品文档", "H2": "使用"}
    assert "## 安装" not in chunks[1].content


def test_markdown_header_splitter_可以保留标题() -> None:
    chunks = split_markdown_headers(MARKDOWN, header_levels=[1, 2], strip_headers=False)

    assert chunks[0].content.startswith("# 产品文档")
    assert chunks[1].content.startswith("## 安装")


def test_组合切分_章节内递归并为每个子块补全标题路径() -> None:
    markdown = """# 产品文档

## 安装

第一步安装依赖。第二步修改配置。第三步启动服务。第四步检查运行状态。

## 使用

输入数据后运行工作流。
"""
    chunks = split_markdown_then_recursive(
        markdown,
        chunk_size=18,
        chunk_overlap=3,
        header_levels=[1, 2],
    )

    install_chunks = [chunk for chunk in chunks if chunk.metadata["H2"] == "安装"]
    assert len(install_chunks) > 1
    assert all(chunk.metadata["H1"] == "产品文档" for chunk in install_chunks)
    assert all(chunk.metadata["header_path"] == "产品文档 > 安装" for chunk in install_chunks)
    assert [chunk.metadata["section_chunk_index"] for chunk in install_chunks] == list(
        range(1, len(install_chunks) + 1)
    )
    assert all("start_index" in chunk.metadata for chunk in install_chunks)


def test_组合切分_可将标题路径前置到每个子块正文() -> None:
    chunks = split_markdown_then_recursive(
        MARKDOWN,
        chunk_size=15,
        chunk_overlap=2,
        header_levels=[1, 2],
        header_path_separator=" / ",
        prepend_header_path=True,
    )

    install_chunks = [chunk for chunk in chunks if chunk.metadata.get("H2") == "安装"]
    assert install_chunks
    assert all(
        chunk.content.startswith("标题路径：产品文档 / 安装\n\n")
        for chunk in install_chunks
    )


def test_overlap_不能大于等于_chunk_size() -> None:
    with pytest.raises(ValueError, match="chunk_overlap 必须小于 chunk_size"):
        split_recursive(MARKDOWN, chunk_size=10, chunk_overlap=10)


def test_separator_转义解析() -> None:
    assert parse_separator(r"\n\n") == "\n\n"
    assert parse_separators("\\n\\n\n空格\n<EMPTY>") == ["\n\n", "空格", ""]
