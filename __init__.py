"""
自定义节点包初始化文件
支持多个节点模块
"""

from .ffmpeg_node import NODE_CLASS_MAPPINGS as FFmpegMappings
from .ffmpeg_node import NODE_DISPLAY_NAME_MAPPINGS as FFmpegNames
from .ffmpeg_concat_node import NODE_CLASS_MAPPINGS as ConcatMappings
from .ffmpeg_concat_node import NODE_DISPLAY_NAME_MAPPINGS as ConcatNames

# 合并所有节点
NODE_CLASS_MAPPINGS = {**FFmpegMappings, **RifeMappings, **ConcatMappings}
NODE_DISPLAY_NAME_MAPPINGS = {**FFmpegNames, **RifeNames, **ConcatNames}

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']
