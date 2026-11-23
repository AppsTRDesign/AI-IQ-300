"""Markdown left in documents: a heading with no space after its #s ("###Ekran Görüntüleme", reported in a PDF on
2026-11-23) and Markdown headings mixed into HTML content."""
from app.tools.docs_gen import Source


def test_tight_heading_becomes_heading():
    s = Source("# Rapor\n\n###Ekran Görüntüleme\n\nMetin\n\n####Alt başlık\n")
    assert "<h3>Ekran Görüntüleme</h3>" in s.html
    assert "<h4>Alt başlık</h4>" in s.html
    assert "###" not in s.html


def test_hashtags_numbers_and_code_stay():
    s = Source("Metin\n\n#hashtag\n\n#1 sırada\n\n```\n###kod\n```\n\n#ai #ml\n")
    assert "#hashtag" in s.html and "#1 sırada" in s.html and "###kod" in s.html and "#ai #ml" in s.html
    assert "<h1>" not in s.html


def test_markdown_heading_inside_html():
    s = Source("<h1>Rapor</h1>\n<p>### Ekran</p>\n<p>##Bellek</p>\n<pre>### kod</pre>")
    assert "<h3>Ekran</h3>" in s.html and "<h2>Bellek</h2>" in s.html
    assert "<pre>### kod</pre>" in s.html
