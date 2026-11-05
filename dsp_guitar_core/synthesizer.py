
"""
synthesizer.py - DSP 音频合成器核心模块
=========================================
功能：
  1. 基础波形生成（Sine / Square / Sawtooth / Triangle）
  2. ADSR 包络生成器（模拟吉他拨弦物理过程）
  3. 频谱包络调制（将第一阶段提取的频谱包络作为频域振幅系数）
  4. 合成音频导出（16-bit PCM 归一化 + WAV 输出）

设计思路：
  - 吉他属于拨弦乐器，其发声物理过程为：拨弦瞬间激励起弦的多种振动模式
    （基频 + 泛音列），随后因弦的阻尼和空气阻力而逐渐衰减。
  - ADSR 模拟这一过程：Attack 极短（拨弦瞬间起振）、Decay 较明显（从峰值衰减到延音水平）、
    Sustain 维持（手指按住琴弦时的稳态）、Release 较短（松手后余音消散）。
  - 频谱包络（Spectral Envelope）是吉他的"音色指纹"——不同和弦/品位下，
    各次谐波的相对振幅分布不同，调制这一步让合成音具备真实吉他的泛音特征。
"""

import numpy as np
from scipy.io import wavfile
from typing import Optional, Tuple, Literal
import warnings

# 抑制 numpy 浮点精度警告
# VisibleDeprecationWarning 在新版 numpy 中已移除，使用兼容写法
try:
    warnings.filterwarnings('ignore', category=np.VisibleDeprecationWarning)
except AttributeError:
    pass


