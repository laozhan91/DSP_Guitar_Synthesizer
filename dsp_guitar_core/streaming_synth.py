"""流式实时合成引擎
====================
把离线「整段合成」改为「逐块 (block) 推进」的实时 KS 合成。

架构：
  - KSVoice: 单根弦的常驻振动状态（延迟线 + 读指针 + 衰减/亮度参数）
  - StreamingGuitarSynth: 维护所有声部，drain 事件队列并逐块渲染

线程模型：
  - 按键线程只把命令 push 进事件队列（加锁，O(1)）
  - 音频回调线程 drain 队列并执行全部 DSP（锁外 DSP、无动态分配）

性能：
  - 逐样本推进，但并发弦数受限（每次扫弦 ≤6 根），单块开销远低于实时预算
  - 回调内禁止分配数组：混音缓冲预分配、声部列表原地淘汰
"""
import threading
from collections import deque

import numpy as np
from scipy.signal import lfilter

from .performance import StrumCommand, MuteCommand

# 基础激励幅度（乘 velocity 后注入延迟线），避免过载
EXCITE_GAIN = 0.3


class KSVoice:
    """单根弦的 Karplus-Strong 延迟线状态"""

    __slots__ = ('freq', 'group', 'n_delay', 'delay', 'idx',
                 'alpha', 'rho', 'energy', '_seg', '_seg_next')

    def __init__(self, freq, group, alpha, rho, sample_rate):
        self.freq = float(freq)
        self.group = group
        self.n_delay = max(2, int(round(sample_rate / self.freq)))
        self.delay = np.zeros(self.n_delay, dtype=np.float32)
        self.idx = 0
        self.alpha = alpha
        self.rho = rho
        self.energy = 1.0  # 当前能量，低于阈值后被引擎淘汰
        # 预分配块级运算缓冲，避免回调内动态分配
        self._seg = np.empty(4096, dtype=np.float32)
        self._seg_next = np.empty(4096, dtype=np.float32)

    def excite(self, velocity, rng, offset_samples=0):
        """注入激励噪声，可整体错位 offset_samples 实现扫弦错位。

        把噪声以 offset_samples 为起点环形写入 delay，idx 保持从 0 开始，
        于是前 offset_samples 个样本读出来是 0（静音），之后自然读到激励，
        无需在渲染循环里做分支。
        """
        noise = rng.standard_normal(self.n_delay).astype(np.float32)
        noise *= (EXCITE_GAIN * velocity)
        n = self.n_delay
        pos = offset_samples % n
        if pos == 0:
            self.delay += noise
        else:
            self.delay[pos:] += noise[: n - pos]
            self.delay[:pos] += noise[n - pos:]

    def mute(self):
        """制音：让余音快速衰减（保留少量平滑，避免硬切爆音）"""
        self.rho = 0.5

    def render(self, out, frames):
        """块级向量化推进 KS 递推，把本弦输出累加到 out。

        与逐样本递推严格等价（每段处理 step 个样本，step 不超过整圈 n）：
          seg[k]       = delay[(idx + k) % n]              # 本段读出的值
          seg_next[k]  = delay[(idx + k + 1) % n]          # 相邻下一位置（上一周期写回值）
          delay[idx+k] = rho * ((1-alpha)*seg[k] + alpha*seg_next[k])

        因 n 可能小于 blocksize（高音弦），按"到数组末尾"分段循环，
        保证每段都落在 delay 内部，避免跨圈切片越界。
        """
        delay = self.delay
        n = self.n_delay
        alpha = self.alpha
        rho = self.rho
        idx = self.idx

        done = 0
        while done < frames:
            step = min(frames - done, n - idx)
            if step == n:
                # 完整一圈会让最后一个样本的“下一位置”读到本段已写回的首元素，
                # 与逐样本递推不等价，故限制单段长度不超过 n-1。
                step = n - 1
            seg = self._seg[:step]
            seg_next = self._seg_next[:step]

            # 1. 读本段窗口（连续，不跨圈）
            seg[:] = delay[idx:idx + step]
            out[done:done + step] += seg

            # 2. 相邻下一位置（最后一个元素环绕到圈首）
            seg_next[:-1] = seg[1:]
            seg_next[-1] = delay[(idx + step) % n]

            # 3. 低通 + 衰减，就地复用 seg 作为写回缓冲
            np.multiply(seg, 1.0 - alpha, out=seg)
            np.multiply(seg_next, alpha, out=seg_next)
            np.add(seg, seg_next, out=seg)
            np.multiply(seg, rho, out=seg)

            # 4. 写回本段
            delay[idx:idx + step] = seg
            idx = (idx + step) % n
            done += step

        self.idx = idx
        # 用整条延迟线的能量判断衰减（与块相位无关，更稳定）
        self.energy = float(np.dot(delay, delay)) / n if n else 0.0


