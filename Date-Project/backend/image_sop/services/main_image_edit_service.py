from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path

from PIL import Image as PilImage

from backend.image_sop.config import Settings

DETAIL_TRANSFORMS: list[tuple[str, str]] = [
    ("center_zoom", "居中放大截取产品核心区域"),
    ("corner_br", "截取右下局部细节"),
    ("corner_tl", "截取左上局部细节"),
    ("rotate_left", "逆时针旋转15度"),
    ("rotate_right", "顺时针旋转12度"),
    ("flip_center", "水平翻转后居中裁剪"),
]


class MainImageEditService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.settings.web_ref_path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def should_edit(theme: str, index: int) -> bool:
        if index <= 1 or "主图" in theme:
            return False
        return any(keyword in theme for keyword in ("品质", "细节", "功能"))

    def create_detail_variant(
        self,
        main_image_path: Path,
        theme: str,
        index: int,
        sku: str,
    ) -> tuple[Path | None, str, str]:
        if not main_image_path.exists():
            return None, "", ""

        transform_name, transform_desc = DETAIL_TRANSFORMS[(index - 2) % len(DETAIL_TRANSFORMS)]
        safe_sku = re.sub(r"[^\w\-]+", "_", sku)[:40]
        filename = f"{safe_sku}_main_edit_{index}.jpg"
        output = self.settings.web_ref_path / filename

        try:
            with PilImage.open(main_image_path) as img:
                img = img.convert("RGB")
                # 限制处理尺寸，避免大内存占用
                img.thumbnail((1600, 1600), PilImage.Resampling.LANCZOS)
                edited = self._apply_transform(img, transform_name)
                edited.thumbnail((1200, 1200), PilImage.Resampling.LANCZOS)
                buffer = BytesIO()
                edited.save(buffer, format="JPEG", quality=90)
                output.write_bytes(buffer.getvalue())
            return output, f"/api/web-refs/{filename}", transform_desc
        except Exception:
            return None, "", transform_desc

    def _apply_transform(self, img: PilImage.Image, transform_name: str) -> PilImage.Image:
        if transform_name == "center_zoom":
            return self._center_zoom(img, 0.62)
        if transform_name == "corner_br":
            return self._corner_crop(img, "br", 0.55)
        if transform_name == "corner_tl":
            return self._corner_crop(img, "tl", 0.55)
        if transform_name == "rotate_left":
            return self._rotate_and_fit(img, 15)
        if transform_name == "rotate_right":
            return self._rotate_and_fit(img, -12)
        if transform_name == "flip_center":
            flipped = img.transpose(PilImage.Transpose.FLIP_LEFT_RIGHT)
            return self._center_zoom(flipped, 0.7)
        return self._center_zoom(img, 0.65)

    @staticmethod
    def _center_zoom(img: PilImage.Image, ratio: float) -> PilImage.Image:
        width, height = img.size
        crop_w = max(int(width * ratio), 1)
        crop_h = max(int(height * ratio), 1)
        left = (width - crop_w) // 2
        top = (height - crop_h) // 2
        cropped = img.crop((left, top, left + crop_w, top + crop_h))
        return cropped.resize((width, height), PilImage.Resampling.LANCZOS)

    @staticmethod
    def _corner_crop(img: PilImage.Image, corner: str, ratio: float) -> PilImage.Image:
        width, height = img.size
        crop_w = max(int(width * ratio), 1)
        crop_h = max(int(height * ratio), 1)
        if corner == "br":
            box = (width - crop_w, height - crop_h, width, height)
        else:
            box = (0, 0, crop_w, crop_h)
        cropped = img.crop(box)
        return cropped.resize((width, height), PilImage.Resampling.LANCZOS)

    @staticmethod
    def _rotate_and_fit(img: PilImage.Image, angle: float) -> PilImage.Image:
        rotated = img.rotate(angle, expand=True, fillcolor=(255, 255, 255))
        return MainImageEditService._center_zoom(rotated, 0.78)
