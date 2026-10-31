
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
    # 6. WAV 导出
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
    'F_major':  get_chord_frequencies('F', 'major'),
    'G_major':  get_chord_frequencies('G', 'major'),
}


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