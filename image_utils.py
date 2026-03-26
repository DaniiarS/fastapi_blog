import uuid
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps

PROFILE_PICS_DIR = Path("media/profile_pics")

def process_file_image(content: bytes) -> str:
    with Image.open(BytesIO(content)) as original:
        # deals with rotation metadata
        img = ImageOps.exif_transpose(original)

        # deals with scaling and corping images while preserving the quality
        # example: if the image size is 800 x 600
        # resize it so that one of the sides is 300 -> image becomes 400 x 300
        # center the image and corp it -> image becomes corped 50 px from both sides while being centered
        # final image is 300 x 300 in size
        img = ImageOps.fit(img, (300, 300), method=Image.Resampling.LANCZOS)

        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")

        filename = f"{uuid.uuid4().hex}.jpg"
        filepath = PROFILE_PICS_DIR / filename # / is overloaded to join paths (cleaner than os.path.join)

        PROFILE_PICS_DIR.mkdir(parents=True, exist_ok=True)

        img.save(filepath, "JPEG", quailty=85, optimize=True)
    
    return filename

def delete_profile_image(filename: str | None) -> None:
    if filename is None:
        return
    
    filepath = PROFILE_PICS_DIR / filename
    if filepath.exists():
        filepath.unlink()