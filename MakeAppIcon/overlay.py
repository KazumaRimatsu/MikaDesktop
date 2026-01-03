import io
import os
from typing import Union
from PIL import Image

def _to_pil(image_data: Union[bytes, str, Image.Image]) -> Image.Image:
	# 支持 bytes, 文件路径 或 已有 PIL Image
	if isinstance(image_data, Image.Image):
		return image_data.convert("RGBA")
	if isinstance(image_data, (bytes, bytearray)):
		return Image.open(io.BytesIO(image_data)).convert("RGBA")
	if isinstance(image_data, str) or hasattr(image_data, "__fspath__"):
		return Image.open(image_data).convert("RGBA")
	raise TypeError("image_data must be bytes, file path, or PIL.Image.Image")

def compose_on_template(image_data: Union[bytes, str, Image.Image],
						template_path: str = None,
						size: tuple = (64, 64),
						output_format: str = "PNG") -> bytes:
	"""
	将输入图像（期望 64x64，若不是则会缩放）居中叠放到模板 app_model.png 上。
	返回合成后的图像数据（PNG bytes）。
	template_path: 可选，默认使用与此模块同目录下的 app_model.png
	"""
	# 转为 PIL
	src = _to_pil(image_data)
	src = src.resize((128,128), Image.LANCZOS)

	# 模板路径
	if template_path is None:
		template_path = os.path.join(os.path.dirname(__file__), "app_model.png")
	if not os.path.exists(template_path):
		raise FileNotFoundError(f"template not found: {template_path}")

	template = Image.open(template_path).convert("RGBA")

	# 计算居中位置并粘贴
	tw, th = template.size
	sw, sh = src.size
	left = (tw - sw) // 2
	top = (th - sh) // 2
	template.paste(src, (left, top), src)

	# 输出为 bytes
	buf = io.BytesIO()
	template.save(buf, format=output_format)
	return buf.getvalue()
