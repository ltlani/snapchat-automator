from pathlib import Path

from PIL import Image


image = Image.new("RGB", (1080, 1920), "black")

Path("assets/outputs").mkdir(parents=True, exist_ok=True)
image.save("assets/outputs/streak.jpg", quality=95)