class Synthesizer:
    """
    吉他 DSP 合成器类。

    参数:
        sample_rate: 采样率 (Hz)，默认 44100
    """

    # 支持的波形类型
    WAVEFORMS = Literal['sine', 'square', 'sawtooth', 'triangle']

    def __init__(self, sample_rate: int = 44100):
        self.sample_rate = sample_rate

    # --------------------------------------------------
    # 1. 基础波形生成
    # --------------------------------------------------

    def generate_waveform(
        self,
        frequency: float,
        duration: float,
        waveform_type: str = 'sine',
        amplitude: float = 1.0
    ) -> np.ndarray:
        """
        生成基础周期波形。

        参数:
            frequency:    基频 (Hz)，如 A4 = 440.0
            duration:     时长 (秒)
            waveform_type: 波形类型 ('sine' | 'square' | 'sawtooth' | 'triangle')
            amplitude:    振幅系数 (默认 1.0)

        返回:
            np.ndarray: 单声道浮点波形数组 [-1.0, 1.0]
        """
        num_samples = int(duration * self.sample_rate)
        t = np.linspace(0.0, duration, num_samples, endpoint=False)

        if waveform_type == 'sine':
            # 纯正弦波: y = A * sin(2*pi*f*t)
            signal = amplitude * np.sin(2.0 * np.pi * frequency * t)
        elif waveform_type == 'square':
            # 方波: 用 sign(sin) 近似（实际方波含奇次谐波，幅度按 1/n 衰减）
            signal = amplitude * np.sign(np.sin(2.0 * np.pi * frequency * t))
        elif waveform_type == 'sawtooth':
            # 锯齿波: 含所有谐波，幅度按 1/n 衰减
            signal = amplitude * (2.0 * (frequency * t - np.floor(0.5 + frequency * t)))
        elif waveform_type == 'triangle':
            # 三角波: 含奇次谐波，幅度按 1/n^2 衰减
            signal = amplitude * (
                2.0 * np.abs(frequency * t - np.floor(0.5 + frequency * t)) - 1.0
            )
        else:
            raise ValueError(f"不支持的波形类型: {waveform_type}")

        # 归一化到 [-1, 1]
        max_val = np.max(np.abs(signal))
        if max_val > 0:
            signal = signal / max_val

        return signal

    # --------------------------------------------------
    # 2. ADSR 包络生成
    # --------------------------------------------------

    def generate_adsr_envelope(
        self,
        duration: float,
        attack: float = 0.005,
        decay: float = 0.1,
        sustain_level: float = 0.6,
        release: float = 0.3
    ) -> np.ndarray:
        """
        生成 ADSR (Attack - Decay - Sustain - Release) 时域包络。

        吉他拨弦的 ADSR 典型参数范围:
            Attack:  0.001 ~ 0.02 s   (拨弦瞬间，极快起振)
            Decay:   0.05 ~ 0.3 s     (从峰值衰减到稳态)
            Sustain: 0.3 ~ 0.8        (按住弦时的稳态振幅比例)
            Release: 0.1 ~ 0.5 s      (松手后余音消散)

        参数:
            duration:       总时长 (秒)
            attack:         起振时间 (秒)
            decay:          衰减时间 (秒)
            sustain_level:  延音水平 (0.0 ~ 1.0)
            release:        释放时间 (秒)

        返回:
            np.ndarray: ADSR 包络数组，形状与输出信号一致
        """
        num_samples = int(duration * self.sample_rate)
        envelope = np.zeros(num_samples)

        # 计算各阶段采样点数
        attack_samples = int(attack * self.sample_rate)
        decay_samples = int(decay * self.sample_rate)
        sustain_samples = num_samples - attack_samples - decay_samples - int(release * self.sample_rate)
        release_samples = int(release * self.sample_rate)

        # 确保非负
        sustain_samples = max(sustain_samples, 0)
        release_samples = max(release_samples, 0)

        # Attack 阶段: 线性上升 0 -> 1
        if attack_samples > 0:
            envelope[:attack_samples] = np.linspace(0.0, 1.0, attack_samples)

        # Decay 阶段: 从 1.0 指数衰减到 sustain_level
        decay_end = attack_samples + decay_samples
        if decay_samples > 0 and attack_samples < num_samples:
            decay_start = max(attack_samples, 0)
            decay_region = np.arange(0, min(decay_samples, num_samples - decay_start))
            # 指数衰减: A(t) = sustain + (1 - sustain) * exp(-t / tau)
            tau = decay_samples / 3.0  # 衰减时间常数
            envelope[decay_start:decay_start + len(decay_region)] = (
                sustain_level + (1.0 - sustain_level) * np.exp(-decay_region / tau)
            )

        # Sustain 阶段: 维持 sustain_level
        sustain_start = attack_samples + decay_samples
        if sustain_samples > 0:
            sustain_end = sustain_start + sustain_samples
            envelope[sustain_start:min(sustain_end, num_samples)] = sustain_level

        # Release 阶段: 从 sustain_level 指数衰减到 0
        release_start = sustain_start + sustain_samples
        if release_samples > 0 and release_start < num_samples:
            release_end = release_start + release_samples
            release_region = np.arange(0, min(release_samples, num_samples - release_start))
            release_tau = release_samples / 4.0  # 释放时间常数稍快
            envelope[release_start:release_start + len(release_region)] = (
                sustain_level * np.exp(-release_region / release_tau)
            )

        # 最终归一化
        max_val = np.max(np.abs(envelope))
        if max_val > 0:
            envelope = envelope / max_val

        return envelope

    # --------------------------------------------------
    # 3. 频谱包络调制
    # --------------------------------------------------

    def apply_spectral_envelope(
        self,
        signal: np.ndarray,
        spectral_envelope: np.ndarray,
        sample_rate: int = 44100,
        n_fft: int = 2048
    ) -> np.ndarray:
        """
        对信号施加频谱包络调制。

        原理:
          1. 对原始波形做 FFT 得到频域表示
          2. 将频谱包络（频率->振幅的映射）插值到 FFT 频率 bins 上
          3. 用插值后的包络乘以频谱幅度
          4. IFFT 回到时域

        参数:
            signal:             原始波形数组
            spectral_envelope:  频谱包络数组 (numpy array)，值为各频率 bin 的振幅系数
                                其长度应等于 n_fft // 2 + 1 (即正频率部分)
            sample_rate:        采样率
            n_fft:              FFT 窗口大小

        返回:
            np.ndarray: 调制后的时域信号
        """
        from scipy.interpolate import interp1d

        # 用完整信号长度做 FFT，避免只处理前 n_fft 个采样导致静音段
        n_fft = max(n_fft, len(signal))

        # 做 FFT
        spectrum = np.fft.rfft(signal, n=n_fft)

        # 确保包络长度与 FFT 正频率 bin 数一致
        n_bins = len(spectrum)
        if len(spectral_envelope) != n_bins:
            # 线性插值到目标长度
            orig_freqs = np.linspace(0, sample_rate / 2, len(spectral_envelope))
            target_freqs = np.linspace(0, sample_rate / 2, n_bins)
            interp_func = interp1d(orig_freqs, spectral_envelope, kind='linear',
                                   fill_value='extrapolate')
            envelope_interp = interp_func(target_freqs)
            envelope_interp = np.clip(envelope_interp, 0.0, None)
        else:
            envelope_interp = spectral_envelope.copy()

        # 施加包络调制（复数频谱的幅度乘以包络，相位保持不变）
        modulated_spectrum = spectrum * envelope_interp

        # IFFT 回到时域
        output = np.fft.irfft(modulated_spectrum, n=n_fft)

        # 如果原始信号长度不等于 n_fft，截取对应部分
        if len(signal) < n_fft:
            output = output[:len(signal)]
        elif len(signal) > n_fft:
            output = np.pad(output, (0, len(signal) - n_fft), mode='constant')

        return output

    # --------------------------------------------------
    # 4. 完整合成流程
    # --------------------------------------------------

    def synthesize_note(
        self,
        frequency: float,
        duration: float,
        waveform_type: str = 'sine',
        adsr_params: Optional[dict] = None,
        spectral_envelope: Optional[np.ndarray] = None,
        amplitude: float = 1.0
    ) -> np.ndarray:
        """
        合成单个音符（完整流程: 波形生成 -> ADSR -> 频谱调制 -> 归一化）。

        参数:
            frequency:        音符基频 (Hz)
            duration:         音符时长 (秒)
            waveform_type:    基础波形类型
            adsr_params:      ADSR 参数字典，可选键: attack, decay, sustain_level, release
                              默认值: {'attack': 0.005, 'decay': 0.1, 'sustain_level': 0.6, 'release': 0.3}
            spectral_envelope: 频谱包络数组 (来自第一阶段提取)，若为 None 则不施加调制
            amplitude:        输出振幅系数

        返回:
            np.ndarray: 合成后的单声道浮点音频信号 [-1.0, 1.0]
        """
        # 默认 ADSR 参数（适合吉他拨弦）
        if adsr_params is None:
            adsr_params = {
                'attack': 0.005,
                'decay': 0.1,
                'sustain_level': 0.6,
                'release': 0.3
            }

        # Step 1: 生成基础波形
        signal = self.generate_waveform(
            frequency=frequency,
            duration=duration,
            waveform_type=waveform_type,
            amplitude=amplitude
        )

        # Step 2: 生成 ADSR 包络并施加
        adsr_env = self.generate_adsr_envelope(
            duration=duration,
            **adsr_params
        )
        signal = signal * adsr_env

        # Step 3: 频谱包络调制（如果提供了包络数据）
        if spectral_envelope is not None:
            signal = self.apply_spectral_envelope(
                signal=signal,
                spectral_envelope=spectral_envelope,
                sample_rate=self.sample_rate
            )

        # Step 4: 最终归一化
        max_val = np.max(np.abs(signal))
        if max_val > 1.0:
            signal = signal / max_val

        return signal

    # --------------------------------------------------
    # 5. 和弦合成（多音同时发声）
    # --------------------------------------------------

    def synthesize_chord(
        self,
        frequencies: list,
        duration: float,
        waveform_type: str = 'sine',
        adsr_params: Optional[dict] = None,
        spectral_envelope: Optional[np.ndarray] = None,
        amplitudes: Optional[list] = None
    ) -> np.ndarray:
        """
        合成和弦（多个音符叠加）。

        参数:
            frequencies:    各音符频率列表
            duration:       和弦时长 (秒)
            waveform_type:  基础波形类型
            adsr_params:    ADSR 参数
            spectral_envelope: 频谱包络
            amplitudes:     各音符振幅权重列表（默认等权）

        返回:
            np.ndarray: 合成和弦信号
        """
        if amplitudes is None:
            amplitudes = [1.0 / len(frequencies)] * len(frequencies)

        mixed_signal = np.zeros(int(duration * self.sample_rate))

        for freq, amp in zip(frequencies, amplitudes):
            note = self.synthesize_note(
                frequency=freq,
                duration=duration,
                waveform_type=waveform_type,
                adsr_params=adsr_params,
                spectral_envelope=spectral_envelope,
                amplitude=amp
            )
            # 截断或补零到统一长度
            target_len = len(mixed_signal)
            if len(note) < target_len:
                note = np.pad(note, (0, target_len - len(note)), mode='constant')
            elif len(note) > target_len:
                note = note[:target_len]
            mixed_signal += note

        # 和弦叠加容易溢出，需压缩动态范围
        max_val = np.max(np.abs(mixed_signal))
        if max_val > 1.0:
            mixed_signal = mixed_signal / max_val * 0.95  # 留 5% 余量

        return mixed_signal

    # --------------------------------------------------
    # 6. 吉他拨弦物理建模合成（与 simulated_guitar 一致）
    # --------------------------------------------------

    def synthesize_guitar_note(
        self,
        frequency: float,
        duration: float,
        attack: float = 0.005,
        decay: float = 0.35,
        sustain_level: float = 0.25,
        release: float = 0.15,
    ) -> np.ndarray:
        """
        模拟单根吉他弦的拨弦声音。

        与 scripts/generate_simulated_guitar.py 中 generate_guitar_note 一致：
        正弦基频 + 少量高次泛音 + 吉他 ADSR + 轻微频散，
        得到自然、不刺耳的拨弦音色。
        """
        t = np.arange(0, duration, 1.0 / self.sample_rate, dtype=np.float32)

        # 轻微频散，避免多个正弦波叠加后过于“纯音”
        freq_offset = frequency * 0.001
        phase = 2.0 * np.pi * (frequency + freq_offset) * t

        signal = np.sin(phase)
        # 加入少量高次谐波，模拟弦振动的泛音
        signal += 0.18 * np.sin(2.0 * phase)
        signal += 0.07 * np.sin(3.0 * phase)

        # ADSR 包络
        total_samples = len(t)
        attack_samples = max(1, int(attack * self.sample_rate))
        decay_samples = max(1, int(decay * self.sample_rate))
        release_samples = max(1, int(release * self.sample_rate))

        sustain_samples = total_samples - attack_samples - decay_samples - release_samples
        if sustain_samples < 0:
            sustain_samples = 0

        envelope = np.zeros(total_samples, dtype=np.float32)

        if attack_samples > 0:
            envelope[:attack_samples] = np.linspace(0.0, 1.0, attack_samples)

        decay_end = attack_samples + decay_samples
        if decay_samples > 0:
            envelope[attack_samples:decay_end] = np.linspace(
                1.0, sustain_level, decay_samples
            )

        sustain_end = decay_end + sustain_samples
        if sustain_samples > 0:
            envelope[decay_end:sustain_end] = sustain_level

        if release_samples > 0:
            release_start = max(decay_end, total_samples - release_samples)
            release_len = total_samples - release_start
            if release_len > 0:
                envelope[release_start:] = np.linspace(
                    sustain_level, 0.0, release_len
                )

        signal = signal * envelope

        # 归一化到 [-1, 1]
        peak = np.max(np.abs(signal))
        if peak > 0:
            signal = signal / peak

        return signal

    def synthesize_guitar_chord(
        self,
        frequencies: list,
        duration: float,
        strum_delay: float = 0.012,
    ) -> np.ndarray:
        """模拟吉他扫弦和弦：每根弦略微错开起音时间。"""
        chord_signal = np.zeros(int(duration * self.sample_rate), dtype=np.float32)

        for i, freq in enumerate(frequencies):
            note = self.synthesize_guitar_note(freq, duration)

            offset_samples = max(0, int(round(i * strum_delay * self.sample_rate)))

            if offset_samples >= len(chord_signal):
                continue

            end = offset_samples + len(note)
            if end > len(chord_signal):
                note = note[: len(chord_signal) - offset_samples]

            chord_signal[offset_samples: offset_samples + len(note)] += note

        # 多弦叠加后重新归一化，避免削波
        peak = np.max(np.abs(chord_signal))
        if peak > 0:
            chord_signal = chord_signal / peak

        return chord_signal

    # --------------------------------------------------
    # 6.5 Karplus-Strong 拨弦物理建模
    # --------------------------------------------------

    def synthesize_ks_note(
        self,
        frequency: float,
        duration: float,
        alpha: float = 0.7,
        rho: float = 0.997,
        ir: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        """
        Karplus-Strong (KS) 拨弦合成：延迟线 + 低通滤波 + 增益衰减。

        原理:
          - 延迟线长度 N = round(sample_rate / f0)，对应弦的基频周期
          - 激励: 白噪声（模拟拨弦瞬间的宽带激励），幅度衰减到 0.3 避免过载
          - 每采样一步: 输出延迟线当前值 -> 相邻两点加权平均（低通，模拟高频
            能量耗散）-> 乘以 rho（能量衰减）-> 反馈回延迟线末端
          - alpha 控制亮度（低通系数，越大越暗），rho 控制衰减长度（越接近 1 越长）
          - 可选 ir: 琴体脉冲响应卷积，模拟共鸣箱体音色

        参数:
            frequency: 基频 (Hz)
            duration:  时长 (秒)
            alpha:     低通系数 (0.0 ~ 1.0)，0.5 为经典平均滤波
            rho:       增益衰减系数 (0.0 ~ 1.0)，越接近 1 余音越长
            ir:        可选琴体脉冲响应数组，非 None 时用 FFT 卷积

        返回:
            np.ndarray: float32 单声道信号，长度 = int(duration * sample_rate)
        """
        if frequency <= 0:
            raise ValueError(f"频率必须为正: {frequency}")

        n_delay = max(2, int(round(self.sample_rate / frequency)))
        num_samples = int(duration * self.sample_rate)

        # 激励: 白噪声，幅度衰减到 0.3 避免过载
        rng = np.random.default_rng()
        delay = (rng.standard_normal(n_delay) * 0.3).astype(np.float32)

        output = np.zeros(num_samples, dtype=np.float32)

        # 索引式环形缓冲，每采样 O(1)，避免 np.roll 的 O(N) 开销
        idx = 0
        for i in range(num_samples):
            output[i] = delay[idx]

            next_idx = idx + 1
            if next_idx >= n_delay:
                next_idx = 0

            # 低通: 相邻两点加权平均，alpha 越大高频衰减越多（音色越暗）
            filtered = (1.0 - alpha) * delay[idx] + alpha * delay[next_idx]

            # 增益衰减后反馈回当前位置（覆盖已读出的值）
            delay[idx] = np.float32(rho * filtered)

            idx = next_idx

        # 可选: 琴体 IR 卷积（FFT 卷积，截断回原始长度）
        if ir is not None:
            from scipy.signal import fftconvolve
            output = fftconvolve(output, ir, mode='full')[:num_samples].astype(np.float32)

        # 归一化到 [-1, 1]
        peak = np.max(np.abs(output))
        if peak > 0:
            output = output / peak

        return output.astype(np.float32)

    def synthesize_ks_chord(
        self,
        frequencies: list,
        duration: float,
        strum_delay: float = 0.012,
        alpha: float = 0.7,
        rho: float = 0.997,
        ir: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        """
        Karplus-Strong 扫弦和弦：每根弦按 strum_delay 错开起音后叠加。

        参数:
            frequencies: 各弦基频列表
            duration:    时长 (秒)
            strum_delay: 扫弦错位间隔 (秒)
            alpha:       低通系数（亮度）
            rho:         增益衰减系数（余音长度）
            ir:          可选琴体脉冲响应（对混好的和弦整体卷积一次）

        返回:
            np.ndarray: float32 和弦信号，归一化到 ±0.9 防削波
        """
        chord_signal = np.zeros(int(duration * self.sample_rate), dtype=np.float32)

        for i, freq in enumerate(frequencies):
            # 每根弦单独合成（不在此处做琴体卷积）
            note = self.synthesize_ks_note(
                frequency=freq,
                duration=duration,
                alpha=alpha,
                rho=rho,
            )

            offset_samples = max(0, int(round(i * strum_delay * self.sample_rate)))
            if offset_samples >= len(chord_signal):
                continue

            end = offset_samples + len(note)
            if end > len(chord_signal):
                note = note[: len(chord_signal) - offset_samples]

            chord_signal[offset_samples: offset_samples + len(note)] += note

        # 琴体 IR 卷积：对混好的和弦整体应用一次（符合物理，避免逐弦固定梳状滤波）
        if ir is not None:
            from scipy.signal import fftconvolve
            n = len(chord_signal)
            chord_signal = fftconvolve(chord_signal, ir, mode='full')[:n].astype(np.float32)

        # 归一化到 ±0.9，防止削波
        peak = np.max(np.abs(chord_signal))
        if peak > 0:
            chord_signal = chord_signal / peak * 0.9

        return chord_signal.astype(np.float32)

    # --------------------------------------------------
    # 7. WAV 导出
    # --------------------------------------------------

    @staticmethod
    def export_wav(
        signal: np.ndarray,
        sample_rate: int = 44100,
        output_path: str = 'output_synthesized.wav',
        normalize: bool = True
    ) -> str:
        """
        将浮点信号导出为 16-bit PCM WAV 文件。

        参数:
            signal:      音频信号数组
            sample_rate: 采样率
            output_path: 输出文件路径
            normalize:   是否做 16-bit 归一化

        返回:
            str: 输出文件绝对路径
        """
        # 确保数据在 [-1, 1] 范围内
        if normalize:
            max_val = np.max(np.abs(signal))
            if max_val > 0:
                signal = signal / max_val

        # 转换为 16-bit PCM
        signal_int16 = (signal * 32767.0).astype(np.int16)

        # 写入 WAV
        wavfile.write(output_path, sample_rate, signal_int16)

        print(f"[Synthesizer] WAV 文件已导出: {output_path}")
        print(f"  - 采样率: {sample_rate} Hz")
        print(f"  - 位深: 16-bit PCM")
        print(f"  - 采样数: {len(signal_int16)}")
        print(f"  - 时长: {len(signal_int16) / sample_rate:.3f} s")

        return output_path


# --------------------------------------------------
# 便捷函数: 批量合成常用和弦
# --------------------------------------------------

def get_chord_frequencies(root_note: str, chord_type: str = 'major') -> list:
    """
    获取常用和弦的频率列表。

    参数:
        root_note:    根音 (如 'A', 'B', 'C', 'D', 'E', 'F', 'G')
        chord_type:   和弦类型 ('major' | 'minor' | '7' | 'maj7')

    返回:
        list: 频率列表 (Hz)，按从低到高排列
    """
    # 十二平均律: f = 440 * 2^(n/12), n 为距 A4 的半音数
    note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    note_to_semitones = {name: i for i, name in enumerate(note_names)}

    def note_freq(note_name, octave=4):
        """计算指定音名+八度的频率"""
        semitone = note_to_semitones[note_name]
        # A4 是第 69 号 MIDI 键 (C4=60, A4=69)
        midi_num = (octave + 1) * 12 + semitone
        return 440.0 * (2.0 ** ((midi_num - 69) / 12.0))

    # 根音半音偏移
    root_semitone = note_to_semitones[root_note]

    # 和弦音程结构 (以半音数表示)
    chord_intervals = {
        'major':  [0, 4, 7],        # 大三和弦: 根音, 大三度, 纯五度
        'minor':  [0, 3, 7],        # 小三和弦: 根音, 小三度, 纯五度
        '7':      [0, 4, 7, 10],    # 属七和弦: 根音, 大三度, 纯五度, 小七度
        'maj7':   [0, 4, 7, 11],    # 大七和弦: 根音, 大三度, 纯五度, 大七度
    }

    if chord_type not in chord_intervals:
        raise ValueError(f"不支持的和弦类型: {chord_type}")

    intervals = chord_intervals[chord_type]

    # 在吉他标准调弦 (E2 A2 D3 G3 B3 E4) 附近寻找合适的八度
    frequencies = []
    for interval in intervals:
        semitone_offset = root_semitone + interval
        octave = 3 + semitone_offset // 12
        note_idx = semitone_offset % 12
        note_name = note_names[note_idx]
        freq = note_freq(note_name, octave)
        frequencies.append(freq)

    return frequencies


# 预定义常用和弦频率表 (吉他标准调弦下的开放和弦)
CHORD_FREQUENCIES = {
    'A_minor':  get_chord_frequencies('A', 'minor'),
    'B_minor':  get_chord_frequencies('B', 'minor'),
    'C_major':  get_chord_frequencies('C', 'major'),
    'D_major':  get_chord_frequencies('D', 'major'),
    'E_major':  get_chord_frequencies('E', 'major'),
    'E_minor':  get_chord_frequencies('E', 'minor'),
    'A_major':  get_chord_frequencies('A', 'major'),
    'F_major':  get_chord_frequencies('F', 'major'),
    'G_major':  get_chord_frequencies('G', 'major'),
}

# 吉他标准调弦六根空弦 (EADGBE)，从低音弦到高音弦（即从第 6 弦到第 1 弦）
OPEN_STRING_FREQUENCIES = [
    82.4069,    # E2  第 6 弦（最粗，最低音）
    110.0000,   # A2  第 5 弦
    146.8324,   # D3  第 4 弦
    195.9977,   # G3  第 3 弦
    246.9417,   # B3  第 2 弦
    329.6276,   # E4  第 1 弦（最细，最高音）
]


# --------------------------------------------------
# 便捷函数: 生成合成脉冲响应 (占位 IR)
# --------------------------------------------------

def generate_synthetic_ir(
    duration: float = 0.004,
    sample_rate: int = 44100,
    n_modes: int = 16,
    f_min: float = 100.0,
    f_max: float = 1500.0,
    seed: int = 0,
) -> np.ndarray:
    """
    生成合成琴体脉冲响应 (IR)，短促低频暖色冲激。

    设计要点（只做"木头暖色"，不做长共鸣，避免"空灵/混响"质感）:
      - 极短时长 (默认 4ms)：只影响音头瞬间，不拖尾巴
      - 低频占优：振幅随频率快速下降，突出低频温暖感
      - 快速衰减：衰减率随频率上升（400~1200），模态在几毫秒内耗散
      - 随机相位：避免整齐谐波叠加产生固定音高环

    占位实现：后续可替换为真实吉他琴体录音的 IR。

    参数:
        duration:    IR 时长 (秒)，越短越不拖尾
        sample_rate: 采样率 (Hz)
        n_modes:     共振模态数量
        f_min:       最低共振频率 (Hz)
        f_max:       最高共振频率 (Hz)
        seed:        随机相位种子（保证可复现）

    返回:
        np.ndarray: float32 归一化 IR 数组，长度 = int(duration * sample_rate)
    """
    rng = np.random.default_rng(seed)

    # 密集模态频率，对数刻度均匀分布
    freqs = np.geomspace(f_min, f_max, n_modes)

    # 振幅随频率快速下降：低频占优，突出温暖感
    amplitudes = (freqs / f_min) ** -0.7

    # 衰减率随频率上升：高频更快衰减，整体快速耗散避免拖尾
    decays = 400.0 + (freqs - f_min) / (f_max - f_min) * 800.0  # 400 ~ 1200

    # 随机相位，避免整齐的谐波叠加
    phases = rng.uniform(0.0, 2.0 * np.pi, n_modes)

    n = int(duration * sample_rate)
    t = np.arange(n, dtype=np.float32) / sample_rate

    ir = np.zeros(n, dtype=np.float32)
    for f, d, a, p in zip(freqs, decays, amplitudes, phases):
        # 指数衰减正弦模态: a * exp(-d*t) * sin(2*pi*f*t + p)
        ir += (a * np.exp(-d * t) * np.sin(2.0 * np.pi * f * t + p)).astype(np.float32)

    # 归一化到 [-1, 1]
    peak = np.max(np.abs(ir))
    if peak > 0:
        ir = ir / peak

    return ir.astype(np.float32)


if __name__ == '__main__':
    # 快速测试: 合成一个 A4 正弦波并导出
    synth = Synthesizer(sample_rate=44100)
    note = synth.synthesize_note(
        frequency=440.0,
        duration=1.0,
        waveform_type='sine',
        adsr_params={'attack': 0.005, 'decay': 0.1, 'sustain_level': 0.6, 'release': 0.3}
    )
    synth.export_wav(note, sample_rate=44100, output_path='test_sine_a4.wav')
    print("测试完成!")