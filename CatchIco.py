"""
WinIconExtract - Windows 应用图标提取库
版本: 1.0.0
支持: Windows 7/8/10/11
依赖: pywin32, Pillow
"""
import os
import ctypes
import winreg
from pathlib import Path
from typing import Optional, List, Dict, Union
from dataclasses import dataclass
from enum import IntEnum, IntFlag
import warnings

# 类型提示
try:
    from typing import Literal
except ImportError:
    from typing_extensions import Literal

# 可选依赖
try:
    import win32gui
    import win32ui
    import win32con
    import win32api
    PYWIN32_AVAILABLE = True
except ImportError:
    PYWIN32_AVAILABLE = False
    warnings.warn("pywin32 未安装，部分功能可能受限")

try:
    from PIL import Image
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    warnings.warn("Pillow 未安装，无法处理图像")


# ====================== 常量定义 ======================

class IconSize(IntEnum):
    """图标尺寸枚举"""
    SMALL = 16
    MEDIUM = 32
    LARGE = 48
    EXTRALARGE = 128
    JUMBO = 256
    THUMBNAIL = 96  # 缩略图尺寸


class IconType(IntFlag):
    """图标类型标志"""
    EXECUTABLE = 1      # 可执行文件
    DOCUMENT = 2        # 文档文件
    FOLDER = 4          # 文件夹
    SHORTCUT = 8        # 快捷方式
    UWP = 16            # UWP应用
    SYSTEM = 32         # 系统图标


class IconFormat(IntEnum):
    """图标输出格式"""
    PNG = 1
    ICO = 2
    BMP = 3
    JPEG = 4


@dataclass
class IconInfo:
    """图标信息容器"""
    path: str                    # 图标源路径
    index: int                   # 图标索引
    width: int                   # 宽度
    height: int                  # 高度
    bits_per_pixel: int          # 位深度
    format: str                  # 原始格式
    size_bytes: int              # 数据大小


@dataclass
class ExtractedIcon:
    """提取的图标数据"""
    image: Optional['Image.Image']   # PIL图像对象
    raw_data: bytes                  # 原始字节数据
    info: IconInfo                   # 图标信息
    success: bool                    # 提取是否成功
    error: Optional[str] = None      # 错误信息


# ====================== 核心类 ======================

