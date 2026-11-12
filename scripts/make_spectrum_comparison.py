"""生成「真实吉他 vs KS 合成」频谱对比图
============================================
对纯吉他版安和桥和 KS 合成的 G_major 和弦（含音色 FIR）求平均幅度谱，
画归一化 dB 对比图，存到 assets/spectrum_comparison.png。
"""
import os
import sys

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.io import wavfile
from scipy.signal import lfilter

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import config
from dsp_guitar_core.synthesizer import Synthesizer, CHORD_FREQUENCIES


def avg_spectrum_db(signal, sr, n=8192, hop=2048, seconds=None):
    if seconds is not None:
        signal = signal[: int(seconds * sr)]
    win = np.hanning(n)
    acc = np.zeros(n // 2 + 1)
    cnt = 0
    for i in range(0, len(signal) - n, hop):
        seg = signal[i:i + n]
        if np.sqrt(np.mean(seg ** 2)) < 1e-4:
            continue
        acc += np.abs(np.fft.rfft(seg * win))
        cnt += 1
    acc /= max(1, cnt)
    freqs = np.fft.rfftfreq(n, 1.0 / sr)
    # 对数平滑
    f_log = np.geomspace(60.0, 8000.0, 96)
    m_log = np.interp(f_log, freqs, acc)
    m_log /= max(1e-9, m_log.max())
    return f_log, 20.0 * np.log10(m_log + 1e-9)


def main():
    bgm = os.path.join(config.BASE_DIR, 'assets', 'BGM')
    wavs = [f for f in os.listdir(bgm) if f.lower().endswith('.wav')]
    path = os.path.join(bgm, [f for f in wavs if '宋冬野' not in f][0])
    sr, data = wavfile.read(path)
    real = data.mean(axis=1).astype(np.float32) / 32768.0

    synth = Synthesizer(sample_rate=config.SAMPLE_RATE)
    ks = synth.synthesize_ks_chord(
        CHORD_FREQUENCIES['G_major'], duration=3.0, alpha=0.7, rho=0.997)

    # 应用吉他音色 FIR（与流式引擎保持一致）
    tone_path = os.path.join(config.ASSETS_DIR, 'guitar_tone.npy')
    if os.path.isfile(tone_path):
        tone = np.load(tone_path).astype(np.float64)
        ks = lfilter(tone, [1.0], ks).astype(np.float32)

    fr, real_db = avg_spectrum_db(real, sr, seconds=20)
    fk, ks_db = avg_spectrum_db(ks, config.SAMPLE_RATE)

    plt.figure(figsize=(8, 4.5))
    plt.plot(fr, real_db, label='Real guitar', lw=2)
    plt.plot(fk, ks_db, label='KS synth (with tone FIR)', lw=2)
    plt.xscale('log')
    plt.xlim(60, 8000)
    plt.ylim(-70, 5)
    plt.xlabel('Frequency (Hz)')
    plt.ylabel('Magnitude (dB, normalized)')
    plt.title('Real guitar vs KS synthesized spectrum')
    plt.grid(True, which='both', alpha=0.3)
    plt.legend()
    plt.tight_layout()
    out = os.path.join(config.ASSETS_DIR, 'spectrum_comparison.png')
    plt.savefig(out, dpi=130)
    print('saved:', out)


if __name__ == '__main__':
    main()
