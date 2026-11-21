"""A chart written from the task folder (images/grafik.png) gets into a document whose source text lives in
docs/.doc-sources/ - before, make_doc looked for it next to the source text and dropped it every time."""
import asyncio

from app.tools.registry import TOOLS, ToolContext


def _png(path):
    from PIL import Image
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (40, 30), (200, 80, 40)).save(path)


def test_a_chart_from_the_task_folder_is_in_every_format(tmp_path):
    _png(tmp_path / "images" / "grafik.png")
    src = tmp_path / "docs" / ".doc-sources" / "r.pdf.md"
    src.parent.mkdir(parents=True)
    src.write_text("# Rapor\n\nMetin.\n\n![Grafik](images/grafik.png)\n", encoding="utf-8")
    ctx = ToolContext("t", tmp_path, "full", asyncio.Event())
    for args, body in (({"path": "docs/r.pdf", "source": "docs/.doc-sources/r.pdf.md"}, ""),
                       ({"path": "docs/r.docx"}, '<h1>Rapor</h1><p>x</p><img src="grafik.png">')):
        res = asyncio.run(TOOLS["make_doc"].fn(ctx, args, body))
        assert res.ok and "contains 1 image" in res.output and "NOT included" not in res.output, res.output
