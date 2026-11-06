"""按用户推算的 62.5 BPM 时间表生成《安和桥》精确和弦时间线
========================================================
每个和弦持续 1 小节（4 拍 = 3.84s）。时间以第一个和弦（前奏 G）为 0.0s。
"""
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import config

# 简化和弦 → 引擎和弦名
CHORD_MAP = {'G': 'G_major', 'D': 'D_major', 'Em': 'E_minor', 'C': 'C_major'}

# (开始秒数, 简化和弦) —— 按用户功能谱推算
DATA = [
    # 前奏
    (0.0, 'G'), (3.8, 'D'), (7.7, 'Em'), (11.5, 'C'), (15.4, 'D'), (19.2, 'G'),
    # 主歌 A
    (23.0, 'G'), (26.9, 'D'), (30.7, 'Em'), (34.6, 'C'), (38.4, 'D'), (42.2, 'G'),
    (46.1, 'G'), (49.9, 'D'), (53.8, 'Em'), (57.6, 'C'), (61.4, 'D'), (65.3, 'Em'),
    # 副歌 A
    (69.1, 'C'), (73.0, 'D'), (76.8, 'Em'), (80.6, 'D'), (84.5, 'C'), (88.3, 'D'),
    (92.2, 'G'), (96.0, 'C'), (99.8, 'D'), (103.7, 'Em'), (107.5, 'D'), (111.4, 'C'),
    (115.2, 'D'), (119.0, 'Em'),
    # 主歌 B
    (122.9, 'G'), (126.7, 'D'), (130.6, 'Em'), (134.4, 'C'), (138.2, 'D'), (142.1, 'G'),
    (145.9, 'G'), (149.8, 'D'), (153.6, 'Em'), (157.4, 'C'), (161.3, 'D'), (165.1, 'Em'),
    # 间奏
    (168.9, 'C'), (172.8, 'D'), (176.6, 'Em'), (180.4, 'C'), (184.3, 'D'), (188.1, 'Em'),
    # 副歌 B / 结尾
    (192.0, 'C'), (195.8, 'D'), (199.6, 'Em'), (203.5, 'D'), (207.3, 'C'), (211.2, 'D'),
    (215.0, 'G'), (218.8, 'C'), (222.7, 'D'), (226.5, 'Em'), (230.4, 'D'), (234.2, 'C'),
    (238.0, 'D'), (241.9, 'Em'),
]

BEAT = 60.0 / 62.5   # 0.96s
BAR = 4 * BEAT       # 3.84s


def main():
    segments = []
    for i, (t, c) in enumerate(DATA):
        end = DATA[i + 1][0] if i + 1 < len(DATA) else t + BAR
        segments.append({'start': round(t, 1), 'end': round(end, 1),
                         'chord': CHORD_MAP[c]})

    out = {'file': '宋冬野 - 安和桥.wav', 'sample_rate': config.SAMPLE_RATE,
           'tempo_bpm': 62.5, 'chord_segments': segments}
    out_path = os.path.join(config.BASE_DIR, 'assets', 'charts', '安和桥_timeline.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print('段数:', len(segments), '| 总长:', round(segments[-1]['end'], 1), 's')
    print('已保存:', out_path)


if __name__ == '__main__':
    main()