class WindowsIconExtractor:
    """
    Windows图标提取器主类
    
    特性:
    - 支持从EXE、DLL、ICO文件提取图标
    - 支持从文件关联获取图标
    - 支持UWP应用图标提取
    - 支持系统图标获取
    - 支持多种尺寸和格式输出
    - 内置图标缓存机制
    """
    
    def __init__(self, enable_cache: bool = True, cache_size: int = 100):
        """
        初始化图标提取器
        
        Args:
            enable_cache: 是否启用图标缓存
            cache_size: 缓存大小（最大条目数）
        """
        # 不在这里强制抛出 ImportError，延迟报错以避免模块导入失败
        self._missing_dependencies = []
        if not PYWIN32_AVAILABLE:
            self._missing_dependencies.append("pywin32")
        if not PILLOW_AVAILABLE:
            self._missing_dependencies.append("Pillow")
        if self._missing_dependencies:
            self._dep_error = f"缺失依赖: {', '.join(self._missing_dependencies)}"
        else:
            self._dep_error = None
         
        self._cache_enabled = enable_cache
        self._icon_cache = {}  # 图标缓存字典
        self._max_cache_size = cache_size
        
        # 系统路径
        self._system_paths = {
            'windows': os.environ.get('SystemRoot', 'C:\\Windows'),
            'program_files': os.environ.get('ProgramFiles', 'C:\\Program Files'),
            'program_files_x86': os.environ.get('ProgramFiles(x86)', 'C:\\Program Files (x86)'),
            'appdata': os.environ.get('AppData', ''),
            'local_appdata': os.environ.get('LocalAppData', ''),
        }
    
    def _check_deps(self):
        if getattr(self, '_dep_error', None):
            return False, self._dep_error
        return True, None
    
    # ====================== 公共API ======================
    
    def extract_icon(self, 
                    source: Union[str, Path, int], 
                    size: Union[int, IconSize] = IconSize.LARGE,
                    icon_index: int = 0,
                    icon_type: Optional[IconType] = None) -> ExtractedIcon:
        """
        提取图标（智能方法，自动判断源类型）
        
        Args:
            source: 图标源，可以是文件路径或系统图标ID
            size: 图标尺寸，支持整数或IconSize枚举
            icon_index: 图标索引（对于多图标的文件）
            icon_type: 图标类型提示
            
        Returns:
            ExtractedIcon: 提取的图标数据
        """
        # 规范化参数
        if isinstance(size, IconSize):
            size = size.value
        
        # 检查缓存
        cache_key = self._make_cache_key(source, size, icon_index)
        if self._cache_enabled and cache_key in self._icon_cache:
            return self._icon_cache[cache_key]
        
        # 判断源类型并分发
        if isinstance(source, int) or str(source).isdigit():
            # 系统图标ID
            icon_id = int(source)
            result = self._extract_system_icon(icon_id, size)
        elif isinstance(source, (str, Path)):
            source_path = str(source)
            
            if source_path.startswith('::'):
                # 特殊文件夹（如::{20D04FE0-3AEA-1069-A2D8-08002B30309D}）
                result = self._extract_special_folder_icon(source_path, size)
            elif source_path.lower().endswith(('.exe', '.dll', '.ico')):
                # 可执行文件或图标文件
                result = self._extract_file_icon(source_path, size, icon_index)
            elif source_path.lower().endswith('.lnk'):
                # 快捷方式
                result = self._extract_shortcut_icon(source_path, size)
            elif '.' in source_path:
                # 可能是文件扩展名
                result = self._extract_extension_icon(source_path, size)
            else:
                # 尝试作为文件路径
                if os.path.exists(source_path):
                    result = self._extract_file_icon(source_path, size, icon_index)
                else:
                    result = ExtractedIcon(
                        image=None,
                        raw_data=b'',
                        info=IconInfo(source_path, icon_index, size, size, 32, 'Unknown', 0),
                        success=False,
                        error=f"无法识别的图标源: {source_path}"
                    )
        else:
            result = ExtractedIcon(
                image=None,
                raw_data=b'',
                info=IconInfo(str(source), icon_index, size, size, 32, 'Unknown', 0),
                success=False,
                error="不支持的图标源类型"
            )
        
        # 缓存结果
        if self._cache_enabled and result.success:
            self._add_to_cache(cache_key, result)
        
        return result
    
    def extract_file_icon(self, 
                         file_path: Union[str, Path], 
                         size: Union[int, IconSize] = IconSize.LARGE,
                         icon_index: int = 0) -> ExtractedIcon:
        """
        从文件提取图标
        
        Args:
            file_path: 文件路径
            size: 图标尺寸
            icon_index: 图标索引
            
        Returns:
            ExtractedIcon: 提取的图标数据
        """
        return self.extract_icon(file_path, size, icon_index)
    
    def extract_system_icon(self, 
                           icon_id: int, 
                           size: Union[int, IconSize] = IconSize.LARGE) -> ExtractedIcon:
        """
        提取系统图标
        
        Args:
            icon_id: 系统图标ID
            size: 图标尺寸
            
        Returns:
            ExtractedIcon: 提取的图标数据
        """
        return self.extract_icon(icon_id, size)
    
    def extract_extension_icon(self, 
                              extension: str, 
                              size: Union[int, IconSize] = IconSize.LARGE) -> ExtractedIcon:
        """
        从文件扩展名获取关联图标
        
        Args:
            extension: 文件扩展名（如'.txt', 'txt'）
            size: 图标尺寸
            
        Returns:
            ExtractedIcon: 提取的图标数据
        """
        if not extension.startswith('.'):
            extension = '.' + extension
        return self.extract_icon(extension, size)
    
    def extract_shortcut_icon(self, 
                             shortcut_path: Union[str, Path], 
                             size: Union[int, IconSize] = IconSize.LARGE) -> ExtractedIcon:
        """
        从快捷方式提取图标
        
        Args:
            shortcut_path: 快捷方式路径
            size: 图标尺寸
            
        Returns:
            ExtractedIcon: 提取的图标数据
        """
        return self.extract_icon(shortcut_path, size)
    
    def extract_uwp_icon(self, 
                        app_id: str, 
                        size: Union[int, IconSize] = IconSize.LARGE) -> ExtractedIcon:
        """
        提取UWP应用图标
        
        Args:
            app_id: UWP应用ID或名称
            size: 图标尺寸
            
        Returns:
            ExtractedIcon: 提取的图标数据
        """
        # 尝试解析UWP应用信息
        uwp_info = self._get_uwp_app_info(app_id)
        if uwp_info and 'logo' in uwp_info:
            logo_path = uwp_info['logo']
            if os.path.exists(logo_path):
                return self.extract_icon(logo_path, size)
        
        return ExtractedIcon(
            image=None,
            raw_data=b'',
            info=IconInfo(app_id, 0, size, size, 32, 'Unknown', 0),
            success=False,
            error=f"未找到UWP应用: {app_id}"
        )
    
    def save_icon(self, 
                 extracted_icon: ExtractedIcon, 
                 save_path: Union[str, Path], 
                 format: Union[str, IconFormat] = 'PNG',
                 quality: int = 95) -> bool:
        """
        保存提取的图标到文件
        
        Args:
            extracted_icon: 提取的图标数据
            save_path: 保存路径
            format: 保存格式
            quality: 保存质量（JPEG格式有效）
            
        Returns:
            bool: 是否保存成功
        """
        if not extracted_icon.success or not extracted_icon.image:
            return False
        
        try:
            if isinstance(format, IconFormat):
                format = format.name
            
            save_path = str(save_path)
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            
            save_kwargs = {'format': format}
            if format.upper() == 'JPEG':
                save_kwargs['quality'] = quality
            
            extracted_icon.image.save(save_path, **save_kwargs)
            return True
        except Exception as e:
            warnings.warn(f"保存图标失败: {e}")
            return False
    
    def get_icon_as_bytes(self, 
                         extracted_icon: ExtractedIcon, 
                         format: Union[str, IconFormat] = 'PNG') -> Optional[bytes]:
        """
        获取图标的字节数据
        
        Args:
            extracted_icon: 提取的图标数据
            format: 输出格式
            
        Returns:
            bytes: 图标字节数据，失败返回None
        """
        if not extracted_icon.success or not extracted_icon.image:
            return None
        
        try:
            import io
            buffer = io.BytesIO()
            
            if isinstance(format, IconFormat):
                format = format.name
            
            save_kwargs = {'format': format}
            extracted_icon.image.save(buffer, **save_kwargs)
            return buffer.getvalue()
        except Exception as e:
            warnings.warn(f"获取图标字节数据失败: {e}")
            return None
    
    def list_icons_in_file(self, 
                          file_path: Union[str, Path]) -> List[IconInfo]:
        """
        列出文件中的所有图标
        
        Args:
            file_path: 文件路径
            
        Returns:
            List[IconInfo]: 图标信息列表
        """
        file_path = str(file_path)
        if not os.path.exists(file_path):
            return []
        
        icons = []
        index = 0
        
        while True:
            try:
                # 尝试提取图标
                result = self._extract_file_icon(file_path, 32, index)
                if result.success:
                    icons.append(result.info)
                    index += 1
                else:
                    break
            except:
                break
        
        return icons
    
    def clear_cache(self) -> None:
        """清除图标缓存"""
        self._icon_cache.clear()
    
    # ====================== 私有方法 ======================
    
    def _make_cache_key(self, source, size, index) -> str:
        """生成缓存键"""
        return f"{source}|{size}|{index}"
    
    def _add_to_cache(self, key: str, icon: ExtractedIcon) -> None:
        """添加图标到缓存"""
        if len(self._icon_cache) >= self._max_cache_size:
            # 移除最早的一个条目（简单的LRU策略）
            oldest_key = next(iter(self._icon_cache))
            del self._icon_cache[oldest_key]
        self._icon_cache[key] = icon
    
    def _extract_file_icon(self, 
                           file_path: str, 
                           size: int, 
                           icon_index: int = 0) -> ExtractedIcon:
        """从文件提取图标的内部实现"""
        ok, err = self._check_deps()
        if not ok:
            return ExtractedIcon(
                image=None,
                raw_data=b'',
                info=IconInfo(file_path, icon_index, size, size, 32, 'Unknown', 0),
                success=False,
                error=err
            )
        try:
            # 使用 ExtractIconEx 获取图标句柄
            large_icons = []
            small_icons = []
            
            # 获取大图标和小图标
            result = win32gui.ExtractIconEx(file_path, icon_index)
            if result and len(result) == 2:
                large_icons, small_icons = result
            
            if not large_icons and not small_icons:
                return ExtractedIcon(
                    image=None,
                    raw_data=b'',
                    info=IconInfo(file_path, icon_index, size, size, 32, 'Unknown', 0),
                    success=False,
                    error="未找到图标"
                )
            
            # 选择合适的图标句柄
            hicon = large_icons[0] if large_icons else small_icons[0]
            
            # 转换为PIL图像
            image = self._hicon_to_pil(hicon, size)
            
            # 获取图标信息
            icon_info = win32gui.GetIconInfo(hicon)
            
            # 清理资源
            for icon in large_icons:
                win32gui.DestroyIcon(icon)
            for icon in small_icons:
                win32gui.DestroyIcon(icon)
            
            # 创建图标信息
            info = IconInfo(
                path=file_path,
                index=icon_index,
                width=size,
                height=size,
                bits_per_pixel=32,  # 假设32位
                format='ICO',
                size_bytes=len(self._pil_to_bytes(image, 'PNG'))
            )
            
            return ExtractedIcon(
                image=image,
                raw_data=self._pil_to_bytes(image, 'PNG'),
                info=info,
                success=True
            )
            
        except Exception as e:
            return ExtractedIcon(
                image=None,
                raw_data=b'',
                info=IconInfo(file_path, icon_index, size, size, 32, 'Unknown', 0),
                success=False,
                error=f"提取图标失败: {e}"
            )
    
    def _extract_system_icon(self, icon_id: int, size: int) -> ExtractedIcon:
        """提取系统图标的内部实现"""
        try:
            # 获取系统图标句柄
            hicon = win32gui.LoadIcon(0, icon_id)
            if not hicon:
                # 尝试从shell32.dll获取
                shell32 = ctypes.windll.shell32
                hicon = shell32.ExtractIconW(0, "shell32.dll", icon_id)
            
            if not hicon:
                return ExtractedIcon(
                    image=None,
                    raw_data=b'',
                    info=IconInfo(f"SystemIcon:{icon_id}", 0, size, size, 32, 'Unknown', 0),
                    success=False,
                    error="未找到系统图标"
                )
            
            # 转换为PIL图像
            image = self._hicon_to_pil(hicon, size)
            
            # 创建图标信息
            info = IconInfo(
                path=f"SystemIcon:{icon_id}",
                index=0,
                width=size,
                height=size,
                bits_per_pixel=32,
                format='ICO',
                size_bytes=len(self._pil_to_bytes(image, 'PNG'))
            )
            
            return ExtractedIcon(
                image=image,
                raw_data=self._pil_to_bytes(image, 'PNG'),
                info=info,
                success=True
            )
            
        except Exception as e:
            return ExtractedIcon(
                image=None,
                raw_data=b'',
                info=IconInfo(f"SystemIcon:{icon_id}", 0, size, size, 32, 'Unknown', 0),
                success=False,
                error=f"提取系统图标失败: {e}"
            )
    
    def _extract_extension_icon(self, extension: str, size: int) -> ExtractedIcon:
        """从扩展名提取图标的内部实现"""
        try:
            # 获取文件类型信息
            file_type = win32gui.RegQueryValue(
                winreg.HKEY_CLASSES_ROOT, 
                extension
            )
            
            if file_type:
                # 获取默认图标
                icon_key_path = f"{file_type}\\DefaultIcon"
                try:
                    icon_path = win32gui.RegQueryValue(
                        winreg.HKEY_CLASSES_ROOT,
                        icon_key_path
                    )
                except:
                    # 尝试直接获取扩展名的图标
                    icon_key_path = f"{extension}\\DefaultIcon"
                    icon_path = win32gui.RegQueryValue(
                        winreg.HKEY_CLASSES_ROOT,
                        icon_key_path
                    )
                
                if icon_path:
                    # 解析图标路径（可能包含索引，如 "shell32.dll,1"）
                    if ',' in icon_path:
                        icon_file, icon_idx = icon_path.rsplit(',', 1)
                        icon_idx = int(icon_idx)
                    else:
                        icon_file = icon_path
                        icon_idx = 0
                    
                    # 展开环境变量
                    icon_file = os.path.expandvars(icon_file)
                    
                    # 如果路径包含系统目录引用，转换为实际路径
                    if '%' in icon_file:
                        icon_file = os.path.expandvars(icon_file)
                    
                    return self.extract_icon(icon_file, size, icon_idx)
            
            # 如果找不到，使用未知文件图标
            return self.extract_system_icon(0, size)
            
        except Exception as e:
            return ExtractedIcon(
                image=None,
                raw_data=b'',
                info=IconInfo(extension, 0, size, size, 32, 'Unknown', 0),
                success=False,
                error=f"提取扩展名图标失败: {e}"
            )
    
    def _extract_shortcut_icon(self, shortcut_path: str, size: int) -> ExtractedIcon:
        """从快捷方式提取图标的内部实现"""
        try:
            # 解析快捷方式获取目标路径
            from win32com.client import Dispatch
            shell = Dispatch("WScript.Shell")
            shortcut = shell.CreateShortcut(shortcut_path)
            target_path = shortcut.TargetPath
            
            if target_path and os.path.exists(target_path):
                # 使用目标文件的图标
                return self.extract_icon(target_path, size)
            else:
                # 使用快捷方式自身的图标
                return self._extract_file_icon(shortcut_path, size)
                
        except Exception as e:
            return ExtractedIcon(
                image=None,
                raw_data=b'',
                info=IconInfo(shortcut_path, 0, size, size, 32, 'Unknown', 0),
                success=False,
                error=f"提取快捷方式图标失败: {e}"
            )
    
    def _extract_special_folder_icon(self, folder_clsid: str, size: int) -> ExtractedIcon:
        """提取特殊文件夹图标的内部实现"""
        try:
            # 使用 SHGetFileInfo 获取特殊文件夹图标
            from ctypes import wintypes
            from ctypes import windll, Structure, POINTER, byref
            
            class SHFILEINFO(Structure):
                _fields_ = [
                    ("hIcon", wintypes.HANDLE),
                    ("iIcon", wintypes.INT),
                    ("dwAttributes", wintypes.DWORD),
                    ("szDisplayName", wintypes.WCHAR * 260),
                    ("szTypeName", wintypes.WCHAR * 80)
                ]
            
            SHGFI_ICON = 0x100
            SHGFI_LARGEICON = 0x0
            SHGFI_SMALLICON = 0x1
            SHGFI_PIDL = 0x8
            
            shell32 = windll.shell32
            shfi = SHFILEINFO()
            
            # 转换为宽字符串
            clsid_w = folder_clsid
            
            flags = SHGFI_ICON | SHGFI_LARGEICON | SHGFI_PIDL
            
            result = shell32.SHGetFileInfoW(
                clsid_w,
                0,
                byref(shfi),
                wintypes.sizeof(shfi),
                flags
            )
            
            if result and shfi.hIcon:
                # 转换为PIL图像
                image = self._hicon_to_pil(shfi.hIcon, size)
                
                info = IconInfo(
                    path=folder_clsid,
                    index=0,
                    width=size,
                    height=size,
                    bits_per_pixel=32,
                    format='ICO',
                    size_bytes=len(self._pil_to_bytes(image, 'PNG'))
                )
                
                return ExtractedIcon(
                    image=image,
                    raw_data=self._pil_to_bytes(image, 'PNG'),
                    info=info,
                    success=True
                )
            else:
                return ExtractedIcon(
                    image=None,
                    raw_data=b'',
                    info=IconInfo(folder_clsid, 0, size, size, 32, 'Unknown', 0),
                    success=False,
                    error="无法获取特殊文件夹图标"
                )
                
        except Exception as e:
            return ExtractedIcon(
                image=None,
                raw_data=b'',
                info=IconInfo(folder_clsid, 0, size, size, 32, 'Unknown', 0),
                success=False,
                error=f"提取特殊文件夹图标失败: {e}"
            )
    
    def _hicon_to_pil(self, hicon, size: int) -> 'Image.Image':
        """将图标句柄转换为PIL图像"""
        ok, err = self._check_deps()
        if not ok:
            raise RuntimeError(err)
        # 创建内存DC
        hdc = win32ui.CreateDCFromHandle(win32gui.GetDC(0))
        hbmp = win32ui.CreateBitmap()
        hbmp.CreateCompatibleBitmap(hdc, size, size)
        hdc = hdc.CreateCompatibleDC()
        hdc.SelectObject(hbmp)
        
        # 绘制图标
        hdc.FillSolidRect((0, 0, size, size), 0xFFFFFF)  # 白色背景
        win32gui.DrawIconEx(
            hdc.GetHandleOutput(), 
            0, 0, hicon, 
            size, size, 
            0, None, 
            win32con.DI_NORMAL
        )
        
        # 转换为PIL Image
        bmpinfo = hbmp.GetInfo()
        bmpstr = hbmp.GetBitmapBits(True)
        
        image = Image.frombuffer(
            'RGB',
            (bmpinfo['bmWidth'], bmpinfo['bmHeight']),
            bmpstr, 'raw', 'BGRX', 0, 1
        )
        
        return image
    
    def _pil_to_bytes(self, image: 'Image.Image', format: str = 'PNG') -> bytes:
        """将PIL图像转换为字节数据"""
        import io
        buffer = io.BytesIO()
        image.save(buffer, format=format)
        return buffer.getvalue()
    
    def _get_uwp_app_info(self, app_id: str) -> Optional[Dict]:
        """获取UWP应用信息（简化实现）"""
        # 注意：完整的UWP应用枚举需要复杂的Windows API调用
        # 这里提供简化实现
        try:
            import winreg
            
            # 在注册表中查找UWP应用
            uwp_key = r"SOFTWARE\Classes\Local Settings\Software\Microsoft\Windows\CurrentVersion\AppModel\Repository\Families"
            
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, uwp_key)
            except:
                return None
            
            app_info = {}
            
            # 遍历应用包
            for i in range(winreg.QueryInfoKey(key)[0]):
                try:
                    family_name = winreg.EnumKey(key, i)
                    family_key = winreg.OpenKey(key, family_name)
                    
                    # 检查是否匹配app_id
                    if app_id.lower() in family_name.lower():
                        # 获取包信息
                        try:
                            package_key = winreg.OpenKey(family_key, "Packages")
                            
                            for j in range(winreg.QueryInfoKey(package_key)[0]):
                                package_name = winreg.EnumKey(package_key, j)
                                if app_id.lower() in package_name.lower():
                                    # 找到匹配的包
                                    app_info['name'] = package_name
                                    
                                    # 尝试获取资源路径
                                    resource_key_path = f"{uwp_key}\\{family_name}\\Packages\\{package_name}\\Resources"
                                    try:
                                        resource_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, resource_key_path)
                                        
                                        # 查找Logo文件
                                        for k in range(winreg.QueryInfoKey(resource_key)[1]):
                                            try:
                                                name, value, _ = winreg.EnumValue(resource_key, k)
                                                if 'logo' in name.lower() and value:
                                                    # 构建完整路径
                                                    base_path = os.path.join(
                                                        os.environ.get('ProgramFiles', 'C:\\Program Files'),
                                                        'WindowsApps',
                                                        package_name
                                                    )
                                                    logo_path = os.path.join(base_path, value)
                                                    if os.path.exists(logo_path):
                                                        app_info['logo'] = logo_path
                                                        break
                                            except:
                                                continue
                                        
                                        winreg.CloseKey(resource_key)
                                    except:
                                        pass
                                    
                                    break
                            
                            winreg.CloseKey(package_key)
                        except:
                            pass
                    
                    winreg.CloseKey(family_key)
                    
                    if app_info:
                        break
                        
                except:
                    continue
            
            winreg.CloseKey(key)
            return app_info if app_info else None
            
        except Exception:
            return None


