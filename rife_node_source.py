"""
RIFE-NCNN-Vulkan ComfyUI 自定义节点 - 完整源码
图像补帧功能
"""

import os
import subprocess
import tempfile
import logging
from datetime import datetime
from typing import Tuple, Optional

import numpy as np
import folder_paths

try:
    from PIL import Image
    import torch
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# 日志配置
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ============================================================================
# RIFE配置
# ============================================================================

RIFE_ROOT = "/workspace/rife-ncnn-vulkan"
RIFE_BINARY = os.path.join(RIFE_ROOT, "rife-ncnn-vulkan")
MODELS_DIR = os.path.join(RIFE_ROOT, "models")


# ============================================================================
# 工具函数
# ============================================================================

def tensor_to_pil(tensor) -> Optional['Image.Image']:
    """PyTorch张量转PIL图片"""
    if not PIL_AVAILABLE:
        raise ImportError("需要安装PIL库")
    
    if isinstance(tensor, torch.Tensor):
        tensor = tensor.cpu().numpy()
    
    # 处理batch维度
    if len(tensor.shape) == 4:
        tensor = tensor[0]
    
    if tensor.max() > 1.0:
        tensor = tensor / 255.0
    
    tensor = (tensor * 255).astype(np.uint8)
    
    if len(tensor.shape) == 3 and tensor.shape[2] == 3:
        return Image.fromarray(tensor, mode='RGB')
    elif len(tensor.shape) == 3 and tensor.shape[2] == 4:
        return Image.fromarray(tensor, mode='RGBA')
    else:
        return Image.fromarray(tensor[:, :, 0], mode='L')


def pil_to_tensor(image: 'Image.Image') -> 'torch.Tensor':
    """PIL图片转PyTorch张量"""
    if not PIL_AVAILABLE:
        raise ImportError("需要安装PIL库")
    
    if image.mode != 'RGB':
        image = image.convert('RGB')
    
    arr = np.array(image).astype(np.float32)
    
    if arr.max() > 1.0:
        arr = arr / 255.0
    
    tensor = torch.from_numpy(arr).unsqueeze(0)
    return tensor


def get_available_models() -> list:
    """获取可用的RIFE模型列表"""
    models = []
    
    if os.path.exists(MODELS_DIR):
        for model_name in os.listdir(MODELS_DIR):
            model_path = os.path.join(MODELS_DIR, model_name)
            if os.path.isdir(model_path):
                has_param = any(f.endswith('.param') for f in os.listdir(model_path))
                has_bin = any(f.endswith('.bin') for f in os.listdir(model_path))
                if has_param and has_bin:
                    models.append(model_name)
    
    return models if models else ['rife-v4', 'rife49', 'rife414']


# ============================================================================
# RIFE补帧节点
# ============================================================================

class RIFEInterpolate:
    """RIFE补帧节点 - 输入两张图片输出补帧后的图片"""
    
    def __init__(self):
        self.rife_binary = RIFE_BINARY
        self.models_dir = MODELS_DIR
    
    @classmethod
    def INPUT_TYPES(cls):
        available_models = get_available_models()
        return {
            "required": {
                "image1": ("IMAGE",),
                "image2": ("IMAGE",),
                "model": (available_models, {"default": available_models[0] if available_models else "rife-v4"}),
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
        """执行补帧"""
        
        if not PIL_AVAILABLE:
            raise ImportError("RIFE节点需要PIL和torch库")
        
        logger.info(f"开始补帧: 模型={model}, 帧数={num_frames}")
        
        if not os.path.exists(self.rife_binary):
            raise FileNotFoundError(f"RIFE可执行文件不存在: {self.rife_binary}")
        
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
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                
                if result.returncode != 0:
                    raise RuntimeError(f"RIFE执行失败: {result.stderr}")
                
                if not os.path.exists(output_path):
                    raise FileNotFoundError(f"输出文件未生成: {output_path}")
                
                output_pil = Image.open(output_path)
                output_tensor = pil_to_tensor(output_pil)
                
                if save_output:
                    output_dir = folder_paths.get_output_directory()
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    save_filename = f"{filename_prefix}_{timestamp}.png"
                    save_path = os.path.join(output_dir, save_filename)
                    output_pil.save(save_path)
                    logger.info(f"输出已保存: {save_filename}")
                
                logger.info(f"补帧完成，输出形状: {output_tensor.shape}")
                return (output_tensor,)
            
            except Exception as e:
                logger.error(f"补帧失败: {e}")
                raise


# ============================================================================
# 节点注册
# ============================================================================

NODE_CLASS_MAPPINGS = {
    "RIFEInterpolate": RIFEInterpolate,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "RIFEInterpolate": "RIFE 补帧",
}
