from __future__ import annotations

import base64
import textwrap
from collections.abc import Callable
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFont

from ..config import Settings
from .router import NineRouterClient


class ImageService:
    def __init__(self, settings: Settings, router: NineRouterClient):
        self.settings = settings
        self.router = router

    async def generate(
        self,
        prompt: str,
        destination: Path,
        *,
        landscape: bool = False,
        on_warning: Callable[[str], None] | None = None,
    ) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        size = "1536x1024" if landscape else "1024x1536"
        try:
            response = await self.router.client.images.generate(
                model=self.settings.nine_router_image_model,
                prompt=prompt,
                size=size,
                n=1,
                response_format="b64_json",
                timeout=600,
            )
            item = response.data[0]
            if getattr(item, "b64_json", None):
                destination.write_bytes(base64.b64decode(item.b64_json))
            elif getattr(item, "url", None):
                async with httpx.AsyncClient(timeout=180) as client:
                    result = await client.get(item.url)
                    result.raise_for_status()
                    destination.write_bytes(result.content)
            else:
                raise ValueError("Image endpoint không trả b64_json hoặc URL")
            with Image.open(destination) as image:
                image.convert("RGB").save(destination, quality=95)
            return destination
        except Exception as error:  # noqa: BLE001 - image providers expose non-uniform SDK errors
            if on_warning:
                on_warning(f"Image API chưa khả dụng, đã tạo proof placeholder: {error}")
            self._placeholder(prompt, destination, landscape)
            return destination

    @staticmethod
    def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        candidates = [
            "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
        for candidate in candidates:
            if Path(candidate).exists():
                return ImageFont.truetype(candidate, size=size)
        return ImageFont.load_default()

    def _placeholder(self, prompt: str, destination: Path, landscape: bool) -> None:
        dimensions = (1536, 1024) if landscape else (1024, 1536)
        image = Image.new("RGB", dimensions, "#f1e9da")
        draw = ImageDraw.Draw(image)
        width, height = dimensions
        draw.rounded_rectangle((48, 48, width - 48, height - 48), 38, fill="#fffaf0", outline="#20231f", width=7)
        draw.rectangle((78, 78, width - 78, 230), fill="#ee6c4d")
        draw.text((110, 115), "COMICFLOW • IMAGE PROOF", font=self._font(42, True), fill="white")
        wrapped = textwrap.wrap(prompt[:1500], width=54 if not landscape else 82)
        y = 300
        for line in wrapped[:22]:
            draw.text((105, y), line, font=self._font(28), fill="#20231f")
            y += 43
        draw.text((105, height - 140), "Connect an image-capable 9Router model to replace this proof.", font=self._font(22), fill="#666")
        image.save(destination)

