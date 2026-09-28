from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


image = Image.new("RGB", (1080, 1920), "black")
font = ImageFont.truetype("assets/fonts/Inter-VariableFont_opsz,wght.ttf", 64)
draw = ImageDraw.Draw(image)
draw.text((540, 960), "a", font=font, fill="white", anchor="mm")

Path("assets/outputs").mkdir(parents=True, exist_ok=True)
image.save("assets/outputs/streak.jpg", quality=95)
