"""分析吉他伴奏：提取和弦进行与扫弦节奏（前 60 秒）
==================================================
用法：python scripts/analyze_bgm.py
输出：和弦分段 + 扫弦 onset 时间 + 估计 BPM，并保存 JSON 到 assets/charts/bgm_analysis.json
"""
import json
import os
import sys

import numpy as np
from scipy.io import wavfile
from scipy.signal import find_peaks

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import config

NOTE_NAMES = ['A', 'A#', 'B', 'C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#']
LIMIT_SECONDS = 60.0


def load_mono(path, limit_seconds):
    sr, data = wavfile.read(path)
    n = int(sr * limit_seconds)
    data = data[:n]
    if data.ndim == 2:
        mono = data.astype(np.float32).mean(axis=1)
    else:
        mono = data.astype(np.float32)
    if data.dtype == np.int16:
        mono /= 32768.0
    return sr, mono


def chromagram(mono, sr, frame=8192, hop=4096):
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
    intervals = {'major': [0, 4, 7], 'minor': [0, 3, 7]}
    templates = {}
    for r in range(12):
        for ct, ivs in intervals.items():
            t = np.zeros(12, dtype=np.float64)
            for iv in ivs:
                t[(r + iv) % 12] = 1.0
            name = f'{NOTE_NAMES[r]}_{ct}'
            templates[name] = t / np.linalg.norm(t)
    return templates


def estimate_chords(chroma, templates, radius=3):
    n = chroma.shape[1]
    labels, scores = [], []
    for i in range(n):
        c = chroma[:, i]
        best, bs = None, -1.0
        for name, t in templates.items():
            s = float(np.dot(c, t))
            if s > bs:
                bs, best = s, name
        labels.append(best)
        scores.append(bs)
    smoothed = []
    for i in range(n):
        lo, hi = max(0, i - radius), min(n, i + radius + 1)
        seg = labels[lo:hi]
        smoothed.append(max(set(seg), key=seg.count))
    return labels, scores, smoothed


def group_segments(labels, frame_time):
    segs = []
    cur, start = labels[0], 0
    for i in range(1, len(labels)):
        if labels[i] != cur:
            segs.append((start * frame_time, i * frame_time, cur))
            cur, start = labels[i], i
    segs.append((start * frame_time, len(labels) * frame_time, cur))
    return segs


def merge_short(segs, min_dur=0.8):
    """把过短的段并入前一段，减少抖动"""
    if not segs:
        return segs
    out = [[segs[0][0], segs[0][1], segs[0][2]]]
    for s, e, c in segs[1:]:
        if e - s < min_dur:
            out[-1][1] = e
        else:
            out.append([s, e, c])
    return [(s, e, c) for s, e, c in out]


def onset_times(mono, sr, frame=1024, hop=512):
    n_frames = 1 + (len(mono) - frame) // hop
    win = np.hanning(frame).astype(np.float32)
    prev = None
    flux = []
    for i in range(n_frames):
        seg = mono[i * hop:i * hop + frame] * win
        spec = np.abs(np.fft.rfft(seg))
        if prev is not None:
            flux.append(float(np.sum(np.maximum(spec - prev, 0))))
        prev = spec
    flux = np.array(flux)
    if flux.max() > 0:
        flux /= flux.max()
    peaks, _ = find_peaks(flux, height=0.15, distance=max(1, int(0.06 * sr / hop)))
    times = peaks * hop / sr
    return times, flux


def estimate_tempo(flux, sr, hop):
    """对 onset 通量做自相关估计速度 (BPM)"""
    if flux.max() > 0:
        flux = flux / flux.max()
    ac = np.correlate(flux, flux, 'full')[len(flux) - 1:]
    min_lag = max(1, int(0.25 * sr / hop))
    max_lag = min(len(ac) - 1, int(2.0 * sr / hop))
    if max_lag <= min_lag:
        return None
    seg = ac[min_lag:max_lag + 1]
    lag = int(np.argmax(seg)) + min_lag
    period_s = lag * hop / sr
    return 60.0 / period_s, period_s


def main():
    bgm_dir = os.path.join(config.BASE_DIR, 'assets', 'BGM')
    files = [f for f in os.listdir(bgm_dir) if f.lower().endswith('.wav')]
    if not files:
        print('未找到 BGM wav')
        return
    path = os.path.join(bgm_dir, files[0])
    print('分析:', os.path.basename(path))
    sr, mono = load_mono(path, LIMIT_SECONDS)
    print(f'采样率 {sr}, 前 {LIMIT_SECONDS}s, 样本 {len(mono)}')

    chroma = chromagram(mono, sr, frame=16384, hop=8192)
    templates = build_templates()
    labels, scores, smoothed = estimate_chords(chroma, templates, radius=4)
    segs = group_segments(smoothed, frame_time=8192 / sr)
    segs = merge_short(segs, min_dur=0.8)
    print('\n== 和弦分段（前60s）==')
    for s, e, c in segs:
        print(f'  {s:6.1f}s - {e:6.1f}s  {c}')

    times, flux = onset_times(mono, sr)
    print(f'\n== 扫弦 onset 数量: {len(times)} ==')
    if len(times):
        print('前 20 个 onset 时间(s):', np.round(times[:20], 2).tolist())
    tempo = estimate_tempo(flux, sr, 512)
    if tempo:
        print(f'估计速度: {tempo[0]:.0f} BPM (周期 {tempo[1]:.2f}s)')

    # 和弦直方图（各和弦总时长，用于确定主和弦进行）
    hist = {}
    for s, e, c in segs:
        hist[c] = hist.get(c, 0.0) + (e - s)
    top = sorted(hist.items(), key=lambda kv: -kv[1])
    print('\n== 主和弦（按时长排序）==')
    for name, dur in top[:10]:
        print(f'  {name:10s} {dur:6.1f}s')

    out = {
        'file': os.path.basename(path),
        'sample_rate': sr,
        'tempo_bpm': round(tempo[0], 1) if tempo else None,
        'chord_segments': [{'start': float(s), 'end': float(e), 'chord': c} for s, e, c in segs],
        'top_chords': [(c, round(d, 1)) for c, d in top[:10]],
        'onsets': [round(float(t), 3) for t in times[:500]],
    }
    out_path = os.path.join(config.BASE_DIR, 'assets', 'charts', 'bgm_analysis.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print('已保存:', out_path)


if __name__ == '__main__':
    main()
