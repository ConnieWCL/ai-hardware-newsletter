"""去重模块单元测试."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from digest.config_loader import Article
from digest.deduper import canonical_url, dedup, jaccard, shingles


def test_canonical_url_strips_tracking():
    a = "https://Example.com/news/x/?utm_source=rss&a=1#top"
    b = "https://example.com/news/x?a=1"
    assert canonical_url(a) == canonical_url(b)


def test_shingles_jaccard_similarity():
    s1 = shingles("Meta launches new Ray-Ban smart glasses")
    s2 = shingles("Meta launches new Ray-Ban smart glasses with AI")
    assert jaccard(s1, s2) > 0.5


def test_same_event_two_sources_clustered():
    a = Article(title="OpenAI unveils AI hardware device", url="https://a.com/x",
                source="a", source_priority=5)
    b = Article(title="OpenAI unveils AI hardware device", url="https://b.com/y",
                source="b", source_priority=9)
    clusters = dedup([a, b], threshold=0.5)
    assert len(clusters) == 1
    assert clusters[0][0].source == "b"  # 高权威度来源作为代表


def test_different_events_not_clustered():
    a = Article(title="Qualcomm announces Snapdragon X2 chip", url="https://a.com/x",
                source="a", source_priority=5)
    b = Article(title="Rokid launches new AR glasses in China", url="https://b.com/y",
                source="b", source_priority=5)
    assert len(dedup([a, b], threshold=0.6)) == 2


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
