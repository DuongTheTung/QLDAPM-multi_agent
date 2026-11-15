from __future__ import annotations

import json
import math
import textwrap
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps
from reportlab.lib.pagesizes import A4, landscape, portrait
from reportlab.pdfgen import canvas


class LayoutService:
    PAGE_SIZE = (1600, 1200)
    ART_WIDTH = 800

    @staticmethod
    def _font(size: int, bold: bool = False):
        candidates = [
            "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
        for candidate in candidates:
            if Path(candidate).exists():
                return ImageFont.truetype(candidate, size=size)
        return ImageFont.load_default()

    def compose_story_page(self, image_path: Path, page: dict[str, Any], output_path: Path) -> Path:
        """Place artwork and prose in separate panels so text never covers a character."""
        with Image.open(image_path) as source:
            artwork = ImageOps.fit(
                source.convert("RGB"), (self.ART_WIDTH, self.PAGE_SIZE[1]),
                method=Image.Resampling.LANCZOS,
            )
        image = Image.new("RGB", self.PAGE_SIZE, "#fbfaf6")
        image.paste(artwork, (0, 0))
        draw = ImageDraw.Draw(image)
        draw.line(
            (self.ART_WIDTH, 0, self.ART_WIDTH, self.PAGE_SIZE[1]),
            fill="#dfd8ca", width=3,
        )
        margin = 62
        text_left = self.ART_WIDTH + margin
        text_width = self.PAGE_SIZE[0] - text_left - margin
        page_number = int(page.get("page_number") or 0)
        draw.text(
            (text_left, 62), f"TRANG {page_number:02d}" if page_number else "CÂU CHUYỆN",
            font=self._font(24, True), fill="#a29b8f",
        )
        story = self._story_text(page)
        font, lines, line_height = self._fit_story_text(draw, story, text_width, 970)
        y = 145
        for line in lines:
            if line == "":
                y += line_height // 2
                continue
            draw.text((text_left, y), line, font=font, fill="#242520")
            y += line_height
        draw.text(
            (self.PAGE_SIZE[0] - 250, self.PAGE_SIZE[1] - 54), "COMICFLOW",
            font=self._font(18, True), fill="#bbb3a5",
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path, quality=96)
        return output_path

    @staticmethod
    def _story_text(page: dict[str, Any]) -> str:
        story = str(page.get("story_text") or page.get("caption") or "").strip()
        if story:
            return story
        parts = [str(page.get("action") or "").strip()]
        parts.extend(
            f'{item.get("speaker", "Nhân vật")} nói: “{str(item.get("text", "")).strip()}”'
            for item in page.get("dialogues", []) if str(item.get("text", "")).strip()
        )
        return "\n\n".join(part for part in parts if part) or "Câu chuyện tiếp tục qua bức tranh này."

    def _fit_story_text(
        self, draw: ImageDraw.ImageDraw, text: str, max_width: int, max_height: int,
    ) -> tuple[Any, list[str], int]:
        for font_size in range(46, 17, -2):
            font = self._font(font_size)
            lines: list[str] = []
            for paragraph in text.splitlines():
                paragraph = paragraph.strip()
                if not paragraph:
                    if lines and lines[-1] != "":
                        lines.append("")
                    continue
                lines.extend(self._wrap_text(draw, paragraph, font, max_width))
            line_height = int(font_size * 1.38)
            blank_count = sum(line == "" for line in lines)
            used_height = (len(lines) - blank_count) * line_height + blank_count * (line_height // 2)
            if used_height <= max_height:
                return font, lines, line_height
        font = self._font(18)
        lines = self._wrap_text(draw, " ".join(text.split()), font, max_width)
        return font, lines, 25

    @staticmethod
    def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: Any, max_width: int) -> list[str]:
        words = text.split()
        if not words:
            return [""]
        lines: list[str] = []
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if draw.textlength(candidate, font=font) <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines

    def finalize_cover(self, image_path: Path, title: str, output_path: Path) -> Path:
        with Image.open(image_path) as source:
            artwork = ImageOps.fit(
                source.convert("RGB"), (self.ART_WIDTH, self.PAGE_SIZE[1]),
                method=Image.Resampling.LANCZOS,
            )
        image = Image.new("RGB", self.PAGE_SIZE, "#fbfaf6")
        image.paste(artwork, (0, 0))
        draw = ImageDraw.Draw(image, "RGBA")
        draw.rounded_rectangle((850, 220, 1550, 990), radius=46, fill=(195, 30, 37, 255))
        draw.text((905, 290), "TRUYỆN TRANH", font=self._font(28, True), fill="#fff4df")
        font_size = max(48, min(86, int(650 / max(7, len(title) * 0.56))))
        font = self._font(font_size, True)
        lines = textwrap.wrap(title.upper(), width=max(11, int(620 / (font_size * 0.58))))[:5]
        y = 390
        for line in lines:
            draw.text((905, y), line, font=font, fill="#71d4c9")
            y += int(font_size * 1.18)
        draw.text((905, 915), "COMICFLOW ORIGINAL", font=self._font(20, True), fill="#fff4df")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path, quality=96)
        return output_path

    def make_contact_sheet(self, cover: Path, pages: list[Path], destination: Path) -> Path:
        sources = [("COVER", cover), *[(f"P{index}", page) for index, page in enumerate(pages, start=1)]]
        columns = 4
        thumb_w, thumb_h, gap, label_h = 230, 330, 18, 34
        rows = math.ceil(len(sources) / columns)
        sheet = Image.new("RGB", (columns * (thumb_w + gap) + gap, rows * (thumb_h + label_h + gap) + gap), "#202822")
        draw = ImageDraw.Draw(sheet)
        for index, (label, path) in enumerate(sources):
            x = gap + (index % columns) * (thumb_w + gap)
            y = gap + (index // columns) * (thumb_h + label_h + gap)
            with Image.open(path) as source:
                thumb = source.convert("RGB")
                thumb.thumbnail((thumb_w, thumb_h))
            px = x + (thumb_w - thumb.width) // 2
            py = y + (thumb_h - thumb.height) // 2
            sheet.paste(thumb, (px, py))
            draw.text((x + 8, y + thumb_h + 6), label, font=self._font(18, True), fill="#f5c34f")
        destination.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(destination, quality=86, optimize=True)
        return destination

    def make_pdf(self, cover: Path, pages: list[Path], destination: Path, metadata: dict[str, Any]) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        pdf = canvas.Canvas(str(destination), pagesize=A4)
        pdf.setTitle(metadata.get("title", "ComicFlow Comic"))
        page_width, page_height = A4
        for image_path in [cover, *pages]:
            with Image.open(image_path) as image:
                iw, ih = image.size
            sheet_size = landscape(A4) if iw >= ih else portrait(A4)
            pdf.setPageSize(sheet_size)
            page_width, page_height = sheet_size
            scale = min(page_width / iw, page_height / ih)
            draw_w, draw_h = iw * scale, ih * scale
            pdf.drawImage(
                str(image_path), (page_width - draw_w) / 2, (page_height - draw_h) / 2,
                width=draw_w, height=draw_h, preserveAspectRatio=True,
            )
            pdf.showPage()
        pdf.save()
        (destination.parent / "manifest.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return destination