# ====================== 便捷函数 ======================

class SystemIcons:
    """系统图标ID常量类"""
    # 标准系统图标
    APPLICATION = 100
    DOCUMENT = 1
    FOLDER = 3
    FOLDER_OPEN = 4
    DRIVE_525 = 6
    DRIVE_35 = 7
    DRIVE_FIXED = 8
    DRIVE_NETWORK = 9
    DRIVE_NETWORK_DISABLED = 10
    DRIVE_CD = 11
    DRIVE_RAM = 12
    WORLD = 15
    SERVER = 16
    PRINTER = 17
    MY_NETWORK = 18
    FIND = 22
    HELP = 23
    SHORTCUT = 29
    UI_GADGET = 123
    # Windows特殊图标
    WARNING = 101
    QUESTION = 102
    ERROR = 103
    INFO = 104
    SHIELD = 106
    # Shell32.dll中的图标
    COMPUTER = 15          # 我的电脑
    RECYCLE_BIN = 31       # 回收站（空）
    RECYCLE_BIN_FULL = 32  # 回收站（满）
    CONTROL_PANEL = 21     # 控制面板
    NETWORK = 17           # 网络
    USERS = 109            # 用户文件夹


def extract_icon(source: Union[str, Path, int], 
                size: Union[int, IconSize] = IconSize.LARGE,
                icon_index: int = 0) -> ExtractedIcon:
    """
    便捷函数：提取图标
    
    Args:
        source: 图标源
        size: 图标尺寸
        icon_index: 图标索引
        
    Returns:
        ExtractedIcon: 提取的图标数据
    """
    extractor = WindowsIconExtractor()
    return extractor.extract_icon(source, size, icon_index)


