import numpy as np
from scipy.io import wavfile

sr = 44100
duration = 2.0  # 增加到2秒，让频谱看起来更清晰
t = np.linspace(0, duration, int(sr * duration), endpoint=False)

# 合成一个包含基频和多个泛音的吉他声音
fundamental = 220  # 基频 220Hz
harmonics = [
    (1.0, fundamental),          # 基频
    (0.6, fundamental * 2),      # 2次谐波 (440Hz)
    (0.4, fundamental * 3),      # 3次谐波 (660Hz)
    (0.3, fundamental * 4),      # 4次谐波 (880Hz)
    (0.2, fundamental * 5),      # 5次谐波 (1100Hz)
    (0.1, fundamental * 6),      # 6次谐波 (1320Hz)
]

data = np.zeros_like(t)
for amplitude, freq in harmonics:
    data += amplitude * np.sin(2 * np.pi * freq * t)

# === 关键修改部分开始 ===
# 1. 计算最大值
max_val = np.max(np.abs(data))
if max_val == 0:
    max_val = 1.0

# 2. 归一化到 -1.0 ~ 1.0 之间
data = data / max_val

# 3. 乘以 0.8 的增益，防止裁剪失真，并转换到 int16
data = (data * 0.8 * 32767).astype(np.int16)
# === 关键修改部分结束 ===

# 写入文件
wavfile.write("assets/guitar_sample.wav", sr, data)
print(f"新测试音频已生成！时长 {duration} 秒，包含基频和 {len(harmonics)-1} 个泛音。")
print(f"最大值校验: {max_val}")