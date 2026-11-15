from pathlib import Path

from PIL import Image, ImageDraw

from backend.app.services.layout import LayoutService


def test_layout_places_story_text_beside_art_and_makes_pdf(tmp_path: Path):
    raw = tmp_path / "raw.png"
    Image.new("RGB", (600, 900), "#c9d9ce").save(raw)
    page = {
        "page_number": 1,
        "story_text": "Ngày nọ, Mèo nhỏ quyết định bước qua khu rừng để tìm người bạn đã lạc mất. " * 5,
    }
    final = LayoutService().compose_story_page(raw, page, tmp_path / "final.png")
    cover = LayoutService().finalize_cover(raw, "Chú mèo dũng cảm", tmp_path / "cover.png")
    sheet = LayoutService().make_contact_sheet(cover, [final], tmp_path / "sheet.jpg")
    pdf = LayoutService().make_pdf(cover, [final], tmp_path / "comic.pdf", {"title": "Test"})
    assert final.exists() and Image.open(final).size == (1600, 1200)
    assert Image.open(cover).size == (1600, 1200)
    assert cover.exists() and sheet.exists()
    assert pdf.exists() and pdf.stat().st_size > 1000


def test_story_text_falls_back_to_legacy_script_fields():
    page = {
        "action": "Mèo nhỏ bước qua khu rừng.",
        "dialogues": [{"speaker": "Mèo", "text": "Mình sẽ tìm được đường về nhà."}],
    }
    story = LayoutService._story_text(page)
    assert "Mèo nhỏ bước qua khu rừng" in story
    assert "Mình sẽ tìm được đường về nhà" in story


def test_dialogue_wrapper_keeps_every_word():
    image = Image.new("RGB", (600, 900), "white")
    draw = ImageDraw.Draw(image)
    text = "Mình sẽ quay lại giúp bạn vì chúng ta luôn cùng nhau vượt qua khó khăn."
    font = LayoutService()._font(24)
    lines = LayoutService()._wrap_text(draw, text, font, 260)
    assert " ".join(lines) == text
    assert len(lines) > 1

