"""
用代码模拟生成吉他扫弦 WAV 文件。

用法示例：
    python generate_simulated_guitar.py
    python generate_simulated_guitar.py --chord A_minor --output assets/simulated_guitar_A_minor.wav
"""

import argparse
import os
import numpy as np
from scipy.io import wavfile


# 常见和弦基频，单位 Hz
CHORD_FREQUENCIES = {
    "A_minor": [220.00, 261.63, 329.63],       # A3, C4, E4
    "C_major": [261.63, 329.63, 392.00],        # C4, E4, G4
    "D_major": [293.66, 369.99, 440.00],        # D4, F#4, A4
    "E_major": [329.63, 415.30, 493.88],        # E4, G#4, B4
    "G_major": [196.00, 246.94, 329.63],        # G3, B3, E4
}


def generate_guitar_note(frequency: float,
                         duration: float,
                         fs: int,
                         attack: float = 0.005,
                         decay: float = 0.35,
                         sustain_level: float = 0.25,
                         release: float = 0.15) -> np.ndarray:
    """
    模拟单根吉他弦的拨弦声音。

    这里用正弦波 + ADSR 包络 + 轻微频率偏移来模拟拨弦瞬态和自然衰减。
    """
    t = np.arange(0, duration, 1.0 / fs, dtype=np.float32)

    # 轻微频散，避免多个正弦波叠加后过于“纯音”
    freq_offset = frequency * 0.001
    phase = 2.0 * np.pi * (frequency + freq_offset) * t

    signal = np.sin(phase)

    # 加入少量高次谐波，模拟弦振动的泛音
    signal += 0.18 * np.sin(2.0 * phase)
    signal += 0.07 * np.sin(3.0 * phase)

    # ADSR 包络
    total_samples = len(t)
    attack_samples = max(1, int(attack * fs))
    decay_samples = max(1, int(decay * fs))
    release_samples = max(1, int(release * fs))

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
            envelope[release_start:] = np.linspace(sustain_level, 0.0, release_len)

    signal = signal * envelope

    # 归一化到 [-1, 1]
    peak = np.max(np.abs(signal))
    if peak > 0:
        signal = signal / peak

    return signal


def generate_chord(frequencies: list[float],
                   duration: float,
                   fs: int,
                   strum_delay: float = 0.012) -> np.ndarray:
    """
    模拟吉他扫弦：每根弦略微错开起音时间。
    """
    chord_signal = np.zeros(int(duration * fs), dtype=np.float32)

    for i, freq in enumerate(frequencies):
        note = generate_guitar_note(freq, duration, fs)

        offset_samples = int(round(i * strum_delay * fs))
        offset_samples = max(0, offset_samples)

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


def save_wav_float32(path: str, audio: np.ndarray, fs: int):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    # 转换为 16-bit PCM
    audio_int16 = np.clip(audio, -1.0, 1.0)
    audio_int16 = (audio_int16 * 32767).astype(np.int16)

    wavfile.write(path, fs, audio_int16)
    print(f"✅ 模拟吉他 WAV 已生成: {path}")


def main():
    parser = argparse.ArgumentParser(
        description="用代码模拟生成吉他扫弦 WAV 文件"
    )
    parser.add_argument(
        "--chord",
        type=str,
        default="A_minor",
        choices=list(CHORD_FREQUENCIES.keys()),
        help="选择和弦",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=3.0,
        help="音频时长，单位秒",
    )
    parser.add_argument(
        "--fs",
        type=int,
        default=44100,
        help="采样率",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="assets/simulated_guitar_A_minor.wav",
        help="输出 WAV 路径",
    )
    args = parser.parse_args()

    frequencies = CHORD_FREQUENCIES[args.chord]
    print(f"🎸 模拟和弦: {args.chord}")
    print(f"   频率: {frequencies}")
    print(f"   时长: {args.duration}s, 采样率: {args.fs}Hz")

    audio = generate_chord(
        frequencies=frequencies,
        duration=args.duration,
        fs=args.fs,
    )

    save_wav_float32(args.output, audio, args.fs)


if __name__ == "__main__":
    main()