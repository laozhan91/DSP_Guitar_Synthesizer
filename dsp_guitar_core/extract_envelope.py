"""
第一阶段：从真实吉他扫弦 WAV 中提取频谱包络，并保存为 assets/guitar_envelope_data.npy

用法示例：
    python extract_envelope.py
    python extract_envelope.py --input assets/guitar-chord-in-a-minor.wav
    python extract_envelope.py --input assets/guitar-chord-in-a-minor.wav --output assets/guitar_envelope_data.npy
"""

import argparse
import os
import numpy as np
from scipy.io import wavfile
from scipy.signal import find_peaks
from scipy.interpolate import interp1d


def load_wav_mono_float32(path: str):
    """读取 WAV，统一转换为单声道 float32，幅度归一化到 [-1, 1]。"""
    fs, data = wavfile.read(path)

    if data.ndim == 2:
        # 立体声取平均合并为单声道
        data = data.mean(axis=1)

    # 统一转换为 float32
    if data.dtype == np.float32:
        audio = data
    elif data.dtype == np.float64:
        audio = data.astype(np.float32)
    else:
        # int16 / int32 等整型 PCM
        max_val = np.iinfo(data.dtype).max
        audio = data.astype(np.float32) / max_val

    # 避免全零导致后续归一化异常
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak

    return fs, audio


def extract_sustain_segment(audio: np.ndarray, fs: int,
                            start_sec: float = 0.5,
                            end_sec: float = 1.5) -> np.ndarray:
    """截取延音段，避开拨弦 Attack 瞬态。"""
    start_sample = int(round(start_sec * fs))
    end_sample = int(round(end_sec * fs))

    start_sample = max(0, start_sample)
    end_sample = min(len(audio), end_sample)

    if end_sample <= start_sample:
        raise ValueError(
            f"截取区间无效: start_sec={start_sec}, end_sec={end_sec}, "
            f"音频总长度={len(audio) / fs:.3f}s"
        )

    return audio[start_sample:end_sample]


def compute_spectral_envelope(audio: np.ndarray,
                              fs: int,
                              n_fft: int = 4096,
                              max_freq: float = 8000.0,
                              n_peaks: int = 120,
                              smooth_window: int = 51) -> dict:
    """
    从延音段音频中提取频谱包络。

    流程：
    1. 去直流
    2. 加 Hann 窗
    3. 计算幅度谱
    4. 峰值检测
    5. 三次插值平滑得到连续包络
    """
    # 1. 去直流
    signal = audio - np.mean(audio)

    # 2. 加窗，抑制频谱泄漏
    window = np.hanning(len(signal))
    windowed = signal * window

    # 3. FFT
    spectrum = np.fft.rfft(windowed, n=n_fft)
    magnitude = np.abs(spectrum)
    freqs = np.fft.rfftfreq(n_fft, d=1.0 / fs)

    # 只保留有效频段
    valid_mask = freqs <= max_freq
    freqs = freqs[valid_mask]
    magnitude = magnitude[valid_mask]

    if len(freqs) < 3:
        raise ValueError("有效频点过少，无法提取频谱包络。")

    # 4. 峰值检测
    min_distance = max(3, n_fft // (2 * int(max_freq)))
    peak_indices, _ = find_peaks(
        magnitude,
        distance=min_distance,
        prominence=np.max(magnitude) * 0.02,
    )

    # 如果峰值太少，回退为均匀采样
    if len(peak_indices) < 4:
        step = max(1, len(freqs) // n_peaks)
        peak_indices = np.arange(0, len(freqs), step)

    peak_freqs = freqs[peak_indices]
    peak_mags = magnitude[peak_indices]

    # 5. 插值平滑，得到连续频谱包络
    interp_func = interp1d(
        peak_freqs,
        peak_mags,
        kind="cubic",
        fill_value="extrapolate",
    )

    envelope_freqs = np.linspace(0.0, max_freq, n_peaks)
    envelope_mags = interp_func(envelope_freqs)

    # 包络归一化，方便第二阶段作为相对增益系数使用
    max_mag = np.max(envelope_mags)
    if max_mag > 0:
        envelope_mags = envelope_mags / max_mag

    return {
        "fs": fs,
        "n_fft": n_fft,
        "max_freq": max_freq,
        "n_peaks": n_peaks,
        "envelope_freqs": envelope_freqs,
        "envelope_mags": envelope_mags,
        "peak_freqs": peak_freqs,
        "peak_mags": peak_mags,
    }


def save_envelope_data(envelope_data: dict, output_path: str):
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    np.save(output_path, envelope_data)
    print(f"✅ 频谱包络已保存至: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="从真实吉他扫弦 WAV 中提取频谱包络"
    )
    parser.add_argument(
        "--input",
        type=str,
        default="assets/guitar-chord-in-a-minor.wav",
        help="输入吉他 WAV 文件路径",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="assets/guitar_envelope_data.npy",
        help="输出包络数据 npy 路径",
    )
    parser.add_argument(
        "--start-sec",
        type=float,
        default=0.5,
        help="延音段起始时间（秒）",
    )
    parser.add_argument(
        "--end-sec",
        type=float,
        default=1.5,
        help="延音段结束时间（秒）",
    )
    parser.add_argument(
        "--n-fft",
        type=int,
        default=4096,
        help="FFT 点数",
    )
    parser.add_argument(
        "--max-freq",
        type=float,
        default=8000.0,
        help="包络最高频率 Hz",
    )
    parser.add_argument(
        "--n-peaks",
        type=int,
        default=120,
        help="包络频点数量",
    )
    args = parser.parse_args()

    if not os.path.isfile(args.input):
        raise FileNotFoundError(f"输入音频不存在: {args.input}")

    print(f"🎸 读取音频: {args.input}")
    fs, audio = load_wav_mono_float32(args.input)
    print(f"   采样率: {fs} Hz, 音频长度: {len(audio) / fs:.3f}s")

    print(
        f"✂️  截取延音段: {args.start_sec}s - {args.end_sec}s"
    )
    sustain = extract_sustain_segment(
        audio, fs, start_sec=args.start_sec, end_sec=args.end_sec
    )
    print(f"   延音段长度: {len(sustain) / fs:.3f}s")

    print("🔍 提取频谱包络...")
    envelope_data = compute_spectral_envelope(
        sustain,
        fs=fs,
        n_fft=args.n_fft,
        max_freq=args.max_freq,
        n_peaks=args.n_peaks,
    )

    save_envelope_data(envelope_data, args.output)

    print(f"   包络频点数: {len(envelope_data['envelope_freqs'])}")
    print(f"   频率范围: 0 - {envelope_data['max_freq']} Hz")
    print("✅ 第一阶段包络提取完成，可进入第二阶段合成器搭建。")


if __name__ == "__main__":
    main()