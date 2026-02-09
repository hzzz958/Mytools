"""
FFmpeg帧率转换节点
输出到ComfyUI标准output目录
"""

import os
import subprocess
import folder_paths
from datetime import datetime


class FFmpegFpsConverter:
    """FFmpeg视频帧率转换"""
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video_path": ("STRING", {"forceInput": True}),
                "fps": ("FLOAT", {
                    "default": 30.0, 
                    "min": 1.0, 
                    "max": 120.0
                }),
            },
            "optional": {
                "filename_prefix": ("STRING", {
                    "default": "ffmpeg_converted"
                }),
            },
        }
    
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("video_path",)
    FUNCTION = "convert_fps"
    CATEGORY = "MyTools/AudioVideo"
    OUTPUT_NODE = False
    
    def convert_fps(self, video_path, fps, filename_prefix="ffmpeg_converted"):
        """
        转换视频帧率
        
        Args:
            video_path: 输入视频路径
            fps: 目标帧率
            filename_prefix: 输出文件前缀
        
        Returns:
            输出视频路径
        """
        
        # 处理输入路径
        video_path = os.path.abspath(video_path.strip('"').strip("'"))
        
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"输入视频不存在: {video_path}")
        
        # 获取ComfyUI输出目录
        output_dir = folder_paths.get_output_directory()
        
        # 获取原文件扩展名
        _, ext = os.path.splitext(video_path)
        if not ext:
            ext = ".mp4"
        
        # 生成输出文件名
        # 格式: {filename_prefix}_{fps}fps_{timestamp}.{ext}
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"{filename_prefix}_{int(fps)}fps_{timestamp}{ext}"
        output_path = os.path.join(output_dir, output_filename)
        
        # FFmpeg命令
        cmd = [
            'ffmpeg',
            '-y',                                    # 覆盖输出文件
            '-i', video_path,                       # 输入文件
            '-vf', f'fps=fps={fps}:round=near',     # 帧率滤镜
            '-c:v', 'libx264',                      # 视频编码器
            '-crf', '18',                           # 质量参数
            '-c:a', 'copy',                         # 音频直接复制
            output_path                             # 输出文件
        ]
        
        try:
            print(f"[FFmpeg] 启动转换: {os.path.basename(video_path)}")
            print(f"[FFmpeg] 目标帧率: {fps} fps")
            print(f"[FFmpeg] 输出路径: {output_path}")
            
            # 运行FFmpeg
            result = subprocess.run(
                cmd, 
                check=True, 
                capture_output=True, 
                text=True
            )
            
            print(f"[FFmpeg] 转换成功! 输出: {output_filename}")
            
            return (output_path,)
        
        except subprocess.CalledProcessError as e:
            error_msg = f"FFmpeg错误: {e.stderr}"
            print(f"[FFmpeg] {error_msg}")
            raise Exception(f"FFmpeg转换失败: {e.stderr}")
        
        except FileNotFoundError:
            raise Exception("未找到FFmpeg程序，请确保已安装FFmpeg")


class FFmpegVideoInfo:
    """获取视频信息"""
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video_path": ("STRING", {"forceInput": True}),
            },
        }
    
    RETURN_TYPES = ("STRING", "INT", "INT", "FLOAT")
    RETURN_NAMES = ("info", "width", "height", "fps")
    FUNCTION = "get_info"
    CATEGORY = "MyTools/AudioVideo"
    
    def get_info(self, video_path):
        """获取视频信息"""
        
        video_path = os.path.abspath(video_path.strip('"').strip("'"))
        
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"视频不存在: {video_path}")
        
        try:
            # 使用ffprobe获取信息
            cmd = [
                'ffprobe',
                '-v', 'error',
                '-select_streams', 'v:0',
                '-show_entries', 'stream=width,height,r_frame_rate',
                '-of', 'csv=p=0',
                video_path
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )
            
            # 解析输出
            output = result.stdout.strip()
            parts = output.split(',')
            
            width = int(parts[0]) if len(parts) > 0 else 0
            height = int(parts[1]) if len(parts) > 1 else 0
            
            # 解析帧率 (format: num/den)
            fps = 30.0
            if len(parts) > 2:
                fps_str = parts[2].strip()
                if '/' in fps_str:
                    num, den = fps_str.split('/')
                    fps = float(num) / float(den)
                else:
                    fps = float(fps_str)
            
            info = f"分辨率: {width}x{height}, 帧率: {fps:.2f}fps"
            
            print(f"[FFmpegInfo] {info}")
            
            return (info, width, height, fps)
        
        except subprocess.CalledProcessError as e:
            raise Exception(f"获取视频信息失败: {e.stderr}")
        except FileNotFoundError:
            raise Exception("未找到ffprobe程序，请确保已安装FFmpeg")


# 节点注册
NODE_CLASS_MAPPINGS = {
    "FFmpegFpsConverter": FFmpegFpsConverter,
    "FFmpegVideoInfo": FFmpegVideoInfo,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FFmpegFpsConverter": "FFmpeg 帧率转换",
    "FFmpegVideoInfo": "FFmpeg 视频信息",
}
