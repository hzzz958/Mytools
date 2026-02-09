"""
自定义节点包初始化文件
"""

from .ffmpeg_node import NODE_CLASS_MAPPINGS as FFmpegMappings
from .ffmpeg_node import NODE_DISPLAY_NAME_MAPPINGS as FFmpegNames
from .rife_node import NODE_CLASS_MAPPINGS as RifeMappings
from .rife_node import NODE_DISPLAY_NAME_MAPPINGS as RifeNames

# 合并所有节点
NODE_CLASS_MAPPINGS = {**FFmpegMappings, **RifeMappings}
NODE_DISPLAY_NAME_MAPPINGS = {**FFmpegNames, **RifeNames}

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']
