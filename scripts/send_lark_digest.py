#!/usr/bin/env python3
"""Send the daily AI News Radar digest to Feishu/Lark via lark-cli."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def fmt_dt(value: str | None) -> str:
    if not value:
        return "时间未知"
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    return dt.astimezone().strftime("%m-%d %H:%M")


def item_title(item: dict[str, Any]) -> str:
    return str(
        item.get("title_zh")
        or item.get("title_bilingual")
        or item.get("title")
        or item.get("title_en")
        or "未命名更新"
    ).strip()


def compact_summary(text: str, max_chars: int = 68) -> str:
    """Turn a title into one concise digest sentence.

    The daily push deliberately stays extractive: it does not invent details
    that are not present in the source title.
    """
    s = re.sub(r"\s+", " ", text or "").strip()
    s = s.strip(" -—–|｜")
    s = re.sub(r"^【([^】]{2,24})】\s*", r"\1：", s)
    s = re.sub(r"^\[([^\]]{2,24})\]\s*", r"\1：", s)
    if len(s) > max_chars:
        s = s[: max_chars - 1].rstrip(" ，,。.!！?？:：;；") + "…"
    if s and s[-1] not in "。.!！?？…":
        s += "。"
    return s or "未命名更新。"


def select_digest_items(
    items: list[dict[str, Any]],
    *,
    top_n: int,
    max_per_site: int,
    max_per_source: int,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    site_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()

    for item in items:
        title = item_title(item)
        url = str(item.get("url") or "").strip()
        if not title or not url:
            continue

        site_key = str(item.get("site_id") or item.get("site_name") or "unknown")
        source_key = f"{site_key}:{item.get('source') or ''}"
        if max_per_site > 0 and site_counts[site_key] >= max_per_site:
            continue
        if max_per_source > 0 and source_counts[source_key] >= max_per_source:
            continue

        selected.append(item)
        site_counts[site_key] += 1
        source_counts[source_key] += 1
        if len(selected) >= top_n:
            break

    if len(selected) >= top_n:
        return selected

    seen_urls = {str(item.get("url") or "").strip() for item in selected}
    for item in items:
        url = str(item.get("url") or "").strip()
        if not url or url in seen_urls:
            continue
        selected.append(item)
        seen_urls.add(url)
        if len(selected) >= top_n:
            break
    return selected


def build_markdown(
    payload: dict[str, Any],
    *,
    site_url: str,
    top_n: int,
    max_per_site: int,
    max_per_source: int,
) -> str:
    items = payload.get("items_ai") or payload.get("items") or []
    if not isinstance(items, list):
        items = []
    selected = select_digest_items(
        items,
        top_n=top_n,
        max_per_site=max_per_site,
        max_per_source=max_per_source,
    )

    generated_at = fmt_dt(str(payload.get("generated_at") or ""))
    total_items = int(payload.get("total_items") or len(items) or 0)
    site_count = int(payload.get("site_count") or 0)
    archive_total = int(payload.get("archive_total") or 0)

    lines = [
        f"**AI News Radar｜今日 AI 热点 Top {len(selected)}**",
        "",
        f"更新：{generated_at} · AI 强相关 {total_items} 条 · 来源 {site_count} 个 · 归档 {archive_total} 条",
    ]

    if not selected:
        lines.append("今天暂时没有抓到 AI 强相关热点。")
    else:
        for idx, item in enumerate(selected, 1):
            summary = compact_summary(item_title(item))
            url = str(item.get("url") or "").strip()
            site_name = str(item.get("site_name") or item.get("site_id") or "未知来源").strip()
            source = str(item.get("source") or "").strip()
            published = fmt_dt(str(item.get("published_at") or item.get("first_seen_at") or ""))
            source_label = f"{site_name} / {source}" if source else site_name
            lines.extend(
                [
                    "",
                    f"{idx}. **核心：{summary}**",
                    f"   [原文链接]({url}) · {source_label} · {published}",
                ]
            )

    if site_url:
        lines.extend(["", f"[打开完整雷达]({site_url})"])
    return "\n".join(lines).strip()


def send_lark_message(markdown: str, *, user_id: str, chat_id: str, dry_run: bool) -> None:
    cmd = ["lark-cli", "im", "+messages-send", "--as", "bot", "--markdown", markdown]
    if user_id:
        cmd.extend(["--user-id", user_id])
    elif chat_id:
        cmd.extend(["--chat-id", chat_id])
    else:
        raise SystemExit("Missing LARK_USER_OPEN_ID or LARK_CHAT_ID")
    if dry_run:
        cmd.append("--dry-run")
    result = subprocess.run(cmd, text=True, capture_output=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-file", default="data/latest-24h.json")
    parser.add_argument("--site-url", default=os.environ.get("AI_NEWS_RADAR_SITE_URL", ""))
    parser.add_argument("--top-n", type=int, default=int(os.environ.get("LARK_DIGEST_TOP_N", "10")))
    parser.add_argument("--max-per-site", type=int, default=int(os.environ.get("LARK_DIGEST_MAX_PER_SITE", "4")))
    parser.add_argument("--max-per-source", type=int, default=int(os.environ.get("LARK_DIGEST_MAX_PER_SOURCE", "2")))
    parser.add_argument("--user-id", default=os.environ.get("LARK_USER_OPEN_ID", ""))
    parser.add_argument("--chat-id", default=os.environ.get("LARK_CHAT_ID", ""))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--print-only", action="store_true")
    args = parser.parse_args()

    payload = load_json(Path(args.data_file))
    markdown = build_markdown(
        payload,
        site_url=args.site_url,
        top_n=args.top_n,
        max_per_site=args.max_per_site,
        max_per_source=args.max_per_source,
    )

    if args.print_only:
        print(markdown)
        return 0

    send_lark_message(markdown, user_id=args.user_id, chat_id=args.chat_id, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
