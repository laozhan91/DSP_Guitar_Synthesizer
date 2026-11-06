"""从真实吉他录音设计「吉他音色」FIR 滤波器
============================================
对纯吉他版安和桥的平均频谱做对数平滑，得到目标频谱包络，
用 firwin2 设计线性相位 FIR，存到 assets/guitar_tone.npy，
流式合成时卷积，使 KS 输出更像真实吉他。

用法：python scripts/build_guitar_tone.py
"""
import os
import sys

import numpy as np
from scipy.io import wavfile
from scipy.signal import firwin2, freqz

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import config


def main():
    bgm = os.path.join(config.BASE_DIR, 'assets', 'BGM')
    wavs = [f for f in os.listdir(bgm) if f.lower().endswith('.wav')]
    path = os.path.join(bgm, [f for f in wavs if '宋冬野' not in f][0])
    sr, data = wavfile.read(path)
    mono = data.mean(axis=1).astype(np.float32) / 32768.0

    # 平均幅度谱
    n = 8192
    hop = 2048
    win = np.hanning(n)
    acc = np.zeros(n // 2 + 1)
    cnt = 0
    for i in range(0, int(30 * sr), hop):
        if i + n > len(mono):
            break
        seg = mono[i:i + n]
        if np.sqrt(np.mean(seg ** 2)) < 0.02:
            continue
        acc += np.abs(np.fft.rfft(seg * win))
        cnt += 1
    acc /= max(1, cnt)
    freqs = np.fft.rfftfreq(n, 1.0 / sr)

    # 对数平滑，得到目标频谱包络
    fmin, fmax = 60.0, 8000.0
    f_log = np.geomspace(fmin, fmax, 48)
    m_log = np.interp(f_log, freqs, acc)
    m_norm = m_log / m_log.max()
    m_norm = np.maximum(m_norm, 0.02)  # 防止无限衰减引起振铃

    # 设计线性相位 FIR（频率轴 0~fs/2，归一化 0~1）
    numtaps = 256
    bands = np.concatenate(([0.0], f_log / (sr / 2), [1.0]))
    gains = np.concatenate(([m_norm[0]], m_norm, [0.0]))
    b = firwin2(numtaps, bands, gains, window='hamming')

    # 归一化：让峰值响应为 0dB，避免整体音量被压低
    w, h = freqz(b, worN=8192)
    b = b / np.max(np.abs(h))
    w, h = freqz(b, worN=8192)
    f = w / np.pi * sr / 2
    print('设计后的 FIR 频率响应：')
    for target in (100, 300, 500, 1000, 2000, 4000, 8000):
        idx = int(np.argmin(np.abs(f - target)))
        print(f'  {target:5d}Hz  {20 * np.log10(abs(h[idx]) + 1e-9):6.1f} dB')

    out = os.path.join(config.ASSETS_DIR, 'guitar_tone.npy')
    np.save(out, b.astype(np.float32))
    print('已保存:', out, '| taps:', len(b))


if __name__ == '__main__':
    main()
