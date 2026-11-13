from __future__ import annotations

import json
import math
import textwrap
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageStat
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


class LayoutService:
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

    def add_dialogue(self, image_path: Path, page: dict[str, Any], output_path: Path) -> Path:
        with Image.open(image_path) as source:
            image = source.convert("RGB")
        dialogues = page.get("dialogues", [])
        width, height = image.size
        rail_height = 0
        if len(dialogues) >= 3:
            rows = math.ceil(len(dialogues) / 2)
            rail_height = max(300, rows * 205 + 38)
            extended = Image.new("RGB", (width, height + rail_height), "#eee9dd")
            extended.paste(image, (0, rail_height))
            image = extended
            height = image.height
        draw = ImageDraw.Draw(image, "RGBA")
        if rail_height:
            draw.line((0, rail_height - 4, width, rail_height - 4), fill=(34, 38, 33, 255), width=7)
        grayscale = image.convert("L")
        edges = grayscale.filter(ImageFilter.FIND_EDGES)
        occupied: list[tuple[int, int, int, int]] = []
        preferred = str(page.get("dialogue_zone", "top"))
        for index, dialogue in enumerate(dialogues):
            speaker = str(dialogue.get("speaker", "")).upper()
            dialogue_text = str(dialogue.get("text", "")).strip()
            bubble_w = int(width * (0.68 if len(dialogues) == 1 else 0.43))
            font_size = 28
            font = self._font(font_size)
            lines = self._wrap_text(draw, dialogue_text, font, bubble_w - 58)
            while len(lines) > 5 and font_size > 19:
                font_size -= 2
                font = self._font(font_size)
                lines = self._wrap_text(draw, dialogue_text, font, bubble_w - 58)
            line_height = font_size + 8
            bubble_h = max(130, 64 + len(lines) * line_height)
            if rail_height:
                rail_rows = math.ceil(len(dialogues) / 2)
                rail_margin = max(24, int(width * 0.035))
                rail_gap = 28
                cell_w = (width - rail_margin * 2 - rail_gap) // 2
                cell_h = (rail_height - rail_margin * 2) // rail_rows
                col, row = index % 2, index // 2
                bubble_w = cell_w
                bubble_h = min(bubble_h, cell_h - 16)
                x = rail_margin + col * (cell_w + rail_gap)
                y = rail_margin + row * cell_h
                box = (x, y, x + bubble_w, y + bubble_h)
            else:
                box = self._find_safe_box(
                    edges, grayscale, bubble_w, bubble_h, occupied, preferred, index,
                )
            x, y, x2, y2 = box
            occupied.append(box)
            shadow = (x + 7, y + 9, x2 + 7, y2 + 9)
            draw.rounded_rectangle(shadow, radius=32, fill=(15, 20, 17, 75))
            draw.rounded_rectangle(box, radius=32, fill=(255, 255, 252, 246), outline=(28, 31, 27, 255), width=6)
            tail_right = x + (x2 - x) / 2 < width / 2
            tail_x = int(x2 - 70 if tail_right else x + 42)
            tail_tip_x = min(width - 20, tail_x + 42) if tail_right else max(20, tail_x - 20)
            draw.polygon(
                [(tail_x, y2 - 4), (tail_x + 35, y2 - 4), (tail_tip_x, min(height - 14, y2 + 38))],
                fill=(255, 255, 252, 246), outline=(28, 31, 27, 255),
            )
            draw.text((x + 28, y + 18), speaker, font=self._font(20, True), fill="#ee6c4d")
            for line_index, line in enumerate(lines):
                draw.text(
                    (x + 28, y + 50 + line_index * line_height), line,
                    font=font, fill=(21, 23, 20, 255),
                )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path, quality=96)
        return output_path

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

    def _find_safe_box(
        self,
        edges: Image.Image,
        grayscale: Image.Image,
        bubble_w: int,
        bubble_h: int,
        occupied: list[tuple[int, int, int, int]],
        preferred: str,
        index: int,
    ) -> tuple[int, int, int, int]:
        width, height = edges.size
        margin = max(28, int(width * 0.035))
        xs = [margin, (width - bubble_w) // 2, width - bubble_w - margin]
        ys = [margin, int(height * 0.2), int(height * 0.42), int(height * 0.66)]
        candidates = [
            (x, y, x + bubble_w, min(height - margin, y + bubble_h))
            for y in ys for x in xs if y + bubble_h <= height - margin
        ]

        def overlap(box: tuple[int, int, int, int]) -> bool:
            padding = 24
            return any(
                not (
                    box[2] + padding < other[0] or box[0] - padding > other[2]
                    or box[3] + padding < other[1] or box[1] - padding > other[3]
                )
                for other in occupied
            )

        def score(box: tuple[int, int, int, int]) -> float:
            if overlap(box):
                return float("inf")
            edge_mean = ImageStat.Stat(edges.crop(box)).mean[0]
            variance = ImageStat.Stat(grayscale.crop(box)).var[0]
            cx = (box[0] + box[2]) / (2 * width)
            cy = (box[1] + box[3]) / (2 * height)
            # Illustrated characters are commonly central and high-detail. Prefer quiet margins.
            subject_penalty = 22 if 0.28 < cx < 0.72 and 0.2 < cy < 0.82 else 0
            vertical_penalty = cy * 8
            preference_penalty = 0
            if "top" in preferred and cy > 0.38:
                preference_penalty += 14
            if "left" in preferred and cx > 0.5:
                preference_penalty += 8
            if "right" in preferred and cx < 0.5:
                preference_penalty += 8
            return edge_mean + min(variance / 180, 22) + subject_penalty + vertical_penalty + preference_penalty

        available = [box for box in candidates if not overlap(box)]
        if available:
            return min(available, key=score)
        # Last-resort cascade remains inside the page when every quiet region is occupied.
        x = margin if index % 2 == 0 else width - bubble_w - margin
        y = min(height - bubble_h - margin, margin + index * (bubble_h + 24))
        return (x, y, x + bubble_w, y + bubble_h)

    def finalize_cover(self, image_path: Path, title: str, output_path: Path) -> Path:
        with Image.open(image_path) as source:
            image = source.convert("RGB")
        draw = ImageDraw.Draw(image, "RGBA")
        width, height = image.size
        band_height = int(height * 0.23)
        draw.rectangle((0, 0, width, band_height), fill=(20, 30, 25, 188))
        font_size = max(44, min(94, int(width / max(7, len(title) * 0.72))))
        font = self._font(font_size, True)
        lines = textwrap.wrap(title.upper(), width=max(12, int(width / (font_size * 0.58))))[:3]
        y = 40
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            x = (width - (bbox[2] - bbox[0])) / 2
            draw.text((x + 4, y + 5), line, font=font, fill=(0, 0, 0, 130))
            draw.text((x, y), line, font=font, fill=(255, 248, 224, 255), stroke_width=2, stroke_fill=(25, 30, 27, 255))
            y += int(font_size * 1.03)
        draw.rounded_rectangle((width - 245, height - 82, width - 28, height - 27), 14, fill=(234, 93, 62, 235))
        draw.text((width - 221, height - 67), "COMICFLOW ORIGINAL", font=self._font(18, True), fill="white")
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

