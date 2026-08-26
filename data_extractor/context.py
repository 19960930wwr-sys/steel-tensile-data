from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def truncate_text(text: str, limit: int = 8000) -> str:
    text = str(text or "")
    return text if len(text) <= limit else text[:limit]


def make_source_id(source_type: str, index: int, page_idx: int | None = None) -> str:
    if page_idx is None:
        return f"{source_type}-{index}"
    return f"{source_type}-{index}-p{page_idx}"


@dataclass
class ArticleContext:
    title: str = ""
    abstract: str = ""
    body_text: str = ""
    table_text: str = ""
    figure_text: str = ""
    source_blocks: list[dict[str, Any]] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        parts = [self.title, self.abstract, self.body_text, self.figure_text]
        return "\n".join(part for part in parts if part)

    def prompt_text(self) -> str:
        lines: list[str] = []
        for block in self.source_blocks:
            sid = block.get("source_id", "")
            section = block.get("section", "")
            quote = block.get("quote", "")
            lines.append(f"[source_id={sid} | section={section}] {quote}".strip())
        if lines:
            return "\n".join(lines)
        return self.full_text

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "abstract": self.abstract,
            "body_text": self.body_text,
            "table_text": self.table_text,
            "figure_text": self.figure_text,
            "source_blocks": self.source_blocks,
        }


def _from_json_payload(payload: Any) -> ArticleContext:
    if isinstance(payload, dict) and "blocks" in payload:
        payload = payload["blocks"]
    blocks = payload if isinstance(payload, list) else []
    text_parts: list[str] = []
    table_parts: list[str] = []
    figure_parts: list[str] = []
    source_blocks: list[dict[str, Any]] = []
    for idx, part in enumerate(blocks):
        if not isinstance(part, dict):
            continue
        part_type = str(part.get("type", "")).lower()
        if part_type == "text":
            text = normalize_whitespace(part.get("text", ""))
            if text:
                text_parts.append(text)
                source_blocks.append(
                    {
                        "source_id": make_source_id("json-text", idx),
                        "source_type": "json",
                        "block_type": "text",
                        "section": part.get("section", ""),
                        "quote": truncate_text(text),
                    }
                )
        elif part_type == "table":
            caption = normalize_whitespace(part.get("table_caption", ""))
            footnote = normalize_whitespace(part.get("table_footnote", ""))
            table_body = str(part.get("table_body", ""))
            soup = BeautifulSoup(table_body, "html.parser")
            table = soup.find("table")
            if table is not None:
                table_text = normalize_whitespace(table.get_text(" | ", strip=True))
                table_parts.append(f"{caption} {footnote} {table_text}".strip())
                source_blocks.append(
                    {
                        "source_id": make_source_id("json-table", idx),
                        "source_type": "json",
                        "block_type": "table",
                        "section": caption,
                        "quote": truncate_text(f"{caption} {table_text}"),
                    }
                )
        elif part_type == "figure":
            caption = normalize_whitespace(part.get("img_caption", part.get("caption", "")))
            if caption:
                figure_parts.append(caption)
                source_blocks.append(
                    {
                        "source_id": make_source_id("json-figure", idx),
                        "source_type": "json",
                        "block_type": "figure",
                        "section": caption,
                        "quote": truncate_text(caption),
                    }
                )
    return ArticleContext(
        body_text="\n".join(text_parts),
        table_text="\n".join(table_parts),
        figure_text="\n".join(figure_parts),
        source_blocks=source_blocks,
    )


def _from_markup(text: str, source_type: str) -> ArticleContext:
    soup = BeautifulSoup(text, "html.parser")
    title = normalize_whitespace((soup.title.text if soup.title else "") or "")
    abstract = normalize_whitespace(" ".join(el.get_text(" ", strip=True) for el in soup.select("abstract, .abstract, #abstract")))
    body_parts = [normalize_whitespace(p.get_text(" ", strip=True)) for p in soup.find_all("p")]
    body_text = "\n".join(part for part in body_parts if part)
    table_parts: list[str] = []
    source_blocks: list[dict[str, Any]] = []
    for idx, table in enumerate(soup.find_all("table")):
        table_text = normalize_whitespace(table.get_text(" | ", strip=True))
        if table_text:
            table_parts.append(table_text)
            source_blocks.append(
                {
                    "source_id": make_source_id(source_type, idx),
                    "source_type": source_type,
                    "block_type": "table",
                    "section": "",
                    "quote": truncate_text(table_text),
                }
            )
    figure_parts = [normalize_whitespace(fig.get_text(" ", strip=True)) for fig in soup.find_all("figcaption")]
    figure_text = "\n".join(part for part in figure_parts if part)
    return ArticleContext(
        title=title,
        abstract=abstract,
        body_text=body_text,
        table_text="\n".join(table_parts),
        figure_text=figure_text,
        source_blocks=source_blocks,
    )


def load_article_context(path: str | Path) -> ArticleContext:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".json":
        with path.open("r", encoding="utf-8") as handle:
            return _from_json_payload(json.load(handle))
    if suffix in {".xml", ".html", ".htm"}:
        return _from_markup(path.read_text(encoding="utf-8", errors="ignore"), source_type=suffix.lstrip("."))
    return ArticleContext(body_text=path.read_text(encoding="utf-8", errors="ignore"))

