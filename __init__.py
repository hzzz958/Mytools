"""
自定义节点包初始化文件
支持多个节点模块
"""

# 导入所有节点模块
from .ffmpeg_node import NODE_CLASS_MAPPINGS as FFmpegMappings
from .ffmpeg_node import NODE_DISPLAY_NAME_MAPPINGS as FFmpegNames

# 如果有rife_node，也导入
try:
    from .rife_node import NODE_CLASS_MAPPINGS as RifeMappings
    from .rife_node import NODE_DISPLAY_NAME_MAPPINGS as RifeNames
except ImportError:
    RifeMappings = {}
    RifeNames = {}

# 合并所有节点
NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

# 添加FFmpeg节点
NODE_CLASS_MAPPINGS.update(FFmpegMappings)
NODE_DISPLAY_NAME_MAPPINGS.update(FFmpegNames)

# 添加RIFE节点（如果存在）
if RifeMappings:
    NODE_CLASS_MAPPINGS.update(RifeMappings)
    NODE_DISPLAY_NAME_MAPPINGS.update(RifeNames)

# 导出
__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']
