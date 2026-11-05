"""生成示例曲谱 assets/charts/*.json
=====================================
按 BPM + 和弦进行 + 节拍模板生成三首示例曲谱，供音序器自动演奏使用。

用法：
    python scripts/generate_charts.py
"""
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import config

# 每首曲目：BPM + 4 小节循环的和弦进行
SONGS = {
    '星空': {
        'bpm': 120,
        'progression': ['C_major', 'G_major', 'A_minor', 'F_major'],
    },
    '河流': {
        'bpm': 96,
        'progression': ['A_minor', 'F_major', 'C_major', 'G_major'],
    },
    '森林': {
        'bpm': 140,
        'progression': ['G_major', 'E_major', 'C_major', 'D_major'],
    },
}

BARS = 8  # 每首 8 小节


def make_chart(name):
    bpm = SONGS[name]['bpm']
    prog = SONGS[name]['progression']
    beat_s = 60.0 / bpm
    events = []

    for bar in range(BARS):
        chord = prog[bar % len(prog)]
        # 每拍一次下扫
        for beat in range(4):
            t_ms = round((bar * 4 + beat) * beat_s * 1000)
            events.append({'time_ms': t_ms, 'type': 'strum', 'chord': chord,
                           'direction': 'down', 'velocity': 0.7})
        # 第 2、4 拍后半拍上扫（八分音符切分）
        for off in (1.5, 3.5):
            t_ms = round((bar * 4 + off) * beat_s * 1000)
            events.append({'time_ms': t_ms, 'type': 'strum', 'chord': chord,
                           'direction': 'up', 'velocity': 0.45})

    # 结尾制音
    end_ms = round(BARS * 4 * beat_s * 1000)
    events.append({'time_ms': end_ms, 'type': 'mute', 'chord': prog[(BARS - 1) % len(prog)]})

    return {'name': name, 'bpm': bpm, 'events': events}


def main():
    out_dir = os.path.join(config.ASSETS_DIR, 'charts')
    os.makedirs(out_dir, exist_ok=True)
    for name in SONGS:
        path = os.path.join(out_dir, f'{name}.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(make_chart(name), f, ensure_ascii=False, indent=2)
        print('生成', path)


if __name__ == '__main__':
    main()
