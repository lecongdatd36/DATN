"""Decode uploads and store only bounded, metadata-free dish pictures."""
from io import BytesIO
import logging
from uuid import uuid4
import warnings

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile
from PIL import Image, ImageOps, UnidentifiedImageError

logger = logging.getLogger(__name__)
MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 20_000_000


def validate_upload_size(upload):
    if upload and not getattr(upload, "_committed", False) and upload.size > MAX_BYTES:
        raise ValidationError("Ảnh món không được vượt quá 5 MB.")


def prepare_dish_image(upload):
    if not isinstance(upload, UploadedFile):
        raise ValidationError({"image": "Vui lòng chọn một tệp ảnh để tải lên."})
    try:
        validate_upload_size(upload)
        upload.seek(0)
        data = upload.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValidationError("Ảnh món không được vượt quá 5 MB.")
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as source:
                if source.format not in ("JPEG", "PNG", "WEBP"):
                    raise ValidationError("Chỉ nhận ảnh JPEG, PNG hoặc WebP.")
                if getattr(source, "is_animated", False):
                    raise ValidationError("Vui lòng chọn ảnh tĩnh, không dùng ảnh động.")
                if source.width * source.height > MAX_PIXELS:
                    raise ValidationError("Ảnh không được vượt quá 20 triệu điểm ảnh.")
                source.verify()
            with Image.open(BytesIO(data)) as source:
                source.load()
                oriented = ImageOps.exif_transpose(source)
                oriented.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
                rgba = oriented.convert("RGBA")
                # A fresh canvas drops EXIF, GPS, ICC and other uploaded metadata.
                clean = Image.new("RGB", rgba.size, "white")
                clean.paste(rgba, mask=rgba.getchannel("A"))
        result = []
        token = uuid4().hex
        for label, size, quality in (("main", 1200, 82), ("thumb", 320, 78)):
            output = clean.copy()
            output.thumbnail((size, size), Image.Resampling.LANCZOS)
            buffer = BytesIO()
            output.save(buffer, format="WEBP", quality=quality, method=4)
            result.append((f"dishes/{token}-{label}.webp", ContentFile(buffer.getvalue())))
        return result
    except ValidationError as error:
        raise ValidationError({"image": error.messages}) from error
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombWarning, Image.DecompressionBombError) as error:
        raise ValidationError({"image": "Tệp ảnh bị lỗi hoặc không phải ảnh JPEG, PNG, WebP hợp lệ."}) from error
    finally:
        upload.seek(0)


def delete_unreferenced_images(names):
    """After commit only; storage failure must not undo an already committed edit."""
    from django.db.models import Q
    from .models import Dish
    storage = Dish._meta.get_field("image").storage
    for name in names:
        if name and not Dish.objects.filter(Q(image=name) | Q(thumbnail=name)).exists():
            try:
                storage.delete(name)
            except OSError:
                logger.exception("Unable to remove unused dish image %s", name)
