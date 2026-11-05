"""可视化环形缓冲
==================
音频回调线程写入最新输出样本，GUI 线程按需读取，用于实时频谱/波形绘制。

- 预分配 numpy 数组，回调内零分配
- 单写者（回调）/单读者（GUI）模型：允许「撕裂读」，不做锁，
  最多多读/少读一帧，对可视化无影响
"""
import numpy as np


class VisualRingBuffer:
    """预分配环形缓冲：`write()` 在音频回调调用，`latest()` 在 GUI 线程调用"""

    def __init__(self, capacity=4096):
        self.capacity = int(capacity)
        self._buf = np.zeros(self.capacity, dtype=np.float32)
        self._write_pos = 0

    def write(self, data):
        n = data.shape[0] if hasattr(data, 'shape') else len(data)
        cap = self.capacity
        if n == 0:
            return
        if n >= cap:
            # 数据超过容量：只保留最后 cap 个
            self._buf[:] = data[n - cap:]
            self._write_pos = 0
            return
        pos = self._write_pos
        end = pos + n
        if end <= cap:
            self._buf[pos:end] = data
        else:
            first = cap - pos
            self._buf[pos:] = data[:first]
            self._buf[:end - cap] = data[first:]
        self._write_pos = end % cap

    def latest(self, n):
        """按时间顺序返回最新 n 个样本（在 GUI 线程调用，允许分配）"""
        n = min(int(n), self.capacity)
        if n == 0:
            return np.zeros(0, dtype=np.float32)
        pos = self._write_pos
        start = (pos - n) % self.capacity
        if start < pos:
            return self._buf[start:pos].copy()
        return np.concatenate((self._buf[start:], self._buf[:pos]))
