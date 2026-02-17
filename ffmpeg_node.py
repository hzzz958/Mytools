"""
FFmpeg 视频处理节点套件
功能：帧率转换、视频信息获取、分辨率调整
增强：实时进度反馈、保存和预览选项、详细提示注释
修改：FFmpegFpsConverter 返回 VHS_FILENAMES 类型，使其输出被 ComfyUI 队列识别为主要视频文件
       这样队列/资产列表会优先显示转换后的 30fps 文件，而不是上游的 vc32 文件
"""
import os
import subprocess
import json
import shutil
import re
from datetime import datetime
from pathlib import Path
import folder_paths

# ============================================================================
# 进度日志管理类
# ============================================================================
class ProgressLogger:
    """
    进度记录和日志管理类
   
    功能：
    - 统一管理日志输出
    - 自动计时
    - 结构化日志格式
    """
   
    def __init__(self, task_name):
        """初始化日志记录器"""
        self.task_name = task_name
        self.log_lines = []
        self.start_time = datetime.now()
       
        # 添加开始信息
        self.add_log(f"{'='*70}")
        self.add_log(f"{task_name} - 开始执行")
        self.add_log(f"执行时间: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.add_log(f"{'='*70}")
   
    def add_log(self, message):
        """添加日志行，同时打印到控制台"""
        self.log_lines.append(message)
        print(message)
   
    def add_section(self, title):
        """添加分节标题（用于区分不同的处理阶段）"""
        self.add_log("")
        self.add_log(f"[{title}]")
        self.add_log("-" * 70)
   
    def add_info(self, key, value):
        """添加信息对（键值对形式）"""
        self.add_log(f" {key}: {value}")
   
    def add_success(self, message):
        """添加成功信息（带 ✓ 符号）"""
        self.add_log(f" ✓ {message}")
   
    def add_error(self, message):
        """添加错误信息（带 ✗ 符号）"""
        self.add_log(f" ✗ {message}")
   
    def get_elapsed_time(self):
        """获取从开始到现在的已用时间"""
        elapsed = datetime.now() - self.start_time
        seconds = int(elapsed.total_seconds())
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes}m {secs}s"
   
    def finish(self):
        """完成任务，生成完整日志"""
        self.add_log("")
        self.add_log(f"{'='*70}")
        self.add_log(f"✓ 任务完成！用时: {self.get_elapsed_time()}")
        self.add_log(f"{'='*70}")
        return "\n".join(self.log_lines)

