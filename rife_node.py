"""
Practical-RIFE ComfyUI 自定义节点
使用 Practical-RIFE 进行视频插帧
https://github.com/hzwer/Practical-RIFE/

安装位置: /workspace/Practical-RIFE/inference_video.py
"""

import os
import subprocess
import tempfile
from datetime import datetime
from typing import Tuple, Optional
from pathlib import Path

import numpy as np
import folder_paths

try:
    from PIL import Image
    import torch
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

PRACTICAL_RIFE_ROOT = "/workspace/Practical-RIFE"
INFERENCE_SCRIPT = os.path.join(PRACTICAL_RIFE_ROOT, "inference_video.py")


def tensor_to_pil(tensor) -> Optional['Image.Image']:
    """PyTorch张量转PIL图片"""
    if not PIL_AVAILABLE:
        return None
    
    if isinstance(tensor, torch.Tensor):
        tensor = tensor.cpu().numpy()
    
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
        return None
    
    if image.mode != 'RGB':
        image = image.convert('RGB')
    
    arr = np.array(image).astype(np.float32)
    
    if arr.max() > 1.0:
        arr = arr / 255.0
    
    tensor = torch.from_numpy(arr).unsqueeze(0)
    return tensor


class PracticalRIFEInterpolate:
    """Practical-RIFE 两帧补帧"""
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image1": ("IMAGE",),
                "image2": ("IMAGE",),
                "multi": ("INT", {
                    "default": 2,
                    "min": 2,
                    "max": 8,
                    "step": 1,
                    "description": "插帧倍数: 2=补1帧, 3=补2帧"
                }),
            },
        }
    
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("IMAGE",)
    FUNCTION = "interpolate"
    CATEGORY = "video/frame-interpolation"
    
    def interpolate(self, image1, image2, multi: int) -> Tuple:
        """两帧之间的补帧"""
        
        print(f"\n[Practical-RIFE] ========== 两帧补帧 ==========")
        print(f"[Practical-RIFE] 插帧倍数: {multi}x")
        
        # 环境检查
        if not PIL_AVAILABLE:
            raise Exception("缺少Python库: pip install Pillow torch")
        
        if not os.path.exists(INFERENCE_SCRIPT):
            raise FileNotFoundError(f"Practical-RIFE脚本不存在: {INFERENCE_SCRIPT}")
        
        print(f"[Practical-RIFE] ✓ 环境检查通过")
        
        # 执行补帧
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                # 转换为PIL并保存
                img1_pil = tensor_to_pil(image1)
                img2_pil = tensor_to_pil(image2)
                
                if img1_pil is None or img2_pil is None:
                    raise Exception("图片转换失败")
                
                # 保存为视频的帧
                img1_path = os.path.join(tmpdir, "frame_0000.png")
                img2_path = os.path.join(tmpdir, "frame_0001.png")
                
                img1_pil.save(img1_path)
                img2_pil.save(img2_path)
                
                # 创建输出目录
                output_dir = os.path.join(tmpdir, "output")
                os.makedirs(output_dir, exist_ok=True)
                
                # 使用ffmpeg创建临时视频
                video_path = os.path.join(tmpdir, "input_video.mp4")
                
                cmd_create_video = [
                    'ffmpeg', '-y',
                    '-framerate', '30',
                    '-i', os.path.join(tmpdir, 'frame_%04d.png'),
                    '-c:v', 'libx264',
                    '-pix_fmt', 'yuv420p',
                    video_path
                ]
                
                print(f"[Practical-RIFE] 创建临时视频...")
                result = subprocess.run(cmd_create_video, capture_output=True, text=True)
                
                if result.returncode != 0:
                    raise RuntimeError(f"视频创建失败: {result.stderr}")
                
                # 调用Practical-RIFE进行插帧
                # 注意: Practical-RIFE不支持 --gpu_id 参数
                cmd_inference = f"python3 {INFERENCE_SCRIPT} --video={video_path} --multi={multi} --model=/workspace/Practical-RIFE/train_log --scale=1.0"
                
                print(f"[Practical-RIFE] 执行插帧...")
                print(f"[Practical-RIFE] 命令: {cmd_inference}")
                
                result = subprocess.run(cmd_inference, shell=True, capture_output=True, text=True)
                
                if result.returncode != 0:
                    print(f"[Practical-RIFE] stderr: {result.stderr}")
                    print(f"[Practical-RIFE] stdout: {result.stdout}")
                    raise RuntimeError(f"插帧失败")
                
                print(f"[Practical-RIFE] ✓ 补帧完成！\n")
                
                # 读取输出文件
                output_video = os.path.join(output_dir, os.path.basename(video_path))
                
                if not os.path.exists(output_video):
                    # Practical-RIFE可能改变输出名称或位置，尝试查找
                    video_files = list(Path(output_dir).glob("*.mp4"))
                    if not video_files:
                        video_files = list(Path(tmpdir).glob("**/*.mp4"))
                    
                    if video_files:
                        output_video = str(video_files[-1])  # 取最新的
                    else:
                        raise FileNotFoundError("输出视频未生成")
                
                # 使用ffmpeg提取第一帧
                output_frame = os.path.join(tmpdir, "output_frame.png")
                cmd_extract = [
                    'ffmpeg', '-y',
                    '-i', output_video,
                    '-frames:v', '1',
                    output_frame
                ]
                
                result = subprocess.run(cmd_extract, capture_output=True, text=True)
                
                if not os.path.exists(output_frame):
                    raise FileNotFoundError("无法提取输出帧")
                
                output_pil = Image.open(output_frame)
                output_tensor = pil_to_tensor(output_pil)
                
                return (output_tensor,)
            
            except Exception as e:
                raise Exception(f"补帧失败: {str(e)}")


