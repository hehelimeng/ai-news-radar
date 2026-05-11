from scripts.send_lark_digest import build_markdown, select_digest_items


def item(site_id, source, title, url):
    return {
        "site_id": site_id,
        "site_name": site_id.upper(),
        "source": source,
        "title_zh": title,
        "url": url,
        "published_at": "2026-05-11T08:00:00Z",
    }


def test_select_digest_items_limits_repeated_sources():
    items = [
        item("a", "same", "A1", "https://example.com/a1"),
        item("a", "same", "A2", "https://example.com/a2"),
        item("a", "same", "A3", "https://example.com/a3"),
        item("b", "other", "B1", "https://example.com/b1"),
    ]

    selected = select_digest_items(items, top_n=3, max_per_site=2, max_per_source=1)

    assert [x["title_zh"] for x in selected] == ["A1", "B1", "A2"]


def test_build_markdown_contains_links_and_counts():
    payload = {
        "generated_at": "2026-05-11T01:00:00Z",
        "total_items": 2,
        "site_count": 2,
        "archive_total": 20,
        "items": [
            item("official_ai", "OpenAI News", "OpenAI 发布更新", "https://openai.com/news/x"),
            item("aibreakfast", "AI Breakfast", "AI 早餐新闻", "https://example.com/b"),
        ],
    }

    markdown = build_markdown(
        payload,
        site_url="https://hehelimeng.github.io/ai-news-radar/",
        top_n=2,
        max_per_site=4,
        max_per_source=2,
    )

    assert "AI News Radar 每日热点" in markdown
    assert "AI 强相关：2 条" in markdown
    assert "[OpenAI 发布更新](https://openai.com/news/x)" in markdown
    assert "[打开完整雷达](https://hehelimeng.github.io/ai-news-radar/)" in markdown
