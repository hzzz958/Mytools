"""
FFmpeg 视频拼接节点
功能：拼接多个视频文件，支持多种过渡效果和完整的参数控制
作者：AI Assistant
日期：2024
"""

import os
import subprocess
import json
import tempfile
import shutil
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
        self.warnings = []
        self.issues = []
        
        # 添加开始信息
        self.add_log(f"{'='*70}")
        self.add_log(f"{task_name}")
        self.add_log(f"执行时间: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.add_log(f"{'='*70}")
    
    def add_log(self, message):
        """添加日志行，同时打印到控制台"""
        self.log_lines.append(message)
        print(message)
    
    def add_section(self, title):
        """添加分节标题"""
        self.add_log("")
        self.add_log(f"[{title}]")
        self.add_log("-" * 70)
    
    def add_info(self, key, value):
        """添加信息对"""
        self.add_log(f"  {key}: {value}")
    
    def add_success(self, message):
        """添加成功信息"""
        self.add_log(f"  ✓ {message}")
    
    def add_warning(self, message):
        """添加警告信息"""
        self.add_log(f"  ⚠️  {message}")
        self.warnings.append(message)
    
    def add_error(self, message):
        """添加错误信息"""
        self.add_log(f"  ✗ {message}")
    
    def add_issue(self, issue_text):
        """添加问题记录"""
        self.issues.append(issue_text)
    
    def get_elapsed_time(self):
        """获取已用时间"""
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
    
    def get_issues_summary(self):
        """获取问题摘要"""
        if not self.issues:
            return "没有检测到问题"
        return "\n".join(self.issues)


# ============================================================================
# FFmpeg 工具类
# ============================================================================

class FFmpegUtils:
    """
    FFmpeg 工具函数集合
    """
    
    @staticmethod
    def check_ffmpeg_installed(logger=None):
        """
        检查 FFmpeg 是否已安装
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
    def get_video_info(video_path, logger=None):
        """
        获取视频的详细信息
        
        返回：{
            'width': int,
            'height': int,
            'fps': float,
            'duration': float,
            'codec_name': str,
            'has_audio': bool,
            'audio_codec': str
        }
        """
        try:
            cmd = [
                'ffprobe',
                '-v', 'error',
                '-select_streams', 'v:0',
                '-show_entries', 'stream=width,height,r_frame_rate,duration,codec_name',
                '-of', 'json',
                video_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=10)
            data = json.loads(result.stdout)
            
            if not data.get('streams'):
                return None
            
            stream = data['streams'][0]
            
            width = int(stream.get('width', 0))
            height = int(stream.get('height', 0))
            duration = float(stream.get('duration', 0))
            codec_name = stream.get('codec_name', 'unknown')
            
            # 解析帧率
            fps = 30.0
            if 'r_frame_rate' in stream:
                fps_str = stream['r_frame_rate']
                if '/' in fps_str:
                    num, den = fps_str.split('/')
                    fps = float(num) / float(den)
                else:
                    fps = float(fps_str)
            
            # 检查是否有音频
            has_audio = False
            audio_codec = "none"
            
            cmd_audio = [
                'ffprobe',
                '-v', 'error',
                '-select_streams', 'a:0',
                '-show_entries', 'stream=codec_name',
                '-of', 'json',
                video_path
            ]
            
            try:
                result_audio = subprocess.run(cmd_audio, capture_output=True, text=True, check=True, timeout=10)
                data_audio = json.loads(result_audio.stdout)
                if data_audio.get('streams'):
                    has_audio = True
                    audio_codec = data_audio['streams'][0].get('codec_name', 'unknown')
            except:
                pass
            
            return {
                'width': width,
                'height': height,
                'fps': fps,
                'duration': duration,
                'codec_name': codec_name,
                'has_audio': has_audio,
                'audio_codec': audio_codec
            }
        
        except Exception as e:
            if logger:
                logger.add_error(f"获取视频信息失败: {e}")
            return None
    
    @staticmethod
    def check_disk_space(output_path, required_mb):
        """
        检查磁盘空间
        """
        try:
            stat = shutil.disk_usage(os.path.dirname(output_path))
            free_mb = stat.free / 1024 / 1024
            return (free_mb > required_mb, free_mb)
        except:
            return (True, None)


# ============================================================================
# 视频拼接节点
# ============================================================================

class FFmpegVideoConcatenate:
    """
    FFmpeg 视频拼接节点
    
    功能：
    - 读取文件夹中的多个视频
    - 检测分辨率和帧率是否一致
    - 支持多种拼接方式（直接拼接、淡入淡出、交叉淡化）
    - 保留所有视频的音频并混音
    - 完整的参数控制
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        """
        定义输入参数及其属性
        """
        return {
            "required": {
                # ========== 基本输入 ==========
                "video_folder": ("STRING", {
                    "default": "videos",
                    "tooltip": (
                        "ComfyUI/input/ 下的文件夹名称\n"
                        "例如：videos（会读取 input/videos/）\n"
                        "注意：文件必须通过 PHP 脚本上传到这里"
                    )
                }),
                
                # ========== 输出尺寸 ==========
                "output_width": ("INT", {
                    "default": 1080,
                    "min": 256,
                    "max": 4096,
                    "step": 8,
                    "tooltip": (
                        "输出视频的宽度（像素）\n"
                        "推荐值：1080（竖屏）或 1920（横屏）\n"
                        "注意：如果输入视频尺寸不同，将自动缩放到这个尺寸"
                    )
                }),
                
                "output_height": ("INT", {
                    "default": 1920,
                    "min": 256,
                    "max": 4096,
                    "step": 8,
                    "tooltip": (
                        "输出视频的高度（像素）\n"
                        "推荐值：1920（竖屏）或 1080（横屏）\n"
                        "常见组合：1080×1920(竖屏), 1920×1080(横屏)"
                    )
                }),
                
                # ========== 帧率 ==========
                "output_fps": ("FLOAT", {
                    "default": 30.0,
                    "min": 1.0,
                    "max": 120.0,
                    "step": 0.1,
                    "tooltip": (
                        "输出视频的帧率（fps）\n"
                        "推荐值：24(电影), 30(标准), 60(高帧率)\n"
                        "警告：如果输入视频帧率不一致，将统一转换到这个值"
                    )
                }),
                
                # ========== 拼接方式 ==========
                "concat_mode": (["direct", "transition_fade", "transition_crossfade"], {
                    "default": "direct",
                    "tooltip": (
                        "拼接方式选择\n"
                        "\n"
                        "【direct】直接拼接（最快）\n"
                        "  - 直接连接视频片段，无任何效果\n"
                        "  - 优点：速度快，文件小\n"
                        "  - 缺点：可能看到明显的跳切\n"
                        "  - 使用场景：对接效果要求不高的情况\n"
                        "\n"
                        "【transition_fade】淡入淡出过渡效果\n"
                        "  - 第一个视频淡出，第二个视频淡入，有短暂黑屏\n"
                        "  - 优点：简洁自然，标准的过渡效果\n"
                        "  - 缺点：处理速度中等\n"
                        "  - 使用场景：正式视频、演讲视频\n"
                        "\n"
                        "【transition_crossfade】交叉淡化过渡（推荐）\n"
                        "  - 两个视频在过渡点重叠，前一个淡出，后一个淡入\n"
                        "  - 优点：平滑自然，专业感强（渐入渐出效果）\n"
                        "  - 缺点：处理速度较慢\n"
                        "  - 使用场景：高质量视频、电影级别的效果"
                    )
                }),
            },
            
            "optional": {
                # ========== 过渡时长 ==========
                "transition_duration": ("FLOAT", {
                    "default": 0.5,
                    "min": 0.1,
                    "max": 2.0,
                    "step": 0.1,
                    "tooltip": (
                        "过渡效果的时长（秒）\n"
                        "说明：在两个视频之间的过渡时间\n"
                        "推荐值：0.3-0.7 秒\n"
                        "注意：过渡时长越长，处理时间越长\n"
                        "（仅在拼接方式不是 'direct' 时有效）"
                    )
                }),
                
                # ========== 视频编码 ==========
                "video_codec": (["libx264", "libx265"], {
                    "default": "libx264",
                    "tooltip": (
                        "视频编码器（codec）\n"
                        "\n"
                        "【libx264】H.264/AVC\n"
                        "  - 优点：兼容性好，速度快，应用广\n"
                        "  - 缺点：压缩率不如 H.265\n"
                        "  - 推荐：99% 的情况下使用这个 ★\n"
                        "\n"
                        "【libx265】H.265/HEVC\n"
                        "  - 优点：压缩率高，文件小 30-40%\n"
                        "  - 缺点：编码速度慢 5-10 倍\n"
                        "  - 推荐：只有在需要最小文件的时候使用"
                    )
                }),
                
                "video_quality": (["low", "medium", "high"], {
                    "default": "medium",
                    "tooltip": (
                        "输出视频质量（crf 值）\n"
                        "  - low: crf=28, 速度快，文件小 (约2Mbps)\n"
                        "  - medium: crf=18, 平衡质量和速度 (约5Mbps) ★推荐\n"
                        "  - high: crf=10, 高质量，文件大 (约10Mbps)\n"
                        "说明：crf 值越低，质量越好，文件越大"
                    )
                }),
                
                # ========== 音频编码 ==========
                "audio_codec": (["aac", "mp3", "libopus"], {
                    "default": "aac",
                    "tooltip": (
                        "音频编码器\n"
                        "  - aac: 高兼容性，通用格式 ★推荐\n"
                        "  - mp3: 兼容性好，但质量一般\n"
                        "  - libopus: 最新格式，高质量，但兼容性一般\n"
                        "说明：所有视频的音频轨会混合到一个音轨"
                    )
                }),
                
                "audio_bitrate": (["64k", "96k", "128k", "192k", "256k"], {
                    "default": "128k",
                    "tooltip": (
                        "音频比特率\n"
                        "  - 64k: 较低质量，文件小\n"
                        "  - 96k: 普通质量\n"
                        "  - 128k: 标准质量 ★推荐\n"
                        "  - 192k: 好质量\n"
                        "  - 256k: 高质量\n"
                        "说明：音频比特率越高，质量越好，但声音改善效果有限"
                    )
                }),
                
                # ========== 缩放和处理 ==========
                "scale_mode": (["fit_letterbox", "fill", "crop"], {
                    "default": "fit_letterbox",
                    "tooltip": (
                        "缩放模式\n"
                        "\n"
                        "【fit_letterbox】等比缩放 + 黑边居中 ★推荐\n"
                        "  - 保持原始长宽比，四周补黑边\n"
                        "  - 优点：不变形，完整显示所有内容\n"
                        "  - 缺点：可能有黑边\n"
                        "\n"
                        "【fill】拉伸填满（可能变形）\n"
                        "  - 直接拉伸到目标尺寸\n"
                        "  - 优点：充满整个屏幕\n"
                        "  - 缺点：可能会变形\n"
                        "\n"
                        "【crop】裁剪（可能损失内容）\n"
                        "  - 保持原始长宽比，超出部分裁剪\n"
                        "  - 优点：不变形\n"
                        "  - 缺点：可能损失图像边缘内容"
                    )
                }),
                
                "deinterlace": (["no", "yes"], {
                    "default": "no",
                    "tooltip": (
                        "是否需要去隔行（反交错）\n"
                        "  - no: 不处理（推荐，除非视频看起来闪烁）\n"
                        "  - yes: 进行去隔行处理（较慢）\n"
                        "说明：某些老视频是隔行格式，需要此处理"
                    )
                }),
                
                # ========== 输出和文件名 ==========
                "filename_prefix": ("STRING", {
                    "default": "concat_video",
                    "tooltip": (
                        "输出文件的前缀\n"
                        "完整文件名格式：{prefix}_{width}x{height}_{timestamp}.mp4\n"
                        "例如：concat_video_1080x1920_20240211_120000.mp4\n"
                        "建议：用有意义的名称，如 'final_video', 'presentation' 等"
                    )
                }),
                
                "save_log_file": (["no", "yes"], {
                    "default": "no",
                    "tooltip": (
                        "是否将处理日志保存到文件\n"
                        "  - no: 只在 ComfyUI 中显示日志\n"
                        "  - yes: 同时保存日志到 output 目录下的 .txt 文件\n"
                        "用途：方便查看详细的处理过程"
                    )
                }),
                
                # ========== 高级选项 ==========
                "detect_issues_only": (["no", "yes"], {
                    "default": "no",
                    "tooltip": (
                        "仅检测问题模式（不进行拼接）\n"
                        "  - no: 正常模式，扫描文件后立即开始拼接\n"
                        "  - yes: 检测模式，只扫描和检查，不拼接\n"
                        "用途：先检查文件是否有问题，再决定是否处理\n"
                        "场景：处理前想要预览文件信息和潜在问题"
                    )
                }),
                
                "preview_info": (["no", "yes"], {
                    "default": "yes",
                    "tooltip": (
                        "是否显示详细的处理信息\n"
                        "  - no: 只显示最终结果\n"
                        "  - yes: 显示每个步骤的详细信息和进度\n"
                        "建议：开发和调试时用 yes，正式使用可用 no"
                    )
                }),
            }
        }
    
    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("video_path", "video_info", "processing_log", "detected_issues")
    FUNCTION = "concatenate_videos"
    CATEGORY = "MyTools/AudioVideo"
    OUTPUT_NODE = True
    
    def concatenate_videos(self, 
                          video_folder,
                          output_width,
                          output_height,
                          output_fps,
                          concat_mode="direct",
                          transition_duration=0.5,
                          video_codec="libx264",
                          video_quality="medium",
                          audio_codec="aac",
                          audio_bitrate="128k",
                          scale_mode="fit_letterbox",
                          deinterlace="no",
                          filename_prefix="concat_video",
                          save_log_file="no",
                          detect_issues_only="no",
                          preview_info="yes"):
        """
        执行视频拼接
        
        参数说明：
            video_folder: 输入视频文件夹（相对于 input/ 目录）
            output_width, output_height: 输出尺寸
            output_fps: 输出帧率
            concat_mode: 拼接方式（direct/transition_fade/transition_crossfade）
            transition_duration: 过渡时长（仅在非 direct 模式有效）
            video_codec: 视频编码器
            video_quality: 视频质量
            audio_codec: 音频编码器
            audio_bitrate: 音频比特率
            scale_mode: 缩放模式
            deinterlace: 是否去隔行
            filename_prefix: 输出文件前缀
            save_log_file: 是否保存日志文件
            detect_issues_only: 是否仅检测问题
            preview_info: 是否显示详细信息
        
        返回：
            (视频路径, 视频信息, 处理日志, 检测问题)
        """
        
        logger = ProgressLogger("FFmpeg 视频拼接")
        
        try:
            # ========== 步骤 1: 环境检查 ==========
            if preview_info == "yes":
                logger.add_section("1. 环境检查")
                
                if not FFmpegUtils.check_ffmpeg_installed(logger):
                    raise Exception("FFmpeg 未安装或不在 PATH 中")
                
                if not FFmpegUtils.check_ffprobe_installed(logger):
                    raise Exception("ffprobe 未安装或不在 PATH 中")
            else:
                if not FFmpegUtils.check_ffmpeg_installed():
                    raise Exception("FFmpeg 未安装")
                if not FFmpegUtils.check_ffprobe_installed():
                    raise Exception("ffprobe 未安装")
            
            # ========== 步骤 2: 获取文件夹路径并扫描 ==========
            if preview_info == "yes":
                logger.add_section("2. 扫描文件夹")
            
            input_dir = folder_paths.get_input_directory()
            video_dir = os.path.join(input_dir, video_folder)
            
            if not os.path.exists(video_dir):
                raise FileNotFoundError(f"文件夹不存在: {video_dir}")
            
            if preview_info == "yes":
                logger.add_info("视频文件夹", video_dir)
            
            # 扫描视频文件
            video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.m4v']
            video_files = [
                f for f in os.listdir(video_dir)
                if os.path.splitext(f)[1].lower() in video_extensions
            ]
            
            if not video_files:
                raise FileNotFoundError(f"文件夹中没有视频文件: {video_dir}")
            
            video_files.sort()
            
            if preview_info == "yes":
                logger.add_success(f"找到 {len(video_files)} 个视频文件")
                logger.add_log("  文件列表:")
                for i, f in enumerate(video_files, 1):
                    logger.add_log(f"    {i}. {f}")
            
            # ========== 步骤 3: 检测每个视频的属性 ==========
            if preview_info == "yes":
                logger.add_section("3. 检测视频属性")
            
            video_info_list = []
            resolutions = set()
            framerates = set()
            
            for idx, video_filename in enumerate(video_files, 1):
                video_path = os.path.join(video_dir, video_filename)
                
                info = FFmpegUtils.get_video_info(video_path, logger)
                if not info:
                    if preview_info == "yes":
                        logger.add_warning(f"无法获取视频 {idx} 的信息，跳过")
                    logger.add_issue(f"[视频{idx}] {video_filename} - 无法读取")
                    continue
                
                info['filename'] = video_filename
                info['path'] = video_path
                video_info_list.append(info)
                
                resolutions.add((info['width'], info['height']))
                framerates.add(round(info['fps'], 2))
                
                if preview_info == "yes":
                    resolution_str = f"{info['width']}×{info['height']}"
                    audio_str = f"有 ({info['audio_codec']})" if info['has_audio'] else "无"
                    
                    logger.add_log(f"  [{idx}] {video_filename}")
                    logger.add_log(f"      分辨率: {resolution_str} | 帧率: {info['fps']:.2f}fps | 音频: {audio_str}")
            
            if not video_info_list:
                raise Exception("无法读取任何视频文件")
            
            # ========== 步骤 4: 检测问题和不一致 ==========
            if preview_info == "yes":
                logger.add_section("4. 检测问题")
            
            issues_found = []
            
            if len(resolutions) > 1:
                issue_msg = f"检测到分辨率不一致！找到 {len(resolutions)} 种不同的分辨率: {resolutions}"
                if preview_info == "yes":
                    logger.add_warning(issue_msg)
                issues_found.append(issue_msg)
                logger.add_issue(f"⚠️  {issue_msg}")
                logger.add_issue(f"   → 将自动缩放所有视频到 {output_width}×{output_height}")
            else:
                if preview_info == "yes":
                    logger.add_success(f"分辨率一致: {list(resolutions)[0]}")
            
            if len(framerates) > 1:
                issue_msg = f"检测到帧率不一致！找到 {len(framerates)} 种不同的帧率: {framerates}"
                if preview_info == "yes":
                    logger.add_warning(issue_msg)
                issues_found.append(issue_msg)
                logger.add_issue(f"⚠️  {issue_msg}")
                logger.add_issue(f"   → 将自动统一转换到 {output_fps}fps")
            else:
                if preview_info == "yes":
                    logger.add_success(f"帧率一致: {list(framerates)[0]}fps")
            
            # 检查音频
            has_audio_files = [v for v in video_info_list if v['has_audio']]
            if len(has_audio_files) > 0:
                if preview_info == "yes":
                    logger.add_success(f"共 {len(has_audio_files)} 个视频有音频，将混合为一个音轨")
            else:
                if preview_info == "yes":
                    logger.add_warning("没有视频有音频")
                logger.add_issue("⚠️  所有视频都没有音频")
            
            # ========== 如果仅检测问题模式，到此结束 ==========
            if detect_issues_only == "yes":
                if preview_info == "yes":
                    logger.add_section("5. 检测完成")
                    logger.add_log("  仅检测模式，不进行拼接")
                
                log_output = logger.finish()
                issues_summary = logger.get_issues_summary()
                
                return ("", "检测模式，未进行拼接", log_output, issues_summary)
            
            # ========== 步骤 5: 创建临时目录 ==========
            if preview_info == "yes":
                logger.add_section("5. 准备处理")
            
            temp_dir = tempfile.mkdtemp(prefix="ffmpeg_concat_")
            if preview_info == "yes":
                logger.add_info("临时目录", temp_dir)
            
            # ========== 步骤 6: 根据拼接方式进行处理 ==========
            if concat_mode == "direct":
                # 直接拼接模式
                result = self._concatenate_direct(
                    video_info_list, 
                    temp_dir, 
                    output_width, 
                    output_height, 
                    output_fps,
                    video_codec,
                    video_quality,
                    audio_codec,
                    audio_bitrate,
                    scale_mode,
                    deinterlace,
                    logger,
                    preview_info
                )
            
            elif concat_mode == "transition_fade":
                # 淡入淡出模式
                result = self._concatenate_with_fade(
                    video_info_list,
                    temp_dir,
                    output_width,
                    output_height,
                    output_fps,
                    transition_duration,
                    video_codec,
                    video_quality,
                    audio_codec,
                    audio_bitrate,
                    scale_mode,
                    deinterlace,
                    logger,
                    preview_info
                )
            
            elif concat_mode == "transition_crossfade":
                # 交叉淡化模式
                result = self._concatenate_with_crossfade(
                    video_info_list,
                    temp_dir,
                    output_width,
                    output_height,
                    output_fps,
                    transition_duration,
                    video_codec,
                    video_quality,
                    audio_codec,
                    audio_bitrate,
                    scale_mode,
                    deinterlace,
                    logger,
                    preview_info
                )
            
            else:
                raise ValueError(f"未知的拼接模式: {concat_mode}")
            
            if not result['success']:
                raise Exception(f"拼接失败: {result.get('error', '未知错误')}")
            
            # ========== 步骤 7: 生成最终输出路径 ==========
            if preview_info == "yes":
                logger.add_section("6. 生成输出文件")
            
            output_dir = folder_paths.get_output_directory()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"{filename_prefix}_{output_width}x{output_height}_{timestamp}.mp4"
            output_path = os.path.join(output_dir, output_filename)
            
            # 移动临时文件到输出目录
            shutil.move(result['temp_output'], output_path)
            
            if preview_info == "yes":
                logger.add_success(f"输出文件: {output_filename}")
            
            output_size = os.path.getsize(output_path) / 1024 / 1024
            if preview_info == "yes":
                logger.add_info("文件大小", f"{output_size:.2f}MB")
            
            # ========== 步骤 8: 清理临时文件 ==========
            if preview_info == "yes":
                logger.add_section("7. 清理")
            
            try:
                shutil.rmtree(temp_dir)
                if preview_info == "yes":
                    logger.add_success("临时文件已清理")
            except:
                if preview_info == "yes":
                    logger.add_warning("无法完全清理临时文件")
            
            # ========== 生成最终日志 ==========
            log_output = logger.finish()
            
            # ========== 生成视频信息摘要 ==========
            total_duration = sum(v['duration'] for v in video_info_list)
            
            video_info_summary = (
                f"✓ 拼接完成\n"
                f"视频数：{len(video_info_list)}\n"
                f"总时长：{total_duration:.1f}s ({int(total_duration//60)}m {int(total_duration%60)}s)\n"
                f"输出尺寸：{output_width}×{output_height}\n"
                f"输出帧率：{output_fps}fps\n"
                f"拼接方式：{concat_mode}\n"
                f"输出编码：{video_codec} ({video_quality} quality)\n"
                f"音频编码：{audio_codec} ({audio_bitrate})\n"
                f"输出大小：{output_size:.2f}MB\n"
                f"处理耗时：{logger.get_elapsed_time()}"
            )
            
            # ========== 保存日志文件（如果需要） ==========
            if save_log_file == "yes":
                log_filename = f"{filename_prefix}_{timestamp}_log.txt"
                log_path = os.path.join(output_dir, log_filename)
                with open(log_path, 'w', encoding='utf-8') as f:
                    f.write(log_output)
                if preview_info == "yes":
                    logger.add_log(f"日志已保存: {log_filename}")
            
            issues_summary = logger.get_issues_summary()
            
            return (output_path, video_info_summary, log_output, issues_summary)
        
        except Exception as e:
            logger.add_error(str(e))
            log_output = logger.finish()
            raise Exception(f"拼接失败: {str(e)}")
    
    # ========== 拼接实现函数 ==========
    
    def _concatenate_direct(self, video_info_list, temp_dir, output_width, output_height,
                           output_fps, video_codec, video_quality, audio_codec, audio_bitrate,
                           scale_mode, deinterlace, logger, preview_info):
        """
        直接拼接模式实现
        
        工作原理：
        1. 对每个视频进行预处理（缩放、统一帧率）
        2. 生成 concat.txt 列表文件
        3. 使用 FFmpeg concat demuxer 直接拼接
        """
        try:
            if preview_info == "yes":
                logger.add_section("6. 执行拼接（直接模式）")
            
            # 第 1 步：预处理视频
            if preview_info == "yes":
                logger.add_log("  【子步骤】预处理视频文件...")
            
            preprocessed_files = []
            crf_map = {"low": 28, "medium": 18, "high": 10}
            crf = crf_map.get(video_quality, 18)
            
            for idx, video_info in enumerate(video_info_list, 1):
                video_path = video_info['path']
                filename = video_info['filename']
                
                prep_filename = f"video_{idx:03d}_prep.mp4"
                prep_output = os.path.join(temp_dir, prep_filename)
                
                if preview_info == "yes":
                    logger.add_log(f"    [{idx}/{len(video_info_list)}] 处理 {filename}...")
                
                # 构建缩放滤镜
                scale_filter = self._build_scale_filter(scale_mode, output_width, output_height, deinterlace)
                
                # 构建 FFmpeg 命令
                cmd = [
                    'ffmpeg',
                    '-y',
                    '-i', video_path,
                    '-vf', scale_filter,
                    '-r', str(output_fps),
                    '-c:v', video_codec,
                    '-crf', str(crf),
                    '-c:a', audio_codec,
                    '-b:a', audio_bitrate,
                    prep_output
                ]
                
                result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=None)
                preprocessed_files.append(prep_output)
                
                if preview_info == "yes":
                    logger.add_log(f"      ✓ 完成")
            
            # 第 2 步：生成 concat 列表
            if preview_info == "yes":
                logger.add_log("  【子步骤】生成拼接列表...")
            
            concat_file = os.path.join(temp_dir, "concat.txt")
            with open(concat_file, 'w', encoding='utf-8') as f:
                for prep_file in preprocessed_files:
                    f.write(f"file '{prep_file}'\n")
            
            if preview_info == "yes":
                logger.add_log("    ✓ 列表已生成")
            
            # 第 3 步：执行拼接
            if preview_info == "yes":
                logger.add_log("  【子步骤】执行拼接...")
            
            output_path = os.path.join(temp_dir, "output.mp4")
            
            concat_cmd = [
                'ffmpeg',
                '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', concat_file,
                '-c:v', 'copy',
                '-c:a', 'copy',
                output_path
            ]
            
            result = subprocess.run(concat_cmd, check=True, capture_output=True, text=True, timeout=None)
            
            if preview_info == "yes":
                logger.add_log("    ✓ 拼接完成")
            
            return {
                'success': True,
                'temp_output': output_path
            }
        
        except Exception as e:
            return {
                'success': False,
                'error': f"直接拼接失败: {str(e)}"
            }
    
    def _concatenate_with_fade(self, video_info_list, temp_dir, output_width, output_height,
                              output_fps, transition_duration, video_codec, video_quality,
                              audio_codec, audio_bitrate, scale_mode, deinterlace, logger, preview_info):
        """
        淡入淡出过渡模式实现
        
        工作原理：
        1. 对每个视频进行预处理
        2. 在每个视频末尾添加淡出效果
        3. 拼接处理后的视频
        """
        try:
            if preview_info == "yes":
                logger.add_section("6. 执行拼接（淡入淡出模式）")
            
            if preview_info == "yes":
                logger.add_log("  【子步骤】预处理视频文件（添加淡出效果）...")
            
            preprocessed_files = []
            crf_map = {"low": 28, "medium": 18, "high": 10}
            crf = crf_map.get(video_quality, 18)
            
            for idx, video_info in enumerate(video_info_list, 1):
                video_path = video_info['path']
                filename = video_info['filename']
                duration = video_info['duration']
                
                prep_filename = f"video_{idx:03d}_prep.mp4"
                prep_output = os.path.join(temp_dir, prep_filename)
                
                if preview_info == "yes":
                    logger.add_log(f"    [{idx}/{len(video_info_list)}] 处理 {filename}...")
                
                # 构建缩放滤镜
                scale_filter = self._build_scale_filter(scale_mode, output_width, output_height, deinterlace)
                
                # 添加淡出效果
                fade_start = max(0, duration - transition_duration)
                scale_filter = f"{scale_filter},fade=t=out:st={fade_start}:d={transition_duration}"
                
                cmd = [
                    'ffmpeg',
                    '-y',
                    '-i', video_path,
                    '-vf', scale_filter,
                    '-r', str(output_fps),
                    '-c:v', video_codec,
                    '-crf', str(crf),
                    '-c:a', audio_codec,
                    '-b:a', audio_bitrate,
                    prep_output
                ]
                
                result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=None)
                preprocessed_files.append(prep_output)
                
                if preview_info == "yes":
                    logger.add_log(f"      ✓ 完成")
            
            # 生成 concat 列表
            if preview_info == "yes":
                logger.add_log("  【子步骤】生成拼接列表...")
            
            concat_file = os.path.join(temp_dir, "concat.txt")
            with open(concat_file, 'w', encoding='utf-8') as f:
                for prep_file in preprocessed_files:
                    f.write(f"file '{prep_file}'\n")
            
            # 执行拼接
            if preview_info == "yes":
                logger.add_log("  【子步骤】执行拼接...")
            
            output_path = os.path.join(temp_dir, "output.mp4")
            
            concat_cmd = [
                'ffmpeg',
                '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', concat_file,
                '-c:v', 'copy',
                '-c:a', 'copy',
                output_path
            ]
            
            result = subprocess.run(concat_cmd, check=True, capture_output=True, text=True, timeout=None)
            
            if preview_info == "yes":
                logger.add_log("    ✓ 拼接完成（淡入淡出效果）")
            
            return {
                'success': True,
                'temp_output': output_path
            }
        
        except Exception as e:
            return {
                'success': False,
                'error': f"淡入淡出拼接失败: {str(e)}"
            }
    
    def _concatenate_with_crossfade(self, video_info_list, temp_dir, output_width, output_height,
                                output_fps, transition_duration, video_codec, video_quality,
                                audio_codec, audio_bitrate, scale_mode, deinterlace, logger, preview_info):
        """
        交叉淡化（渐入渐出）模式实现 - 音视频同步过渡
        """
        try:
            if preview_info == "yes":
                logger.add_section("6. 执行拼接（交叉淡化模式 - 音视频同步渐入渐出）")
                logger.add_log(f" 过渡时长: {transition_duration}秒")

            if len(video_info_list) <= 1:
                if preview_info == "yes":
                    logger.add_log(" 只有一个视频，无需过渡，直接返回原文件")
                return {
                    'success': True,
                    'temp_output': video_info_list[0]['path']  # 直接用原始路径（或预处理后的）
                }

            if preview_info == "yes":
                logger.add_log(" 【子步骤1】预处理所有视频（统一分辨率、帧率）...")

            preprocessed_files = []
            crf_map = {"low": 28, "medium": 18, "high": 10}
            crf = crf_map.get(video_quality, 18)

            # 预处理：统一尺寸、帧率（但不加任何淡化滤镜）
            for idx, video_info in enumerate(video_info_list, 1):
                video_path = video_info['path']
                filename = video_info['filename']

                prep_filename = f"video_{idx:03d}_prep.mp4"
                prep_output = os.path.join(temp_dir, prep_filename)

                if preview_info == "yes":
                    logger.add_log(f"  [{idx}/{len(video_info_list)}] 处理 {filename}...")

                scale_filter = self._build_scale_filter(scale_mode, output_width, output_height, deinterlace)

                # 如果原始帧率与输出不一致，才强制转换
                r_filter = f"-r {output_fps}" if abs(video_info['fps'] - output_fps) > 0.1 else ""

                cmd = [
                    'ffmpeg', '-y',
                    '-i', video_path,
                    '-vf', scale_filter,
                ]
                if r_filter:
                    cmd.extend(['-r', str(output_fps)])

                cmd.extend([
                    '-c:v', video_codec,
                    '-crf', str(crf),
                    '-c:a', audio_codec,
                    '-b:a', audio_bitrate,
                    '-map', '0:v?',   # 视频轨（可选，防止无视频崩溃）
                    '-map', '0:a?',   # 音频轨（可选）
                    prep_output
                ])

                result = subprocess.run(cmd, check=True, capture_output=True, text=True)
                preprocessed_files.append(prep_output)

                if preview_info == "yes":
                    logger.add_log("   ✓ 完成")

            # ────────────────────────────────────────────────
            # 核心：构建音视频交叉淡化 filter_complex
            # ────────────────────────────────────────────────
            if preview_info == "yes":
                logger.add_log(" 【子步骤2】构建交叉淡化滤镜链...")

            filter_parts = []
            inputs = []
            video_label = "[0:v]"
            audio_label = "[0:a]"

            # 累计 offset，用于计算每个过渡的开始位置
            cumulative_duration = 0.0

            for i in range(1, len(preprocessed_files)):
                prev_duration = video_info_list[i-1]['duration']
                # offset = 前一段累计时长 + 前一段时长 - 过渡时长（重叠过渡）
                offset = max(0, cumulative_duration + prev_duration - transition_duration)
                cumulative_duration = offset  # 更新累计

                v_out = f"[v{i}]"
                a_out = f"[a{i}]"

                # 视频：xfade
                filter_parts.append(
                    f"{video_label}[{i}:v]xfade=transition=fade:duration={transition_duration}:offset={offset}{v_out}"
                )

                # 音频：acrossfade（使用三角窗，声音过渡自然）
                # 先检查当前视频是否有音频
                has_audio = video_info_list[i]['has_audio']

                if has_audio:
                    audio_input = f"[{i}:a]"
                else:
                    # 无音频 → 生成静音轨（长度与视频匹配）
                    audio_input = f"anullsrc=r=48000:cl=stereo,atrim=0:{prev_duration}[silence{i}]"
                    filter_parts.append(audio_input)
                    audio_input = f"[silence{i}]"

                filter_parts.append(
                    f"{audio_label}{audio_input}acrossfade=d={transition_duration}:curve1=ipar:curve2=ipar{a_out}"
                )

                video_label = v_out
                audio_label = a_out

            filter_complex = ";".join(filter_parts)

            # ────────────────────────────────────────────────
            # 最终 FFmpeg 命令 - 一次性完成所有过渡
            # ────────────────────────────────────────────────
            if preview_info == "yes":
                logger.add_log(" 【子步骤3】执行最终交叉淡化拼接...")

            output_path = os.path.join(temp_dir, "final_crossfade.mp4")

            cmd = ['ffmpeg', '-y']
            for prep_file in preprocessed_files:
                cmd.extend(['-i', prep_file])

            cmd.extend([
                '-filter_complex', filter_complex,
                '-map', video_label,
                '-map', audio_label,
                '-c:v', video_codec,
                '-crf', str(crf),
                '-c:a', audio_codec,
                '-b:a', audio_bitrate,
                '-shortest',                # 以最短流为准（防止静音轨过长）
                output_path
            ])

            result = subprocess.run(cmd, check=True, capture_output=True, text=True)

            if preview_info == "yes":
                logger.add_success(f"交叉淡化拼接完成 → {output_path}")

            return {
                'success': True,
                'temp_output': output_path
            }

        except subprocess.CalledProcessError as e:
            error_msg = f"FFmpeg 执行失败: {e}\nstderr: {e.stderr}"
            logger.add_error(error_msg)
            return {'success': False, 'error': error_msg}
        except Exception as e:
            error_msg = f"交叉淡化处理异常: {str(e)}"
            logger.add_error(error_msg)
            return {'success': False, 'error': error_msg}
    
    def _build_scale_filter(self, scale_mode, width, height, deinterlace):
        """
        构建缩放滤镜
        """
        if scale_mode == "fit_letterbox":
            # 等比缩放 + 黑边居中
            scale_filter = (
                f"scale={width}:{height}:"
                f"force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:"
                f"(ow-iw)/2:(oh-ih)/2:color=black"
            )
        elif scale_mode == "fill":
            # 直接拉伸
            scale_filter = f"scale={width}:{height}"
        elif scale_mode == "crop":
            # 裁剪
            scale_filter = (
                f"scale={width}:{height}:"
                f"force_original_aspect_ratio=increase,"
                f"crop={width}:{height}"
            )
        
        # 添加去隔行滤镜（如果需要）
        if deinterlace == "yes":
            scale_filter = f"{scale_filter},yadif=0:-1:0"
        
        return scale_filter


# ============================================================================
# 节点注册
# ============================================================================

NODE_CLASS_MAPPINGS = {
    "FFmpegVideoConcatenate": FFmpegVideoConcatenate,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FFmpegVideoConcatenate": "FFmpeg 视频拼接",
}
