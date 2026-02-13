import torch
import numpy as np
import sys
import os
import time

RIFE_PATH = "/workspace/Practical-RIFE"
if RIFE_PATH not in sys.path:
    sys.path.append(RIFE_PATH)

try:
    from train_log.RIFE_HDv3 import Model
except ImportError:
    # 启动时不抛异常，只打印提示，让节点能正常显示
    print(f"[RIFE 提示] 模型源码未找到（路径: {RIFE_PATH}），节点仍可显示，运行时会报错")
    # 不 raise，让节点继续注册成功

class PracticalRIFE_Direct:
    """
    RIFE 视频帧插值节点（显存优化版）
    - 支持批量图像序列插帧
    - 可调节显存占用，适合 3090 等显卡
    - 启动时不加载模型，确保节点一定能显示
    - 运行工作流时才加载模型并执行插帧
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
                               "要求：连续帧，按顺序排列"
                }),
                "multi": ("INT", {
                    "default": 2,
                    "min": 2,
                    "max": 8,
                    "step": 1,
                    "tooltip": "每两帧之间插入多少帧\n"
                               "2 = 插入1帧（2倍帧率）\n"
                               "4 = 插入3帧（4倍帧率）\n"
                               "越大，帧率越高，但耗时越长"
                }),
                "scale": ("FLOAT", {
                    "default": 1.0,
                    "min": 0.1,
                    "max": 2.0,
                    "step": 0.1,
                    "tooltip": "模型内部缩放比例（通常保持1.0）\n"
                               "调小可加速、降低显存占用\n"
                               "调大可提升细节（但显存和时间增加）"
                }),
                "vram_limit_frames": ("INT", {
                    "default": 1,
                    "min": 1,
                    "max": 200,
                    "step": 1,
                    "tooltip": "显存中最多同时保留多少帧\n"
                               "值越小，显存占用越低（适合3090/24GB以下显卡）\n"
                               "值越大，速度越快（但显存可能爆掉）\n"
                               "推荐：3090 用 1~4，4090 用 10~50"
                }),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "interpolate"
    CATEGORY = "Video/Interpolation"

    def interpolate(self, images, multi, scale, vram_limit_frames):
        # 模型加载移到这里：运行工作流时才执行
        if self.model is None:
            try:
                print(f"[RIFE] 正在加载模型... 路径: {RIFE_PATH}/train_log")
                self.model = Model()
                self.model.load_model(os.path.join(RIFE_PATH, 'train_log'), -1)
                self.model.eval()
                self.model.device()
                print("[RIFE] 模型加载成功")
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
       
        # 将输入帧放到 GPU
        frames = images.permute(0, 3, 1, 2).to(self.device)
        output_frames_cpu = []          # 最终存放在系统内存的结果
        temp_gpu_buffer = []            # 显存缓冲区
       
        print(f"[Practical-RIFE] 🚀 启动！显存缓冲上限: {vram_limit_frames} 帧")
       
        with torch.no_grad():
            for i in range(n - 1):
                I0 = frames[i:i+1]
                I1 = frames[i+1:i+2]
               
                # 放入起始帧
                temp_gpu_buffer.append(I0)
               
                # 插帧计算
                for step in range(1, multi):
                    timestep = step / multi
                    interp_frame = self.model.inference(I0, I1, timestep=timestep, scale=scale)
                    temp_gpu_buffer.append(interp_frame)
               
                # --- 核心：显存水位控制 ---
                if len(temp_gpu_buffer) >= vram_limit_frames:
                    # 批量搬运到 CPU，腾出显存空间
                    cpu_batch = torch.cat(temp_gpu_buffer, dim=0).cpu()
                    output_frames_cpu.append(cpu_batch)
                    temp_gpu_buffer = []  # 清空 GPU 缓冲区
                    torch.cuda.empty_cache()  # 强制释放显存碎片
               
                if i % 50 == 0 and i > 0:
                    print(f"[Practical-RIFE] 进度: {i}/{n} | 瞬时速度: {i/(time.time()-start_time):.2f} it/s")
            
            # 处理最后一帧和残余缓冲区
            temp_gpu_buffer.append(frames[-1:])
            if temp_gpu_buffer:
                output_frames_cpu.append(torch.cat(temp_gpu_buffer, dim=0).cpu())
        
        # 内存合并
        out_tensor = torch.cat(output_frames_cpu, dim=0)
        out_tensor = out_tensor.permute(0, 2, 3, 1)
       
        duration = time.time() - start_time
        print(f"✅ 任务结束! 总耗时: {duration:.2f}s | 平均速度: {n/duration:.2f} it/s")
       
        return (out_tensor,)

NODE_CLASS_MAPPINGS = {"PracticalRIFE_Direct": PracticalRIFE_Direct}
NODE_DISPLAY_NAME_MAPPINGS = {"PracticalRIFE_Direct": "🚀 RIFE 3090 显存极限调优版"}
