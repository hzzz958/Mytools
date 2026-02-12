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
    raise ImportError(f"找不到 RIFE 源码，请检查路径: {RIFE_PATH}")

class PracticalRIFE_Direct:
    def __init__(self):
        self.model = None
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "images": ("IMAGE",), 
                "multi": ("INT", {"default": 2, "min": 2, "max": 8}),
                "scale": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 2.0}),
                # 新增：显存常驻帧数限制
                "vram_limit_frames": ("INT", {"default": 1, "min": 1, "max": 200, "step": 1}),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "interpolate"
    CATEGORY = "Video/Interpolation"

    def interpolate(self, images, multi, scale, vram_limit_frames):
        if self.model is None:
            self.model = Model()
            self.model.load_model(os.path.join(RIFE_PATH, 'train_log'), -1)
            self.model.eval()
            self.model.device()

        n, h, w, c = images.shape
        start_time = time.time()
        
        # 将输入帧放到 GPU
        frames = images.permute(0, 3, 1, 2).to(self.device)
        output_frames_cpu = [] # 最终存放在系统内存的结果
        temp_gpu_buffer = []   # 显存缓冲区
        
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
                    temp_gpu_buffer = [] # 清空 GPU 缓冲区
                    torch.cuda.empty_cache() # 强制释放显存碎片
                
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