class PracticalRIFEVFI:
    """Practical-RIFE 视频插帧（推荐方式）
    
    直接用Practical-RIFE的inference_video.py处理视频
    输入帧序列，输出插帧后的帧序列
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),  # 帧序列
                "multi": ("INT", {
                    "default": 2,
                    "min": 2,
                    "max": 8,
                    "step": 1,
                    "description": "插帧倍数: 2=30fps->60fps, 3=30fps->90fps"
                }),
            },
            "optional": {
                "filename_prefix": ("STRING", {
                    "default": "rife_video"
                }),
                "save_output": ("BOOLEAN", {
                    "default": False,
                    "description": "保存到ComfyUI output目录"
                }),
            }
        }
    
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("IMAGE",)
    FUNCTION = "interpolate_video"
    CATEGORY = "video/frame-interpolation"
    
    def interpolate_video(self, images, multi: int,
                         filename_prefix: str = "rife_video",
                         save_output: bool = False) -> Tuple:
        """
        使用Practical-RIFE进行视频插帧
        
        输入: 帧序列
        输出: 插帧后的帧序列
        """
        
        num_frames = images.shape[0]
        print(f"\n[Practical-RIFE VFI] ========== 视频插帧处理 ==========")
        print(f"[Practical-RIFE VFI] 输入帧数: {num_frames}")
        print(f"[Practical-RIFE VFI] 插帧倍数: {multi}x")
        print(f"[Practical-RIFE VFI] 预期输出帧数: 约{num_frames * multi}")
        
        # 环境检查
        if not PIL_AVAILABLE:
            raise Exception("缺少Python库: pip install Pillow torch")
        
        if not os.path.exists(INFERENCE_SCRIPT):
            raise FileNotFoundError(f"Practical-RIFE脚本不存在: {INFERENCE_SCRIPT}")
        
        print(f"[Practical-RIFE VFI] ✓ 环境检查通过")
        
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                # 保存帧为PNG序列
                print(f"[Practical-RIFE VFI] 保存帧序列...")
                for i, frame in enumerate(images):
                    pil_frame = tensor_to_pil(frame)
                    if pil_frame is None:
                        raise Exception(f"帧{i}转换失败")
                    
                    frame_path = os.path.join(tmpdir, f"frame_{i:04d}.png")
                    pil_frame.save(frame_path)
                
                # 创建输出目录
                output_base_dir = os.path.join(tmpdir, "output")
                os.makedirs(output_base_dir, exist_ok=True)
                
                # 使用ffmpeg创建视频
                print(f"[Practical-RIFE VFI] 创建输入视频...")
                video_path = os.path.join(tmpdir, "input_video.mp4")
                
                cmd_create_video = [
                    'ffmpeg', '-y', '-loglevel', 'error',
                    '-framerate', '30',
                    '-i', os.path.join(tmpdir, 'frame_%04d.png'),
                    '-c:v', 'libx264',
                    '-pix_fmt', 'yuv420p',
                    video_path
                ]
                
                result = subprocess.run(cmd_create_video, capture_output=True, text=True)
                
                if result.returncode != 0:
                    raise RuntimeError(f"视频创建失败: {result.stderr}")
                
                # 调用Practical-RIFE
                # 重要: Practical-RIFE会在当前工作目录或指定的输出目录创建结果
                print(f"[Practical-RIFE VFI] 执行插帧处理...")
                
                # 使用output参数指定输出目录
                cmd_inference = f"python3 {INFERENCE_SCRIPT} --video={video_path} --multi={multi} --model=/workspace/Practical-RIFE/train_log --scale=1.0 --output={output_base_dir}"
                
                print(f"[Practical-RIFE VFI] 命令: {cmd_inference}")
                
                result = subprocess.run(cmd_inference, shell=True, capture_output=True, text=True, cwd=tmpdir)
                
                print(f"[Practical-RIFE VFI] stdout: {result.stdout}")
                if result.stderr:
                    print(f"[Practical-RIFE VFI] stderr: {result.stderr}")
                
                if result.returncode != 0:
                    raise RuntimeError("插帧失败")
                
                print(f"[Practical-RIFE VFI] ✓ 插帧完成!")
                
                # 查找输出视频（Practical-RIFE会生成新视频）
                # 尝试多个可能的位置
                possible_dirs = [
                    output_base_dir,
                    os.path.join(output_base_dir, "results"),
                    tmpdir,
                ]
                
                output_video = None
                for search_dir in possible_dirs:
                    if os.path.exists(search_dir):
                        print(f"[Practical-RIFE VFI] 搜索目录: {search_dir}")
                        video_files = list(Path(search_dir).glob("*.mp4"))
                        if video_files:
                            # 找最新修改的文件（应该是输出视频）
                            output_video = max(video_files, key=lambda p: p.stat().st_mtime)
                            output_video = str(output_video)
                            print(f"[Practical-RIFE VFI] 找到输出视频: {output_video}")
                            break
                
                if not output_video:
                    raise FileNotFoundError("未找到输出视频")
                
                # 使用ffmpeg提取所有帧
                print(f"[Practical-RIFE VFI] 提取输出帧...")
                output_frames_dir = os.path.join(tmpdir, "output_frames")
                os.makedirs(output_frames_dir, exist_ok=True)
                
                cmd_extract = [
                    'ffmpeg', '-y', '-loglevel', 'error',
                    '-i', output_video,
                    os.path.join(output_frames_dir, 'frame_%04d.png')
                ]
                
                result = subprocess.run(cmd_extract, capture_output=True, text=True)
                
                if result.returncode != 0:
                    raise RuntimeError(f"提取帧失败: {result.stderr}")
                
                # 读取输出帧
                output_frames = []
                frame_files = sorted(Path(output_frames_dir).glob("*.png"))
                
                print(f"[Practical-RIFE VFI] 找到 {len(frame_files)} 个输出帧")
                
                for frame_file in frame_files:
                    frame_pil = Image.open(frame_file)
                    frame_tensor = pil_to_tensor(frame_pil)
                    output_frames.append(frame_tensor)
                
                if not output_frames:
                    raise Exception("没有输出帧")
                
                # 合并帧
                output_tensor = torch.cat(output_frames, dim=0)
                
                print(f"[Practical-RIFE VFI] ✓ 完成！")
                print(f"[Practical-RIFE VFI] 输入帧数: {num_frames}")
                print(f"[Practical-RIFE VFI] 输出帧数: {output_tensor.shape[0]}")
                print(f"[Practical-RIFE VFI] 倍数验证: {output_tensor.shape[0] / num_frames:.2f}x")
                
                # 保存到输出目录
                if save_output:
                    output_dir = folder_paths.get_output_directory()
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    for idx, frame in enumerate(output_frames):
                        save_filename = f"{filename_prefix}_{timestamp}_{idx:04d}.png"
                        save_path = os.path.join(output_dir, save_filename)
                        frame_pil = tensor_to_pil(frame)
                        frame_pil.save(save_path)
                    print(f"[Practical-RIFE VFI] ✓ 已保存到输出目录")
                
                print(f"[Practical-RIFE VFI] ==========================================\n")
                
                return (output_tensor,)
            
            except Exception as e:
                raise Exception(f"视频插帧失败: {str(e)}")


NODE_CLASS_MAPPINGS = {
    "PracticalRIFEInterpolate": PracticalRIFEInterpolate,
    "PracticalRIFEVFI": PracticalRIFEVFI,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "PracticalRIFEInterpolate": "Practical-RIFE 两帧补帧",
    "PracticalRIFEVFI": "Practical-RIFE 视频插帧",
}
