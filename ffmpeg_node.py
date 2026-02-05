import os
import subprocess
import folder_paths

class FFmpegFpsConverter:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "video_path": ("STRING", {"forceInput": True}),
                "fps": ("FLOAT", {"default": 30.0, "min": 1.0, "max": 120.0}),
            },
        }

    RETURN_TYPES = ("STRING",)
    FUNCTION = "convert_fps"
    CATEGORY = "MyTools/AudioVideo"

    def convert_fps(self, video_path, fps):
        # 处理路径问题，确保支持各种格式
        video_path = os.path.abspath(video_path.strip('"'))
        base, ext = os.path.splitext(video_path)
        output_path = f"{base}_{int(fps)}fps{ext}"
        
        # 你的神级命令：32转30，口型对齐
        cmd = [
            'ffmpeg', '-y', '-i', video_path,
            '-vf', f'fps=fps={fps}:round=near',
            '-c:v', 'libx264', '-crf', '18',
            '-c:a', 'copy', output_path
        ]
        
        try:
            print(f"--- 启动 FFmpeg 转换: {video_path} ---")
            # 使用 subprocess.run 运行，不弹黑框，但在后台日志可见
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            print(f"--- 转换成功: {output_path} ---")
            return (output_path,)
        except subprocess.CalledProcessError as e:
            print(f"FFmpeg 错误日志: {e.stderr}")
            raise Exception(f"FFmpeg 转换失败，请检查是否安装 FFmpeg 环境。")

NODE_CLASS_MAPPINGS = {"FFmpegFpsConverter": FFmpegFpsConverter}
NODE_DISPLAY_NAME_MAPPINGS = {"FFmpegFpsConverter": "FFmpeg精准帧率转换(30fps)"}