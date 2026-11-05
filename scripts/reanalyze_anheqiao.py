"""重新提取《宋冬野 - 安和桥》的和弦时间线（限定 G/D/Em/C 四个和弦）
====================================================================
用法：python scripts/reanalyze_anheqiao.py
输出：assets/charts/安和桥_timeline.json（chord_segments: [{start,end,chord}]）
"""
import json
import os
import sys

import numpy as np
from scipy.io import wavfile

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import config

# A-based 音级：A=0 A#=1 B=2 C=3 C#=4 D=5 D#=6 E=7 F=8 F#=9 G=10 G#=11
CHORD_TONES = {
    'G_major': [10, 2, 5],
    'D_major': [5, 9, 0],
    'E_minor': [7, 10, 2],
    'C_major': [3, 7, 10],
}


def load_mono(path):
    sr, data = wavfile.read(path)
    if data.ndim == 2:
        mono = data.astype(np.float32).mean(axis=1)
    else:
        mono = data.astype(np.float32)
    if data.dtype == np.int16:
        mono /= 32768.0
    return sr, mono


def chromagram(mono, sr, frame=16384, hop=8192):
    freqs = np.fft.rfftfreq(frame, 1.0 / sr)
    n_frames = 1 + (len(mono) - frame) // hop
    chroma = np.zeros((12, n_frames), dtype=np.float64)
    win = np.hanning(frame).astype(np.float32)
    for i in range(n_frames):
        seg = mono[i * hop:i * hop + frame] * win
        spec = np.abs(np.fft.rfft(seg))
        mask = (freqs >= 80.0) & (freqs <= 5000.0)
        f = freqs[mask]
        s = spec[mask]
        pc = np.mod(np.round(12.0 * np.log2(f / 440.0)).astype(int), 12)
        for c in range(12):
            chroma[c, i] = float(np.sum(s[pc == c]))
    norm = np.linalg.norm(chroma, axis=0)
    norm[norm < 1e-9] = 1.0
    chroma /= norm[None, :]
    return chroma


def build_templates():
    templates = {}
    for name, tones in CHORD_TONES.items():
        t = np.zeros(12, dtype=np.float64)
        for pc in tones:
            t[pc] = 1.0
        templates[name] = t / np.linalg.norm(t)
    return templates


def main():
    bgm_dir = os.path.join(config.BASE_DIR, 'assets', 'BGM')
    path = os.path.join(bgm_dir, '宋冬野 - 安和桥.wav')
    sr, mono = load_mono(path)
    chroma = chromagram(mono, sr)
    templates = build_templates()

    # 按 ~1 拍(约0.93s)对 chroma 求均值，降低人声/鼓点干扰
    avg = 5
    n_avg = chroma.shape[1] // avg
    chroma_avg = chroma[:, :n_avg * avg].reshape(12, n_avg, avg).mean(axis=2)

    n = chroma_avg.shape[1]
    labels = []
    for i in range(n):
        c = chroma_avg[:, i]
        best, bs = None, -1.0
        for name, t in templates.items():
            s = float(np.dot(c, t))
            if s > bs:
                bs, best = s, name
        labels.append(best)

    radius = 1  # 已按拍平均，轻度平滑即可
    smoothed = []
    for i in range(n):
        lo, hi = max(0, i - radius), min(n, i + radius + 1)
        seg = labels[lo:hi]
        smoothed.append(max(set(seg), key=seg.count))

    frame_time = 8192 / sr * avg
    segs = []
    cur, start = smoothed[0], 0
    for i in range(1, len(smoothed)):
        if smoothed[i] != cur:
            segs.append({'start': round(start * frame_time, 2),
                         'end': round(i * frame_time, 2), 'chord': cur})
            cur, start = smoothed[i], i
    segs.append({'start': round(start * frame_time, 2),
                 'end': round(len(smoothed) * frame_time, 2), 'chord': cur})

    merged = []
    for s in segs:
        if merged and (s['end'] - s['start'] < 1.2):
            merged[-1]['end'] = s['end']
        else:
            merged.append(s)

    out = {'file': os.path.basename(path), 'sample_rate': sr,
           'chord_segments': merged}
    out_path = os.path.join(config.BASE_DIR, 'assets', 'charts', '安和桥_timeline.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print('段数:', len(merged))
    for s in merged[:60]:
        print(f"  {s['start']:6.1f}-{s['end']:6.1f}  {s['chord']}")
    print('已保存:', out_path)


if __name__ == '__main__':
    main()