def get_file_icon(file_path: Union[str, Path], 
                 size: Union[int, IconSize] = IconSize.LARGE) -> ExtractedIcon:
    """
    便捷函数：获取文件图标
    
    Args:
        file_path: 文件路径
        size: 图标尺寸
        
    Returns:
        ExtractedIcon: 提取的图标数据
    """
    extractor = WindowsIconExtractor()
    return extractor.extract_file_icon(file_path, size)


def get_system_icon(icon_id: int, 
                   size: Union[int, IconSize] = IconSize.LARGE) -> ExtractedIcon:
    """
    便捷函数：获取系统图标
    
    Args:
        icon_id: 系统图标ID
        size: 图标尺寸
        
    Returns:
        ExtractedIcon: 提取的图标数据
    """
    extractor = WindowsIconExtractor()
    return extractor.extract_system_icon(icon_id, size)


def save_icon_to_file(extracted_icon: ExtractedIcon, 
                     save_path: Union[str, Path], 
                     format: str = 'PNG') -> bool:
    """
    便捷函数：保存图标到文件
    
    Args:
        extracted_icon: 提取的图标数据
        save_path: 保存路径
        format: 保存格式
        
    Returns:
        bool: 是否保存成功
    """
    extractor = WindowsIconExtractor()
    return extractor.save_icon(extracted_icon, save_path, format)


