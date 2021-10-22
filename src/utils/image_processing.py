from PIL import Image
import io

def make_thumbnail(file_path, size = (225, 225)):
    return resize_image(file_path, size)

def make_preview(file_path, size = (500, 500)):
    return resize_image(file_path, size)

def make_banner(file_path):
    return resize_image(file_path, (650, 650))

def make_icon(file_path):
    return resize_image(file_path, (100, 100))

def resize_image(file_path, size, quality = 80):
    try:
        with Image.open(file_path) as image:
            image.verify()
    except:
        return None

    with Image.open(file_path) as image:
        image = image.convert('RGB')
        image.thumbnail(size)

        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format = 'JPEG', quality = quality)
        img_byte_arr.seek(0)
        return (img_byte_arr.read(), 'image/jpeg')
