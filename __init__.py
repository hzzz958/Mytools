"""
自定义节点包初始化文件
支持多个节点模块
"""

# 导入所有节点模块
from .ffmpeg_node import NODE_CLASS_MAPPINGS as FFmpegMappings
from .ffmpeg_node import NODE_DISPLAY_NAME_MAPPINGS as FFmpegNames

# 导入 RIFE 节点（强制导入，不再使用 try-except，方便你在控制台看到路径报错）
from .rife_node import NODE_CLASS_MAPPINGS as RifeMappings
from .rife_node import NODE_DISPLAY_NAME_MAPPINGS as RifeNames

# 合并所有节点
NODE_CLASS_MAPPINGS = {**FFmpegMappings, **RifeMappings}
NODE_DISPLAY_NAME_MAPPINGS = {**FFmpegNames, **RifeNames}

# 导出
__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']
