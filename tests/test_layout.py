from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from backend.app.services.layout import LayoutService


def test_layout_adds_bubbles_and_makes_pdf(tmp_path: Path):
    raw = tmp_path / "raw.png"
    Image.new("RGB", (600, 900), "#c9d9ce").save(raw)
    page = {"dialogues": [{"speaker": "Mèo", "text": "Mình sẽ thử thêm một lần nữa!"}]}
    final = LayoutService().add_dialogue(raw, page, tmp_path / "final.png")
    cover = LayoutService().finalize_cover(raw, "Chú mèo dũng cảm", tmp_path / "cover.png")
    sheet = LayoutService().make_contact_sheet(cover, [final], tmp_path / "sheet.jpg")
    pdf = LayoutService().make_pdf(cover, [final], tmp_path / "comic.pdf", {"title": "Test"})
    assert final.exists() and final.stat().st_size > raw.stat().st_size
    assert cover.exists() and sheet.exists()
    assert pdf.exists() and pdf.stat().st_size > 1000


def test_safe_box_avoids_busy_character_area():
    image = Image.new("RGB", (600, 900), "white")
    draw = ImageDraw.Draw(image)
    for x in range(20, 280, 12):
        draw.line((x, 10, x, 320), fill="black", width=6)
    gray = image.convert("L")
    edges = gray.filter(ImageFilter.FIND_EDGES)

    box = LayoutService()._find_safe_box(edges, gray, 240, 140, [], "top", 0)
    assert box[0] >= 180  # picks the quiet center/right instead of the busy top-left


def test_dialogue_wrapper_keeps_every_word():
    image = Image.new("RGB", (600, 900), "white")
    draw = ImageDraw.Draw(image)
    text = "Mình sẽ quay lại giúp bạn vì chúng ta luôn cùng nhau vượt qua khó khăn."
    font = LayoutService()._font(24)
    lines = LayoutService()._wrap_text(draw, text, font, 260)
    assert " ".join(lines) == text
    assert len(lines) > 1