# ============================================================================
# FFmpeg 工具函数集合
# ============================================================================
class FFmpegUtils:
    """
    FFmpeg 工具函数集合
   
    提供：
    - FFmpeg/ffprobe 安装检查
    - 文件验证
    - 视频信息提取
    - 文件大小估算
    - 磁盘空间检查
    """
   
    @staticmethod
    def check_ffmpeg_installed(logger=None):
        """
        检查 FFmpeg 是否已安装
       
        参数:
            logger: ProgressLogger 实例（可选）
       
        返回:
            bool: True 表示已安装，False 表示未安装
        """
        try:
            subprocess.run(
                ['ffmpeg', '-version'],
                capture_output=True,
                timeout=5
            )
            if logger:
                logger.add_success("FFmpeg 已安装")
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            if logger:
                logger.add_error("FFmpeg 未找到或不在 PATH 中")
            return False
   
    @staticmethod
    def check_ffprobe_installed(logger=None):
        """
        检查 ffprobe 是否已安装
       
        参数:
            logger: ProgressLogger 实例（可选）
       
        返回:
            bool: True 表示已安装，False 表示未安装
        """
        try:
            subprocess.run(
                ['ffprobe', '-version'],
                capture_output=True,
                timeout=5
            )
            if logger:
                logger.add_success("ffprobe 已安装")
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            if logger:
                logger.add_error("ffprobe 未找到或不在 PATH 中")
            return False
   
    @staticmethod
    def validate_input_file(file_path, logger=None):
        """
        验证输入文件是否有效
       
        检查项:
        - 文件是否存在
        - 是否是文件（不是目录）
        - 是否有读取权限
       
        参数:
            file_path: 文件路径
            logger: ProgressLogger 实例（可选）
       
        返回:
            str: 规范化的文件路径
       
        异常:
            FileNotFoundError: 文件不存在
            IsADirectoryError: 路径是目录而不是文件
            PermissionError: 无读取权限
        """
        file_path = os.path.abspath(file_path.strip('"').strip("'"))
       
        if not os.path.exists(file_path):
            if logger:
                logger.add_error(f"文件不存在: {file_path}")
            raise FileNotFoundError(f"文件不存在: {file_path}")
       
        if not os.path.isfile(file_path):
            if logger:
                logger.add_error(f"这是一个目录，不是文件: {file_path}")
            raise IsADirectoryError(f"这是一个目录: {file_path}")
       
        if not os.access(file_path, os.R_OK):
            if logger:
                logger.add_error(f"无读取权限: {file_path}")
            raise PermissionError(f"无读取权限: {file_path}")
       
        # 获取文件大小并记录
        file_size_mb = os.path.getsize(file_path) / 1024 / 1024
        if logger:
            logger.add_success(f"文件有效 ({file_size_mb:.2f}MB)")
       
        return file_path
   
    @staticmethod
    def parse_ffmpeg_output(output_text):
        """
        解析 FFmpeg 输出，提取进度信息
       
        FFmpeg 的 stderr 输出包含如下形式的进度信息：
        frame= 1500 fps= 45 q= 23.0 Lsize=N/A time=00:01:00.00 bitrate=5000k speed=2.5x
       
        参数:
            output_text: FFmpeg 输出的一行文本
       
        返回:
            dict: {
                'frame': int, # 已处理帧数
                'fps': float, # 当前处理速度（FPS）
                'time': str, # 已处理视频时长
                'bitrate': str, # 当前比特率
                'speed': float # 相对处理速度（X 倍）
            }
        """
        info = {}
       
        # 提取帧数: frame=1500
        frame_match = re.search(r'frame=\s*(\d+)', output_text)
        if frame_match:
            info['frame'] = int(frame_match.group(1))
       
        # 提取 FPS: fps=45
        fps_match = re.search(r'fps=\s*([\d.]+)', output_text)
        if fps_match:
            info['fps'] = float(fps_match.group(1))
       
        # 提取处理时间: time=00:01:00.00
        time_match = re.search(r'time=(\d{2}):(\d{2}):(\d{2}\.\d{2})', output_text)
        if time_match:
            h, m, s = time_match.groups()
            info['time'] = f"{h}:{m}:{s}"
       
        # 提取比特率: bitrate=5000k
        bitrate_match = re.search(r'bitrate=\s*([\d.]+\w+)', output_text)
        if bitrate_match:
            info['bitrate'] = bitrate_match.group(1)
       
        # 提取速度: speed=2.5x
        speed_match = re.search(r'speed=\s*([\d.]+)x', output_text)
        if speed_match:
            info['speed'] = float(speed_match.group(1))
       
        return info
   
    @staticmethod
    def estimate_output_size(duration, quality='medium'):
        """
        估算输出文件大小
       
        基于视频时长和质量等级估算输出文件大小
       
        参数:
            duration: 视频时长（秒）
            quality: 质量等级 ('low', 'medium', 'high')
       
        返回:
            float: 估算的文件大小（MB）
        """
        # 不同质量级别对应的比特率
        bitrate_map = {
            'low': 2000, # 2 Mbps - 快速，文件小
            'medium': 5000, # 5 Mbps - 平衡
            'high': 10000, # 10 Mbps - 高质量，文件大
        }
        bitrate = bitrate_map.get(quality, 5000)
        # 公式：(比特率 Mbps × 时长 s) / 8 / 1024 = 文件大小 MB
        estimated_size = (bitrate * duration) / 8 / 1024 / 1024
        return estimated_size
   
    @staticmethod
    def check_disk_space(output_path, required_mb):
        """
        检查输出路径所在磁盘是否有足够空间
       
        参数:
            output_path: 输出文件路径
            required_mb: 需要的空间（MB）
       
        返回:
            tuple: (是否有足够空间, 可用空间MB)
        """
        try:
            stat = shutil.disk_usage(os.path.dirname(output_path))
            free_mb = stat.free / 1024 / 1024
            return (free_mb > required_mb, free_mb)
        except Exception as e:
            print(f"[Warning] 无法检查磁盘空间: {e}")
            return (True, None) # 默认认为空间充足

