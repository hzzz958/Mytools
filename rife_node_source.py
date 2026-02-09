"""
RIFE-NCNN-Vulkan ComfyUI 自定义节点
已优化：支持在无环境情况下进行工作流连线
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
# RIFE 配置 (这些路径主要用于远程服务器)
# ============================================================================
RIFE_ROOT = "/workspace/rife-ncnn-vulkan"
RIFE_BINARY = os.path.join(RIFE_ROOT, "rife-ncnn-vulkan")
MODELS_DIR = os.path.join(RIFE_ROOT, "models")

# ============================================================================
# 工具函数
# ============================================================================

def tensor_to_pil(tensor):
    if not PIL_AVAILABLE:
        raise ImportError("本地环境缺少 Pillow 或 PyTorch 库")
    
    if isinstance(tensor, torch.Tensor):
        tensor = tensor.cpu().numpy()
    
    if len(tensor.shape) == 4:
        tensor = tensor[0]
    
    if tensor.max() <= 1.0:
        tensor = (tensor * 255).astype(np.uint8)
    
    return Image.fromarray(tensor)

def pil_to_tensor(image):
    if image.mode != 'RGB':
        image = image.convert('RGB')
    arr = np.array(image).astype(np.float32) / 255.0
    return torch.from_numpy(arr).unsqueeze(0)

# ============================================================================
# 节点类
# ============================================================================

class RIFEInterpolate:
    """RIFE补帧节点 (支持占位连线)"""
    
    @classmethod
    def INPUT_TYPES(cls):
        # 预设模型列表，即使本地没有模型文件也能在 UI 选择
        available_models = ["rife-v4", "rife49", "rife414", "rife-v2", "rife-v3"]
        
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
                "gpu_id": ("INT", {"default": -2}),
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
        
        # --- 运行时环境检查 ---
        if not os.path.exists(RIFE_BINARY):
            error_msg = (
                f"\n[RIFE 节点错误] 未能找到 RIFE 执行文件：{RIFE_BINARY}\n"
                f"当前环境仅支持 UI 连线。若要运行，请确保在服务器上正确安装 rife-ncnn-vulkan。"
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        if not PIL_AVAILABLE:
            raise RuntimeError("Python 环境缺失必要的库 (torch/Pillow)")

        # --- 核心逻辑 ---
        logger.info(f"正在执行补帧: {model}")
        
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                img1_pil = tensor_to_pil(image1)
                img2_pil = tensor_to_pil(image2)
                
                img1_path = os.path.join(tmpdir, "input0.png")
                img2_path = os.path.join(tmpdir, "input1.png")
                output_path = os.path.join(tmpdir, "output.png")
                
                img1_pil.save(img1_path)
                img2_pil.save(img2_path)
                
                model_path = os.path.join(MODELS_DIR, model)
                
                cmd = [
                    RIFE_BINARY,
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
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                
                if result.returncode != 0:
                    raise RuntimeError(f"RIFE 执行失败: {result.stderr}")
                
                output_pil = Image.open(output_path)
                output_tensor = pil_to_tensor(output_pil)
                
                if save_output:
                    output_dir = folder_paths.get_output_directory()
                    save_path = os.path.join(output_dir, f"{filename_prefix}_{datetime.now().strftime('%H%M%S')}.png")
                    output_pil.save(save_path)
                
                return (output_tensor,)
            
            except Exception as e:
                logger.error(f"处理失败: {e}")
                raise

# ============================================================================
# 注册映射
# ============================================================================
NODE_CLASS_MAPPINGS = {
    "RIFEInterpolate": RIFEInterpolate,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "RIFEInterpolate": "RIFE 补帧 (云端预览版)",
}
