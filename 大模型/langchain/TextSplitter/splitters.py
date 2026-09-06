"""LangChain Markdown 文本切分器的统一封装。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from langchain_text_splitters import (
    CharacterTextSplitter,
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

SplitterName = Literal[
    "RecursiveCharacterTextSplitter",
    "CharacterTextSplitter",
    "MarkdownHeaderTextSplitter",
    "MarkdownHeader + Recursive",
]


@dataclass(frozen=True, slots=True)
class Chunk:
    """供前端展示的统一切分结果。"""

    index: int
    content: str
    metadata: dict[str, Any]

    @property
    def char_count(self) -> int:
        return len(self.content)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["char_count"] = self.char_count
        return result


def _validate_chunk_options(chunk_size: int, chunk_overlap: int) -> None:
    if chunk_size <= 0:
        raise ValueError("chunk_size 必须大于 0")
    if chunk_overlap < 0:
        raise ValueError("chunk_overlap 不能小于 0")
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap 必须小于 chunk_size")


def _to_chunks(documents: list[Any]) -> list[Chunk]:
    return [
        Chunk(index=index, content=document.page_content, metadata=dict(document.metadata))
        for index, document in enumerate(documents, start=1)
    ]


def _normalize_header_levels(header_levels: list[int] | None) -> list[int]:
    levels = [1, 2, 3] if header_levels is None else sorted(set(header_levels))
    if not levels:
        raise ValueError("请至少选择一个 Markdown 标题层级")
    if any(level not in range(1, 7) for level in levels):
        raise ValueError("Markdown 标题层级必须在 1 到 6 之间")
    return levels


def _build_header_path(metadata: dict[str, Any], separator: str) -> str:
    """按 H1～H6 顺序拼接当前章节已有的标题。"""

    titles = [str(metadata[f"H{level}"]) for level in range(1, 7) if metadata.get(f"H{level}")]
    return separator.join(titles)


def split_recursive(
    markdown: str,
    *,
    chunk_size: int = 300,
    chunk_overlap: int = 50,
    separators: list[str] | None = None,
    keep_separator: bool = True,
) -> list[Chunk]:
    """按分隔符优先级递归切分 Markdown。"""

    _validate_chunk_options(chunk_size, chunk_overlap)
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=separators or ["\n\n", "\n", "。", "！", "？", " ", ""],
        keep_separator=keep_separator,
        add_start_index=True,
        length_function=len,
    )
    return _to_chunks(splitter.create_documents([markdown]))


def split_character(
    markdown: str,
    *,
    chunk_size: int = 300,
    chunk_overlap: int = 50,
    separator: str = "\n\n",
    keep_separator: bool = False,
) -> list[Chunk]:
    """只使用一个指定分隔符切分 Markdown。"""

    _validate_chunk_options(chunk_size, chunk_overlap)
    splitter = CharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separator=separator,
        keep_separator=keep_separator,
        add_start_index=True,
        length_function=len,
    )
    return _to_chunks(splitter.create_documents([markdown]))


def split_markdown_headers(
    markdown: str,
    *,
    header_levels: list[int] | None = None,
    strip_headers: bool = True,
    return_each_line: bool = False,
) -> list[Chunk]:
    """按 Markdown 标题层级切分，并把标题路径写入 metadata。"""

    levels = _normalize_header_levels(header_levels)
    headers_to_split_on = [("#" * level, f"H{level}") for level in levels]
    splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split_on,
        strip_headers=strip_headers,
        return_each_line=return_each_line,
    )
    return _to_chunks(splitter.split_text(markdown))


def split_markdown_then_recursive(
    markdown: str,
    *,
    chunk_size: int = 300,
    chunk_overlap: int = 50,
    header_levels: list[int] | None = None,
    strip_headers: bool = True,
    separators: list[str] | None = None,
    keep_separator: bool = True,
    header_path_separator: str = " > ",
    prepend_header_path: bool = False,
) -> list[Chunk]:
    """先按标题拆章节，再在章节内递归切分，并把完整标题路径传给每个 chunk。

    ``start_index`` 是 chunk 在所属章节正文中的相对位置，而非原始 Markdown
    的绝对位置。标题路径前置发生在递归切分之后，因此不会参与 chunk_size 计算。
    """

    _validate_chunk_options(chunk_size, chunk_overlap)
    levels = _normalize_header_levels(header_levels)
    if not header_path_separator:
        raise ValueError("标题路径分隔符不能为空")

    header_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=[("#" * level, f"H{level}") for level in levels],
        strip_headers=strip_headers,
    )
    recursive_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=separators or ["\n\n", "\n", "。", "！", "？", " ", ""],
        keep_separator=keep_separator,
        add_start_index=True,
        length_function=len,
    )

    result: list[Chunk] = []
    sections = header_splitter.split_text(markdown)
    for section_index, section in enumerate(sections, start=1):
        header_path = _build_header_path(section.metadata, header_path_separator)
        section.metadata.update(
            {
                "header_path": header_path,
                "section_index": section_index,
            }
        )
        section_chunks = recursive_splitter.split_documents([section])
        for section_chunk_index, document in enumerate(section_chunks, start=1):
            metadata = dict(document.metadata)
            metadata["section_chunk_index"] = section_chunk_index
            content = document.page_content
            if prepend_header_path and header_path:
                content = f"标题路径：{header_path}\n\n{content}"
            result.append(
                Chunk(index=len(result) + 1, content=content, metadata=metadata)
            )

    return result


def parse_separator(value: str) -> str:
    """把界面中的 ``\\n``、``\\t``、``\\r`` 转成真实控制字符。"""

    return value.replace("\\r", "\r").replace("\\n", "\n").replace("\\t", "\t")


def parse_separators(value: str) -> list[str]:
    """解析每行一个的分隔符；``<EMPTY>`` 表示空字符串兜底。"""

    separators: list[str] = []
    for line in value.splitlines():
        if line == "<EMPTY>":
            separators.append("")
        elif line:
            separators.append(parse_separator(line))
    return separators