# ============================================================================
# 节点 1: FFmpeg 帧率转换（改进版 - 支持 VHS_FILENAMES 输出）
# ============================================================================
class FFmpegFpsConverter:
    """
    FFmpeg 视频帧率转换节点
   
    功能:
    - 将视频转换到指定帧率（1-120 fps）
    - 支持多种编码器和质量级别
    - 实时显示处理进度
    - 可选保存输出和预览信息
   
    修改:
    - 返回 VHS_FILENAMES 类型，让 ComfyUI 队列/资产列表优先显示转换后的 30fps 文件
    - filename_prefix 默认改为 "vc30"（可自行调整）
    """
   
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video_path": ("STRING", {
                    "forceInput": True,
                    "tooltip": "输入视频文件的完整路径"
                }),
                "fps": ("FLOAT", {
                    "default": 30.0,
                    "min": 1.0,
                    "max": 120.0,
                    "step": 0.1,
                    "tooltip": "目标帧率（1-120 fps）\n推荐值：24(电影), 30(标准), 60(高帧率)"
                }),
            },
            "optional": {
                "filename_prefix": ("STRING", {
                    "default": "vc30",  # 修改默认前缀，便于识别为最终文件
                    "tooltip": "输出文件的前缀，完整名称会包含帧率和时间戳"
                }),
                "quality": (["low", "medium", "high"], {
                    "default": "medium",
                    "tooltip": "输出质量\nlow: 快速, 小文件 (2Mbps)\nmedium: 平衡 (5Mbps)\nhigh: 高质量, 大文件 (10Mbps)"
                }),
                "codec": (["libx264", "libx265"], {
                    "default": "libx264",
                    "tooltip": "视频编码器\nlibx264: H.264 (兼容性好，更快)\nlibx265: H.265 (压缩率高，更慢)"
                }),
                "save_output": (["yes", "no"], {
                    "default": "yes",
                    "tooltip": "是否保存输出视频\nyes: 保存到输出目录\nno: 只预览信息，不保存"
                }),
                "preview_info": (["yes", "no"], {
                    "default": "yes",
                    "tooltip": "是否显示详细的预览信息和进度反馈\nyes: 显示完整日志\nno: 只显示基本信息"
                }),
            },
        }
   
    # 修改关键：返回 VHS_FILENAMES 类型，让队列显示这个文件
    RETURN_TYPES = ("VHS_FILENAMES", "STRING", "STRING")
    RETURN_NAMES = ("Filenames", "summary", "detailed_log")
    FUNCTION = "convert_fps"
    CATEGORY = "MyTools/AudioVideo"
    OUTPUT_NODE = True  # 标记为输出节点，队列更优先
   
    def convert_fps(self, video_path, fps, filename_prefix="vc30",
                   quality="medium", codec="libx264",
                   save_output="yes", preview_info="yes"):
        """
        执行帧率转换
       
        处理流程：
        1. 环境检查 - 验证 FFmpeg 是否可用
        2. 文件验证 - 检查输入文件是否有效
        3. 视频分析 - 获取原始视频信息
        4. 参数计算 - 计算输出参数和文件大小
        5. 空间检查 - 确保磁盘有足够空间
        6. 执行转换 - 运行 FFmpeg，实时显示进度
        7. 验证输出 - 检查输出文件是否生成
        8. 生成报告 - 输出处理总结和详细日志
       
        返回:
            (VHS_FILENAMES, 简要总结, 详细日志) - VHS_FILENAMES 让 ComfyUI 优先显示转换后的文件
        """
       
        logger = ProgressLogger("FFmpeg 帧率转换")
       
        try:
            # ========== 步骤 1: 环境检查 ==========
            if preview_info == "yes":
                logger.add_section("1. 环境检查")
               
                if not FFmpegUtils.check_ffmpeg_installed(logger):
                    raise Exception("FFmpeg 未安装或不在 PATH 中")
            else:
                if not FFmpegUtils.check_ffmpeg_installed():
                    raise Exception("FFmpeg 未安装或不在 PATH 中")
           
            # ========== 步骤 2: 验证输入文件 ==========
            if preview_info == "yes":
                logger.add_section("2. 验证输入文件")
                video_path = FFmpegUtils.validate_input_file(video_path, logger)
            else:
                video_path = FFmpegUtils.validate_input_file(video_path)
           
            # ========== 步骤 3: 获取视频信息 ==========
            if preview_info == "yes":
                logger.add_section("3. 获取视频信息")
           
            cmd_info = [
                'ffprobe',
                '-v', 'error',
                '-select_streams', 'v:0',
                '-show_entries', 'stream=width,height,r_frame_rate,duration',
                '-of', 'json',
                video_path
            ]
           
            result = subprocess.run(cmd_info, capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)
            stream = data['streams'][0]
           
            orig_width = int(stream.get('width', 0))
            orig_height = int(stream.get('height', 0))
            orig_duration = float(stream.get('duration', 0))
           
            if preview_info == "yes":
                logger.add_info("分辨率", f"{orig_width}×{orig_height}")
                logger.add_info("时长", f"{orig_duration:.2f}s ({int(orig_duration//60)}m {int(orig_duration%60)}s)")
           
            # ========== 步骤 4: 计算输出参数 ==========
            if preview_info == "yes":
                logger.add_section("4. 计算输出参数")
           
            estimated_size = FFmpegUtils.estimate_output_size(orig_duration, quality)
           
            if preview_info == "yes":
                logger.add_info("输出尺寸", f"{orig_width}×{orig_height}")
                logger.add_info("输出帧率", f"{fps} fps")
                logger.add_info("编码器", codec)
                logger.add_info("质量级别", quality)
                logger.add_info("估算文件大小", f"{estimated_size:.2f}MB")
                logger.add_info("保存输出", save_output)
           
            # ========== 步骤 5: 检查磁盘空间 ==========
            output_dir = folder_paths.get_output_directory()
            _, ext = os.path.splitext(video_path)
            if not ext:
                ext = ".mp4"
           
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"{filename_prefix}_{int(fps)}fps_{timestamp}{ext}"
            output_path = os.path.join(output_dir, output_filename)
           
            if save_output == "yes":
                if preview_info == "yes":
                    logger.add_section("5. 检查磁盘空间")
               
                has_space, free_space = FFmpegUtils.check_disk_space(output_path, estimated_size * 1.2)
                if not has_space:
                    if preview_info == "yes":
                        logger.add_error(f"空间不足! 需要 {estimated_size*1.2:.2f}MB, 仅有 {free_space:.2f}MB")
                    raise Exception(f"磁盘空间不足")
               
                if preview_info == "yes":
                    logger.add_success(f"空间充足 (可用 {free_space:.2f}MB)")
           
            # ========== 步骤 6: 执行转换 ==========
            if preview_info == "yes":
                logger.add_section("6. 执行转换")
                logger.add_info("开始时间", datetime.now().strftime("%H:%M:%S"))
           
            crf_map = {"low": 28, "medium": 18, "high": 10}
            crf = crf_map.get(quality, 18)
           
            cmd = [
                'ffmpeg',
                '-y',
                '-i', video_path,
                '-vf', f'fps=fps={fps}:round=near',
                '-c:v', codec,
                '-crf', str(crf),
                '-c:a', 'aac',
                '-b:a', '128k',
                output_path
            ]
           
            # 如果不保存，输出到 /dev/null（仅进行处理，不保存）
            if save_output == "no":
                cmd[-1] = '-f' if os.name == 'nt' else '/dev/null'
           
            # 执行 FFmpeg
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )
           
            # 逐行读取输出，获取进度
            line_count = 0
            for line in process.stdout:
                line = line.strip()
                if not line:
                    continue
               
                # 每 10 行打印一次进度（避免输出过多）
                if preview_info == "yes" and ('frame=' in line or 'time=' in line):
                    line_count += 1
                    if line_count % 10 == 0:
                        info = FFmpegUtils.parse_ffmpeg_output(line)
                        if 'frame' in info and 'time' in info:
                            logger.add_info(
                                f"进度 [{info.get('time', 'N/A')}]",
                                f"帧: {info.get('frame', 0)} FPS: {info.get('fps', 0):.1f} 速度: {info.get('speed', 0):.2f}x"
                            )
           
            process.wait()
           
            if process.returncode != 0:
                raise Exception(f"FFmpeg 处理失败 (代码: {process.returncode})")
           
            # ========== 步骤 7: 验证输出 ==========
            if preview_info == "yes":
                logger.add_section("7. 验证输出")
           
            if save_output == "yes":
                if not os.path.exists(output_path):
                    raise Exception("输出文件未生成")
               
                output_size = os.path.getsize(output_path) / 1024 / 1024
                if preview_info == "yes":
                    logger.add_success(f"文件已生成 ({output_size:.2f}MB)")
            else:
                output_size = estimated_size
                if preview_info == "yes":
                    logger.add_success(f"处理完成（仅预览，未保存）")
                output_path = "" # 返回空路径表示未保存
           
            # ========== 步骤 8: 生成总结 ==========
            if preview_info == "yes":
                logger.add_section("8. 处理总结")
                logger.add_info("输出文件", output_filename)
                logger.add_info("输出大小", f"{output_size:.2f}MB")
           
            summary = (
                f"✓ 转换成功!\n"
                f"输入: {os.path.basename(video_path)} ({orig_width}×{orig_height})\n"
                f"输出: {output_filename} ({output_size:.2f}MB)\n"
                f"参数: {fps}fps, {codec}, 质量{quality}"
            )
           
            log_output = logger.finish() if preview_info == "yes" else summary
           
            # 关键修改：包装成 VHS_FILENAMES，让 ComfyUI 队列优先显示这个文件
            filenames = []
            # 返回标准的 VHS_FILENAMES 格式
            vhs_filenames = {
                "filenames": [output_filename] if (save_output == "yes" and output_path) else [],
                "subfolder": ""
            }
              
            return (vhs_filenames, summary, log_output)
       
        except Exception as e:
            logger.add_error(str(e))
            log_output = logger.finish()
            raise Exception(f"{str(e)}")

