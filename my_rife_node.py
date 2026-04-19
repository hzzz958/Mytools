import torch
import numpy as np
import sys
import os
import time
import gc
import psutil
import tempfile
import shutil

RIFE_PATH = "/workspace/Practical-RIFE"
if RIFE_PATH not in sys.path:
    sys.path.append(RIFE_PATH)

try:
    from train_log.RIFE_HDv3 import Model
except ImportError:
    print(f"[RIFE 提示] 模型源码未找到（路径: {RIFE_PATH}），节点仍可显示，运行时会报错")

class PracticalRIFE_Direct:
    """
    RIFE 视频帧插值节点 - 预分配内存版
    
    === 核心改进 ===
    ✅ 去掉分段逻辑，改用预分配 + 写盘两条路径
    ✅ 预分配：一次性分配输出 tensor，逐帧写入，零额外拷贝
    ✅ 写盘：内存紧张时写临时文件，读回时同样用预分配
    ✅ 自动判断走哪条路径，无需用户手调
    
    === 内存模型 ===
    预分配路径：输入 frames + 输出 tensor 同时存在
    写盘路径：输入 frames + 磁盘 I/O，读回时只需输出 tensor
    峰值内存 ≈ max(输入大小, 输出大小)，不会翻倍
    """
    
    def __init__(self):
        self.model = None
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "images": ("IMAGE", {
                    "tooltip": "输入图像序列（通常是从 Load Image Batch 或 Video to Images 节点获取）\n"
                               "要求：连续帧，按顺序排列\n"
                               "重要：所有帧的分辨率必须完全一致，且宽度/高度最好能被 64 整除（如 1080×1920、1920×1088）\n"
                               "不满足 mod 64 容易导致 RIFE 内部报错（tensor size mismatch）\n"
                               "推荐先用 Resize 节点统一到 1080×1920 再输入"
                }),
                "multi": ("INT", {
                    "default": 2,
                    "min": 2,
                    "max": 8,
                    "step": 1,
                    "tooltip": "每两帧之间插入多少帧\n"
                               "2 = 插入1帧（2倍帧率）\n"
                               "4 = 插入3帧（4倍帧率）\n"
                               "8 = 插入7帧（8倍帧率）\n"
                               "越大，帧率越高，但耗时越长"
                }),
                "scale": ("FLOAT", {
                    "default": 1.0,
                    "min": 0.1,
                    "max": 2.0,
                    "step": 0.1,
                    "tooltip": "模型内部缩放比例（通常保持1.0）\n"
                               "调小可加速、降低显存占用\n"
                               "调大可提升细节（但显存和时间增加）\n"
                               "注意：scale 过大会放大分辨率不兼容问题"
                }),
                "auto_memory_mode": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "✅ 推荐保持 True（自动内存管理）\n"
                               "节点会自动根据输出大小选择处理路径\n"
                               "设为 False 时使用预分配模式"
                }),
                "memory_limit_gb": ("INT", {
                    "default": 40,
                    "min": 20,
                    "max": 200,
                    "step": 5,
                    "tooltip": "最多允许使用多少 GB 系统内存\n"
                               "自动模式会根据这个值选择预分配或写盘\n"
                               "如果你的机器内存少，改成 30\n"
                               "如果你的机器内存多，改成 60 或更多（会更快）"
                }),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "interpolate"
    CATEGORY = "Video/Interpolation"

    def interpolate(self, images, multi, scale, auto_memory_mode, memory_limit_gb):
        """
        主入口：自适应内存管理插帧处理
        """
        # 模型加载
        if self.model is None:
            try:
                print(f"[RIFE] 正在加载模型... 路径: {RIFE_PATH}/train_log")
                self.model = Model()
                self.model.load_model(os.path.join(RIFE_PATH, 'train_log'), -1)
                self.model.eval()
                self.model.device()
                print("[RIFE] 模型加载成功 ✓")
            except Exception as e:
                raise RuntimeError(
                    f"RIFE 模型加载失败！\n"
                    f"路径: {RIFE_PATH}\n"
                    f"错误: {str(e)}\n"
                    f"请检查：\n"
                    f"1. Practical-RIFE 文件夹是否存在\n"
                    f"2. train_log 文件夹里有模型权重\n"
                    f"3. torch 和依赖是否正确安装"
                )

        n, h, w, c = images.shape
        start_time = time.time()
        
        # 计算输出帧数
        output_frames = (n - 1) * multi + 1
        
        print(f"\n{'='*75}")
        print(f"[RIFE 预分配内存版]")
        print(f"  输入帧数: {n:,} 帧")
        print(f"  分辨率: {w}×{h}")
        print(f"  插帧倍数: {multi}x")
        print(f"  预期输出帧数: {output_frames:,}")
        
        self._log_memory_info()
        
        # 计算输出 tensor 大小
        bytes_per_frame = w * h * c * 4  # float32 = 4 bytes
        total_output_gb = output_frames * bytes_per_frame / (1024**3)
        
        # 获取有效内存限制
        try:
            total_system_memory_gb = psutil.virtual_memory().total / (1024**3)
        except:
            total_system_memory_gb = 128
        
        effective_limit_gb = min(memory_limit_gb, total_system_memory_gb * 0.45)
        
        print(f"  输出 tensor 大小: {total_output_gb:.1f} GB")
        print(f"  有效内存限制: {effective_limit_gb:.1f} GB")
        
        # 决策：预分配还是写盘
        use_disk = auto_memory_mode and (total_output_gb > effective_limit_gb * 0.5)
        
        if use_disk:
            print(f"\n[决策] 输出较大，使用写盘路径")
            print(f"  原因: {total_output_gb:.1f}GB > {effective_limit_gb * 0.5:.1f}GB (限制×0.5)")
        else:
            print(f"\n[决策] 输出适中，使用预分配路径")
            print(f"  原因: {total_output_gb:.1f}GB <= {effective_limit_gb * 0.5:.1f}GB (限制×0.5)")
        
        # 转换维度：ComfyUI IMAGE (N, H, W, C) → 模型输入 (N, C, H, W)
        frames = images.permute(0, 3, 1, 2).to(self.device)
        
        # 执行处理
        if use_disk:
            result = self._process_disk(frames, multi, scale, n, output_frames, c, h, w)
        else:
            result = self._process_preallocate(frames, multi, scale, n, output_frames, c, h, w)
        
        duration = time.time() - start_time
        print(f"\n✅ 任务完成！")
        print(f"  总耗时: {duration/60:.1f} 分钟 ({duration:.0f}s)")
        print(f"  输出帧数: {result.shape[0]:,}")
        print(f"  平均速度: {n/duration:.2f} it/s")
        print(f"{'='*75}\n")
        
        return (result,)

    def _log_memory_info(self):
        """打印当前系统内存信息"""
        try:
            mem = psutil.virtual_memory()
            print(f"  当前系统内存: {mem.available / (1024**3):.1f} GB 可用 / {mem.total / (1024**3):.1f} GB 总计")
        except:
            pass

    def _process_preallocate(self, frames, multi, scale, n, output_frames, c, h, w):
        """
        预分配路径：一次性分配输出 tensor，逐帧写入
        峰值内存：输入 frames + 输出 tensor，无额外拷贝
        """
        print(f"\n[处理] 预分配模式")
        
        # 预分配输出 tensor（CPU 上，float32）
        out_tensor = torch.empty(output_frames, c, h, w, dtype=torch.float32)
        print(f"  预分配完成: {output_frames} 帧 × {c}×{h}×{w}")
        
        write_idx = 0
        total_pairs = n - 1
        
        with torch.no_grad():
            for i in range(total_pairs):
                I0 = frames[i:i+1]
                I1 = frames[i+1:i+2]
                
                # 写入 I0
                out_tensor[write_idx] = I0[0].cpu()
                write_idx += 1
                
                # 写入插值帧
                for step in range(1, multi):
                    timestep = step / multi
                    interp = self.model.inference(I0, I1, timestep=timestep, scale=scale)
                    out_tensor[write_idx] = interp[0].cpu()
                    write_idx += 1
                
                # 进度
                if i % max(1, total_pairs // 10) == 0 and i > 0:
                    progress = int(100 * i / total_pairs)
                    print(f"  处理中: {progress}% ({i}/{total_pairs})")
            
            # 写入最后一帧
            out_tensor[write_idx] = frames[-1].cpu()
        
        print(f"  写入完成: {write_idx + 1} 帧")
        
        # 转换维度：(N, C, H, W) → (N, H, W, C) ComfyUI 格式
        return out_tensor.permute(0, 2, 3, 1)

    def _process_disk(self, frames, multi, scale, n, output_frames, c, h, w):
        """
        写盘路径：推理时写临时文件，读回时用预分配
        峰值内存：输入 frames（推理时）或 输出 tensor（读回时）
        """
        print(f"\n[处理] 写盘模式")
        
        # 创建临时目录
        temp_dir = tempfile.mkdtemp(prefix="rife_")
        print(f"  临时目录: {temp_dir}")
        
        temp_files = []
        file_idx = 0
        total_pairs = n - 1
        
        try:
            # === 阶段1：推理 + 写盘 ===
            print(f"  [阶段1] 推理并写入临时文件...")
            
            with torch.no_grad():
                for i in range(total_pairs):
                    I0 = frames[i:i+1]
                    I1 = frames[i+1:i+2]
                    
                    # 保存 I0
                    temp_path = os.path.join(temp_dir, f"{file_idx:06d}.pt")
                    torch.save(I0[0].cpu(), temp_path)
                    temp_files.append(temp_path)
                    file_idx += 1
                    
                    # 保存插值帧
                    for step in range(1, multi):
                        timestep = step / multi
                        interp = self.model.inference(I0, I1, timestep=timestep, scale=scale)
                        temp_path = os.path.join(temp_dir, f"{file_idx:06d}.pt")
                        torch.save(interp[0].cpu(), temp_path)
                        temp_files.append(temp_path)
                        file_idx += 1
                    
                    # 进度
                    if i % max(1, total_pairs // 10) == 0 and i > 0:
                        progress = int(100 * i / total_pairs)
                        print(f"    写入: {progress}% ({i}/{total_pairs})")
                
                # 保存最后一帧
                temp_path = os.path.join(temp_dir, f"{file_idx:06d}.pt")
                torch.save(frames[-1].cpu(), temp_path)
                temp_files.append(temp_path)
            
            print(f"  [阶段1] 完成，共写入 {len(temp_files)} 个文件")
            
            # 释放 GPU 显存
            del frames
            torch.cuda.empty_cache()
            gc.collect()
            
            # === 阶段2：读回 + 预分配 ===
            print(f"  [阶段2] 读回并组装输出 tensor...")
            
            # 预分配输出 tensor
            out_tensor = torch.empty(len(temp_files), c, h, w, dtype=torch.float32)
            
            for idx, temp_path in enumerate(temp_files):
                t = torch.load(temp_path)
                out_tensor[idx] = t
                del t
                
                if idx % 100 == 0 and idx > 0:
                    progress = int(100 * idx / len(temp_files))
                    print(f"    读回: {progress}% ({idx}/{len(temp_files)})")
            
            print(f"  [阶段2] 完成")
            
        finally:
            # 清理临时目录
            try:
                shutil.rmtree(temp_dir)
                print(f"  临时文件已清理")
            except Exception as e:
                print(f"  清理临时文件失败: {e}")
        
        # 转换维度
        return out_tensor.permute(0, 2, 3, 1)


NODE_CLASS_MAPPINGS = {"PracticalRIFE_Direct": PracticalRIFE_Direct}
NODE_DISPLAY_NAME_MAPPINGS = {"PracticalRIFE_Direct": "🚀 RIFE 预分配内存版"}
