import io

from PIL import Image


def image_to_bytes(image: Image, file_format: str = "PNG") -> bytes:
    with io.BytesIO() as output:
        image.save(output, format=file_format)
        return output.getvalue()