# ============================================================================
# 节点 2: FFmpeg 视频信息获取
# ============================================================================
class FFmpegVideoInfo:
    """
    FFmpeg 视频信息查询节点
   
    功能:
    - 获取视频的详细信息（分辨率、帧率、时长等）
    - 计算派生参数（长宽比、总帧数等）
    - 显示详细的分析日志
   
    使用场景:
    - 在处理视频前了解其属性
    - 判断是否需要转换格式或参数
    - 与其他节点配合进行参数验证
    """
   
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video_path": ("STRING", {
                    "forceInput": True,
                    "tooltip": "输入视频文件的完整路径"
                }),
            },
        }
   
    RETURN_TYPES = ("STRING", "INT", "INT", "FLOAT", "FLOAT", "STRING")
    RETURN_NAMES = ("info", "width", "height", "fps", "duration", "detailed_log")
    FUNCTION = "get_info"
    CATEGORY = "MyTools/AudioVideo"
   
    def get_info(self, video_path):
        """
        获取视频信息
       
        返回:
            - info: 格式化的信息字符串
            - width: 视频宽度（像素）
            - height: 视频高度（像素）
            - fps: 帧率（帧/秒）
            - duration: 时长（秒）
            - detailed_log: 详细的分析日志
        """
       
        logger = ProgressLogger("FFmpeg 视频信息获取")
       
        try:
            # ========== 环境检查 ==========
            logger.add_section("1. 环境检查")
           
            if not FFmpegUtils.check_ffprobe_installed(logger):
                raise Exception("ffprobe 未安装")
           
            # ========== 验证文件 ==========
            logger.add_section("2. 验证输入文件")
            video_path = FFmpegUtils.validate_input_file(video_path, logger)
           
            # ========== 获取信息 ==========
            logger.add_section("3. 获取视频信息")
           
            cmd = [
                'ffprobe',
                '-v', 'error',
                '-select_streams', 'v:0',
                '-show_entries', 'stream=width,height,r_frame_rate,duration',
                '-of', 'json',
                video_path
            ]
           
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=10
            )
           
            data = json.loads(result.stdout)
            stream = data['streams'][0]
           
            width = int(stream.get('width', 0))
            height = int(stream.get('height', 0))
            duration = float(stream.get('duration', 0))
           
            # 解析帧率（通常格式为 num/den，例如 30/1）
            fps = 30.0
            if 'r_frame_rate' in stream:
                fps_str = stream['r_frame_rate']
                if '/' in fps_str:
                    num, den = fps_str.split('/')
                    fps = float(num) / float(den)
                else:
                    fps = float(fps_str)
           
            # 计算派生参数
            total_frames = int(duration * fps)
            minutes = int(duration // 60)
            seconds = int(duration % 60)
           
            logger.add_info("分辨率", f"{width}×{height}")
            logger.add_info("帧率", f"{fps:.2f} fps")
            logger.add_info("时长", f"{duration:.2f}s ({minutes}m {seconds}s)")
            logger.add_info("总帧数", total_frames)
           
            # ========== 计算额外信息 ==========
            logger.add_section("4. 计算派生参数")
           
            aspect_ratio = width / height if height > 0 else 0
            pixel_count = width * height
           
            logger.add_info("长宽比", f"{aspect_ratio:.2f}:1")
            logger.add_info("总像素数", f"{pixel_count:,}")
           
            # ========== 生成输出 ==========
            logger.add_section("5. 输出信息")
           
            info = (
                f"✓ 视频信息\n"
                f"分辨率: {width}×{height}\n"
                f"帧率: {fps:.2f}fps\n"
                f"时长: {minutes}m {seconds}s\n"
                f"总帧数: {total_frames}"
            )
           
            log_output = logger.finish()
           
            return (info, width, height, fps, duration, log_output)
       
        except Exception as e:
            logger.add_error(str(e))
            log_output = logger.finish()
            raise Exception(f"{str(e)}")

# ============================================================================
# 节点 3: FFmpeg 分辨率调整
# ============================================================================
class FFmpegResize:
    """
    FFmpeg 分辨率调整节点
   
    功能:
    - 调整视频分辨率
    - 支持等比缩放（黑边）或拉伸两种模式
    - 实时显示处理进度
    - 可选保存和预览
   
    使用场景:
    - 将视频转为手机竖屏格式（1080×1920）
    - 将高清视频缩小以减小文件
    - 统一多个视频的分辨率用于拼接
    """
   
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video_path": ("STRING", {
                    "forceInput": True,
                    "tooltip": "输入视频文件的完整路径"
                }),
                "width": ("INT", {
                    "default": 1920,
                    "min": 320,
                    "max": 4096,
                    "step": 8,
                    "tooltip": "输出宽度（像素）"
                }),
                "height": ("INT", {
                    "default": 1080,
                    "min": 240,
                    "max": 2304,
                    "step": 8,
                    "tooltip": "输出高度（像素）"
                }),
            },
            "optional": {
                "filename_prefix": ("STRING", {
                    "default": "ffmpeg_resized",
                    "tooltip": "输出文件的前缀"
                }),
                "keep_aspect": (["yes", "no"], {
                    "default": "yes",
                    "tooltip": "是否保持长宽比\nyes: 等比缩放，四周补黑边\nno: 直接拉伸，可能变形"
                }),
                "save_output": (["yes", "no"], {
                    "default": "yes",
                    "tooltip": "是否保存输出视频"
                }),
                "preview_info": (["yes", "no"], {
                    "default": "yes",
                    "tooltip": "是否显示详细的预览信息"
                }),
            },
        }
   
    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("video_path", "summary", "detailed_log")
    FUNCTION = "resize_video"
    CATEGORY = "MyTools/AudioVideo"
   
    def resize_video(self, video_path, width, height,
                    filename_prefix="ffmpeg_resized", keep_aspect="yes",
                    save_output="yes", preview_info="yes"):
        """
        执行分辨率调整
       
        参数:
            video_path: 输入视频路径
            width: 输出宽度
            height: 输出高度
            filename_prefix: 输出文件的前缀
            keep_aspect: 是否保持长宽比
            save_output: 是否保存输出
            preview_info: 是否显示详细信息
        """
       
        logger = ProgressLogger("FFmpeg 分辨率调整")
       
        try:
            # ========== 环境检查 ==========
            if preview_info == "yes":
                logger.add_section("1. 环境检查")
               
                if not FFmpegUtils.check_ffmpeg_installed(logger):
                    raise Exception("FFmpeg 未安装")
            else:
                if not FFmpegUtils.check_ffmpeg_installed():
                    raise Exception("FFmpeg 未安装")
           
            # ========== 验证输入 ==========
            if preview_info == "yes":
                logger.add_section("2. 验证输入文件")
                video_path = FFmpegUtils.validate_input_file(video_path, logger)
            else:
                video_path = FFmpegUtils.validate_input_file(video_path)
           
            # ========== 获取原始信息 ==========
            if preview_info == "yes":
                logger.add_section("3. 获取原始视频信息")
           
            cmd_info = [
                'ffprobe',
                '-v', 'error',
                '-select_streams', 'v:0',
                '-show_entries', 'stream=width,height,duration',
                '-of', 'json',
                video_path
            ]
           
            result = subprocess.run(cmd_info, capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)
            stream = data['streams'][0]
           
            orig_width = int(stream.get('width', 1920))
            orig_height = int(stream.get('height', 1080))
            duration = float(stream.get('duration', 0))
           
            if preview_info == "yes":
                logger.add_info("原始分辨率", f"{orig_width}×{orig_height}")
                logger.add_info("目标分辨率", f"{width}×{height}")
                logger.add_info("保持比例", keep_aspect)
           
            # ========== 生成输出文件 ==========
            output_dir = folder_paths.get_output_directory()
            _, ext = os.path.splitext(video_path)
            if not ext:
                ext = ".mp4"
           
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"{filename_prefix}_{width}x{height}_{timestamp}{ext}"
            output_path = os.path.join(output_dir, output_filename)
           
            if preview_info == "yes":
                logger.add_section("4. 准备输出")
                logger.add_info("输出文件", output_filename)
           
            # ========== 构建 FFmpeg 命令 ==========
            if preview_info == "yes":
                logger.add_section("5. 执行调整")
           
            if keep_aspect == "yes":
                # 等比缩放 + 黑边居中
                scale_filter = (
                    f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                    f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2"
                )
                scale_mode = "等比缩放 + 黑边居中"
            else:
                # 直接拉伸
                scale_filter = f"scale={width}:{height}"
                scale_mode = "直接拉伸"
           
            if preview_info == "yes":
                logger.add_info("缩放模式", scale_mode)
                logger.add_info("开始时间", datetime.now().strftime("%H:%M:%S"))
           
            cmd = [
                'ffmpeg',
                '-y',
                '-i', video_path,
                '-vf', scale_filter,
                '-c:v', 'libx264',
                '-crf', '18',
                '-c:a', 'copy',
                output_path
            ]
           
            # 如果不保存，输出到 /dev/null
            if save_output == "no":
                cmd[-1] = '-f' if os.name == 'nt' else '/dev/null'
           
            # 执行 FFmpeg
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )
           
            # 显示进度
            line_count = 0
            for line in process.stdout:
                line = line.strip()
                if not line:
                    continue
               
                if preview_info == "yes" and ('frame=' in line or 'time=' in line):
                    line_count += 1
                    if line_count % 10 == 0:
                        info = FFmpegUtils.parse_ffmpeg_output(line)
                        if 'time' in info:
                            logger.add_info(
                                f"进度 [{info.get('time', 'N/A')}]",
                                f"速度: {info.get('speed', 0):.2f}x"
                            )
           
            process.wait()
           
            if process.returncode != 0:
                raise Exception(f"FFmpeg 处理失败")
           
            # ========== 验证输出 ==========
            if preview_info == "yes":
                logger.add_section("6. 验证输出")
           
            if save_output == "yes":
                output_size = os.path.getsize(output_path) / 1024 / 1024
                if preview_info == "yes":
                    logger.add_success(f"文件已生成 ({output_size:.2f}MB)")
            else:
                output_size = 0
                if preview_info == "yes":
                    logger.add_success(f"处理完成（仅预览，未保存）")
                output_path = ""
           
            # ========== 总结 ==========
            if preview_info == "yes":
                logger.add_section("7. 处理总结")
                logger.add_info("输出文件", output_filename)
                logger.add_info("输出大小", f"{output_size:.2f}MB")
           
            summary = (
                f"✓ 调整完成!\n"
                f"原始: {orig_width}×{orig_height}\n"
                f"输出: {width}×{height}\n"
                f"大小: {output_size:.2f}MB"
            )
           
            log_output = logger.finish() if preview_info == "yes" else summary
           
            return (output_path, summary, log_output)
       
        except Exception as e:
            logger.add_error(str(e))
            log_output = logger.finish()
            raise Exception(f"{str(e)}")

# ============================================================================
# 节点注册
# ============================================================================
NODE_CLASS_MAPPINGS = {
    "FFmpegFpsConverter": FFmpegFpsConverter,
    "FFmpegVideoInfo": FFmpegVideoInfo,
    "FFmpegResize": FFmpegResize,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "FFmpegFpsConverter": "FFmpeg 帧率转换",
    "FFmpegVideoInfo": "FFmpeg 视频信息",
    "FFmpegResize": "FFmpeg 分辨率调整",
}
