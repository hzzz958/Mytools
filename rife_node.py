"""
RIFE-NCNN-Vulkan ComfyUI 自定义节点
已优化：即使本地环境缺失也能在 UI 界面连线和搭建工作流
"""

import os
import subprocess
import tempfile
import logging
from datetime import datetime
from typing import Tuple

import numpy as np
import folder_paths

# 尝试导入必要库，如果本地环境没有，节点依然会显示，但运行会报错
try:
    from PIL import Image
    import torch
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

logger = logging.getLogger(__name__)

# ============================================================================
# RIFE 配置 (这些路径主要针对你的远程服务器环境)
# ============================================================================
RIFE_ROOT = "/workspace/rife-ncnn-vulkan"
RIFE_BINARY = os.path.join(RIFE_ROOT, "rife-ncnn-vulkan")
MODELS_DIR = os.path.join(RIFE_ROOT, "models")

# ============================================================================
# 工具函数
# ============================================================================

def tensor_to_pil(tensor) -> 'Image.Image':
    """PyTorch张量转PIL图片"""
    if not PIL_AVAILABLE:
        raise ImportError("缺失必要的 Python 库 (torch 或 Pillow)")
    
    if isinstance(tensor, torch.Tensor):
        tensor = tensor.cpu().numpy()
    
    # 处理 batch 维度
    if len(tensor.shape) == 4:
        tensor = tensor[0]
    
    if tensor.max() <= 1.0:
        tensor = (tensor * 255).astype(np.uint8)
    
    return Image.fromarray(tensor)

def pil_to_tensor(image: 'Image.Image') -> 'torch.Tensor':
    """PIL图片转PyTorch张量"""
    if image.mode != 'RGB':
        image = image.convert('RGB')
    
    arr = np.array(image).astype(np.float32) / 255.0
    return torch.from_numpy(arr).unsqueeze(0)

# ============================================================================
# RIFE 补帧节点类
# ============================================================================

class RIFEInterpolate:
    """RIFE补帧节点 - 支持在本地无环境状态下占位连线"""
    
    def __init__(self):
        self.rife_binary = RIFE_BINARY
        self.models_dir = MODELS_DIR
    
    @classmethod
    def INPUT_TYPES(cls):
        # 核心改动：使用静态列表，防止在本地因为找不到文件夹而导致加载失败
        available_models = ['rife-v4', 'rife49', 'rife414', 'rife-v2', 'rife-v3']
        
        return {
            "required": {
                "image1": ("IMAGE",),
                "image2": ("IMAGE",),
                "model": (available_models, {"default": "rife-v4"}),
                "num_frames": ("INT", {"default": 2, "min": 2, "max": 10, "step": 1}),
            },
            "optional": {
                "time_step": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01}),
                "enable_tta": ("BOOLEAN", {"default": False}),
                "gpu_id": ("INT", {"default": -2, "min": -2, "max": 4, "step": 1}),
                "filename_prefix": ("STRING", {"default": "rife_interpolated"}),
                "save_output": ("BOOLEAN", {"default": False}),
            }
        }
    
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("IMAGE",)
    FUNCTION = "interpolate"
    CATEGORY = "image/interpolation"
    
    def interpolate(self, image1, image2, model: str, num_frames: int, 
                   time_step: float = 0.5, enable_tta: bool = False, 
                   gpu_id: int = -2, filename_prefix: str = "rife_interpolated",
                   save_output: bool = False) -> Tuple:
        """执行补帧逻辑"""
        
        # 1. 运行时环境检查：只有运行到这一步才会报错
        if not os.path.exists(self.rife_binary):
            error_msg = f"运行时错误：在路径 {self.rife_binary} 未找到 RIFE 执行程序。本地连线调试请忽略，运行请在配置好环境的服务器上执行。"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)

        if not PIL_AVAILABLE:
            raise RuntimeError("Python 环境缺失必要的库 (torch/Pillow)")
        
        logger.info(f"开始补帧: 模型={model}, 帧数={num_frames}")
        
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                img1_pil = tensor_to_pil(image1)
                img2_pil = tensor_to_pil(image2)
                
                img1_path = os.path.join(tmpdir, "input0.png")
                img2_path = os.path.join(tmpdir, "input1.png")
                output_path = os.path.join(tmpdir, "output.png")
                
                img1_pil.save(img1_path)
                img2_pil.save(img2_path)
                
                model_path = os.path.join(self.models_dir, model)
                
                # 构建命令行参数
                cmd = [
                    self.rife_binary,
                    "-m", model_path,
                    "-0", img1_path,
                    "-1", img2_path,
                    "-o", output_path,
                    "-n", str(num_frames),
                    "-s", str(time_step),
                ]
                
                if gpu_id >= -1:
                    cmd.extend(["-g", str(gpu_id)])
                if enable_tta:
                    cmd.extend(["-x", "-z"])
                
                # 运行 RIFE
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                
                if result.returncode != 0:
                    raise RuntimeError(f"RIFE 执行失败: {result.stderr}")
                
                if not os.path.exists(output_path):
                    raise FileNotFoundError(f"输出文件未生成: {output_path}")
                
                output_pil = Image.open(output_path)
                output_tensor = pil_to_tensor(output_pil)
                
                if save_output:
                    output_dir = folder_paths.get_output_directory()
                    timestamp = datetime.now().strftime("%H%M%S")
                    save_path = os.path.join(output_dir, f"{filename_prefix}_{timestamp}.png")
                    output_pil.save(save_path)
                
                return (output_tensor,)
            
            except Exception as e:
                logger.error(f"补帧处理失败: {e}")
                raise

# ============================================================================
# 节点注册
# ============================================================================

NODE_CLASS_MAPPINGS = {
    "RIFEInterpolate": RIFEInterpolate,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "RIFEInterpolate": "RIFE 补帧 (云端预览/占位)",
}
