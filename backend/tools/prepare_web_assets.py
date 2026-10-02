"""Create web-size brand assets without touching the original artwork.

Run with Pillow installed: python backend/tools/prepare_web_assets.py
The assistant sheet uses lossless WebP and is checked byte-for-byte as RGBA.
"""
from pathlib import Path

from PIL import Image


def main():
    assets = Path(__file__).resolve().parents[2] / "research-room" / "public"
    icon = Image.open(assets / "qier-icon.png").convert("RGBA")
    for size in (48, 192):
        icon.resize((size, size), Image.Resampling.LANCZOS).save(
            assets / f"qier-icon-{size}.png", optimize=True
        )
    icon.resize((96, 96), Image.Resampling.LANCZOS).save(
        assets / "qier-icon-96.webp", lossless=True, method=6
    )
    sprite = Image.open(assets / "xiaoqi-assistant-sprites.png").convert("RGBA")
    output = assets / "xiaoqi-assistant-sprites.lossless.webp"
    sprite.save(output, lossless=True, method=6)
    assert Image.open(output).convert("RGBA").tobytes() == sprite.tobytes()
    for path in [*assets.glob("qier-icon-*.png"), assets / "qier-icon-96.webp", output]:
        print(f"{path.name}: {path.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