# ====================== 高级功能 ======================

class AdvancedIconExtractor(WindowsIconExtractor):
    """高级图标提取器（提供更多功能）"""
    
    def extract_all_sizes(self, 
                         source: Union[str, Path, int],
                         icon_index: int = 0) -> Dict[int, ExtractedIcon]:
        """
        提取所有尺寸的图标
        
        Args:
            source: 图标源
            icon_index: 图标索引
            
        Returns:
            Dict[int, ExtractedIcon]: 尺寸到图标的映射
        """
        sizes = [16, 32, 48, 64, 128, 256]
        result = {}
        
        for size in sizes:
            icon = self.extract_icon(source, size, icon_index)
            if icon.success:
                result[size] = icon
        
        return result
    
    def extract_icon_family(self, 
                           file_path: Union[str, Path]) -> Dict[str, List[ExtractedIcon]]:
        """
        提取图标族（包含所有尺寸的所有图标）
        
        Args:
            file_path: 文件路径
            
        Returns:
            Dict[str, List[ExtractedIcon]]: 图标索引到尺寸列表的映射
        """
        # 首先列出所有图标
        icons_info = self.list_icons_in_file(file_path)
        if not icons_info:
            return {}
        
        result = {}
        sizes = [16, 32, 48, 256]
        
        for icon_info in icons_info:
            icon_index = icon_info.index
            result[str(icon_index)] = []
            
            for size in sizes:
                icon = self.extract_icon(file_path, size, icon_index)
                if icon.success:
                    result[str(icon_index)].append(icon)
        
        return result
    
    def create_icon_file(self, 
                        icons: List[ExtractedIcon], 
                        output_path: Union[str, Path]) -> bool:
        """
        创建图标文件（ICO格式）
        
        Args:
            icons: 图标列表（不同尺寸）
            output_path: 输出路径
            
        Returns:
            bool: 是否创建成功
        """
        try:
            from PIL import Image
            
            # 将图标转换为ICO格式
            icon_images = []
            for icon in icons:
                if icon.success and icon.image:
                    icon_images.append(icon.image)
            
            if not icon_images:
                return False
            
            # 保存为ICO文件
            icon_images[0].save(
                output_path,
                format='ICO',
                append_images=icon_images[1:] if len(icon_images) > 1 else None
            )
            return True
            
        except Exception as e:
            warnings.warn(f"创建图标文件失败: {e}")
            return False