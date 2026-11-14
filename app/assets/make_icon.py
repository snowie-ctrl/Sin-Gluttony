"""Makes gluttony.ico (the exe's icon) from the premade gluttonyAppIcon.png.

The PNG is 236 x 224, so it is centred on a transparent square first; Windows would otherwise stretch it.
Run with the scraper's venv, which has Pillow:
    scraper\\.venv\\Scripts\\python.exe -I app\\assets\\make_icon.py app\\assets\\images\\gluttonyAppIcon.png app\\assets\\gluttony.ico
"""
import sys

from PIL import Image

SIZES = [16, 24, 32, 48, 64, 128, 256]


def main(source, target):
    picture = Image.open(source).convert("RGBA")
    side = max(picture.size)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(picture, ((side - picture.width) // 2, (side - picture.height) // 2))
    square = square.resize((256, 256), Image.Resampling.LANCZOS)
    square.save(target, format="ICO", sizes=[(s, s) for s in SIZES])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