class StreamingGuitarSynth:
    """流式吉他合成引擎：维护声部、执行命令、逐块渲染"""

    def __init__(self, sample_rate, alpha=0.7, rho=0.997,
                 master_gain=0.9, energy_threshold=1e-5,
                 strum_delay=0.012, use_ir=False, max_voices=48):
        self.sample_rate = sample_rate
        self.alpha = alpha
        self.rho = rho
        self.master_gain = master_gain
        self.energy_threshold = energy_threshold
        self.strum_delay = strum_delay
        self.max_voices = max_voices

        self.voices = []
        self.rng = np.random.default_rng()
        self._queue = deque()
        self._lock = threading.Lock()

        # 预分配混音缓冲（blocksize 上限，避免回调内分配）
        self._buf = np.zeros(4096, dtype=np.float32)

        # 可选琴体 IR（分块 FIR 状态）
        self._ir = None
        self._zi = None
        if use_ir:
            from .synthesizer import generate_synthetic_ir
            self._ir = generate_synthetic_ir(sample_rate=sample_rate).astype(np.float64)
            self._zi = np.zeros(len(self._ir) - 1, dtype=np.float64)

    # --------------------------------------------------
    # 按键线程调用：只投递命令（O(1) 加锁）
    # --------------------------------------------------

    def strum(self, cmd: StrumCommand):
        with self._lock:
            self._queue.append(cmd)

    def mute(self, cmd: MuteCommand):
        with self._lock:
            self._queue.append(cmd)

    # --------------------------------------------------
    # 音频回调线程调用
    # --------------------------------------------------

    def process(self, outdata, frames):
        # 1. drain 事件（锁内只做交换，不执行 DSP）
        with self._lock:
            events = list(self._queue)
            self._queue.clear()

        # 2. 执行命令（锁外，回调线程）
        for ev in events:
            if isinstance(ev, StrumCommand):
                self._do_strum(ev)
            elif isinstance(ev, MuteCommand):
                self._do_mute(ev)

        # 3. 渲染（混音缓冲预分配，先清零）
        if frames > len(self._buf):
            self._buf = np.zeros(frames, dtype=np.float32)
        buf = self._buf[:frames]
        buf.fill(0.0)
        for v in self.voices:
            v.render(buf, frames)

        # 4. 淘汰衰减完的声部（原地倒序删除，避免重新分配）
        i = len(self.voices) - 1
        while i >= 0:
            if self.voices[i].energy < self.energy_threshold:
                self.voices.pop(i)
            i -= 1

        # 5. 可选琴体 FIR（保持状态的分块卷积）
        if self._ir is not None:
            filtered, self._zi = lfilter(self._ir, [1.0], buf, zi=self._zi)
            buf = filtered.astype(np.float32)

        # 6. 软限幅 + 主增益（全程就地计算，无临时分配）
        np.tanh(buf, out=buf)
        np.multiply(buf, self.master_gain, out=buf)
        outdata[:, 0] = buf

    # --------------------------------------------------
    # 命令执行（回调线程内部）
    # --------------------------------------------------

    def _do_strum(self, cmd: StrumCommand):
        freqs = list(cmd.freqs)
        # down: 低音弦先响（升序）；up: 高音弦先响（降序）
        ordered = sorted(freqs, reverse=(cmd.direction == 'up'))
        offset_step = int(round(self.strum_delay * self.sample_rate))
        for i, freq in enumerate(ordered):
            voice = KSVoice(freq, cmd.group, self.alpha, self.rho, self.sample_rate)
            voice.excite(cmd.velocity, self.rng, offset_samples=i * offset_step)
            self.voices.append(voice)

        # 声部上限：超出时淘汰最安静的声部，保证 CPU 有硬上界、不 xrun
        if len(self.voices) > self.max_voices:
            self.voices.sort(key=lambda v: v.energy, reverse=True)
            del self.voices[self.max_voices:]

    def _do_mute(self, cmd: MuteCommand):
        for v in self.voices:
            if v.group == cmd.group:
                v.mute()
