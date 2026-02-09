"""
RIFE-NCNN-Vulkan ComfyUI 自定义节点
已优化：即使本地环境缺失也能在 UI 界面连线
"""

import os
import subprocess
import tempfile
import logging
from datetime import datetime
from typing import Tuple

import numpy as np
import folder_paths

# 尝试导入，失败也不影响节点显示
try:
    from PIL import Image
    import torch
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

logger = logging.getLogger(__name__)

# ============================================================================
# RIFE配置 (在远程服务器生效)
# ============================================================================
RIFE_ROOT = "/workspace/rife-ncnn-vulkan"
RIFE_BINARY = os.path.join(RIFE_ROOT, "rife-ncnn-vulkan")
MODELS_DIR = os.path.join(RIFE_ROOT, "models")

# ============================================================================
# 工具函数 (增加空环境兼容)
# ============================================================================
def tensor_to_pil(tensor):
    if not PIL_AVAILABLE: raise ImportError("缺失必要库")
    if isinstance(tensor, torch.Tensor): tensor = tensor.cpu().numpy()
    if len(tensor.shape) == 4: tensor = tensor[0]
    if tensor.max() <= 1.0: tensor = (tensor * 255).astype(np.uint8)
    return Image.fromarray(tensor)

def pil_to_tensor(image):
    if image.mode != 'RGB': image = image.convert('RGB')
    arr = np.array(image).astype(np.float32) / 255.0
    return torch.from_numpy(arr).unsqueeze(0)

# ============================================================================
# RIFE补帧节点
# ============================================================================
class RIFEInterpolate:
    @classmethod
    def INPUT_TYPES(cls):
        # 注意：这里改成了写死的列表，不再扫描磁盘，所以本地不会报错
        available_models = ['rife-v4', 'rife49', 'rife414'] 
        return {
            "required": {
                "image1": ("IMAGE",),
                "image2": ("IMAGE",),
                "model": (available_models, {"default": "rife-v4"}),
                "num_frames": ("INT", {"default": 2, "min": 2, "max": 10}),
            },
            "optional": {
                "time_step": ("FLOAT", {"default": 0.5}),
                "enable_tta": ("BOOLEAN", {"default": False}),
                "gpu_id": ("INT", {"default": -2}),
                "filename_prefix": ("STRING", {"default": "rife_interpolated"}),
                "save_output": ("BOOLEAN", {"default": False}),
            }
        }
    
    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "interpolate"
    CATEGORY = "image/interpolation"
    
    def interpolate(self, image1, image2, model, num_frames, **kwargs):
        # 只有在运行点击时，才会检查路径是否存在
        if not os.path.exists(RIFE_BINARY):
            raise FileNotFoundError(f"本地环境中未找到 RIFE 执行程序: {RIFE_BINARY}。连线调试请忽略，运行请上服务器。")

        # ... (此处接你原来的 subprocess 执行逻辑)
        return (image1,) # 占位返回

NODE_CLASS_MAPPINGS = {"RIFEInterpolate": RIFEInterpolate}
NODE_DISPLAY_NAME_MAPPINGS = {"RIFEInterpolate": "RIFE 补帧 (占位模式)"}
