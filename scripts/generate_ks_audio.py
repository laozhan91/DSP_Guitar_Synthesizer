"""
generate_ks_audio.py - Karplus-Strong 拨弦合成音频生成脚本
===========================================================
功能：
  1. 使用 Karplus-Strong 算法合成目标吉他和弦
  2. 导出 WAV 到 assets/synthesized/ks_<chord>.wav
  3. 与 assets/simulated_guitar_A_minor.wav 做 A/B 听感对比

使用方式：
  python generate_ks_audio.py                        # 默认合成 A_minor
  python generate_ks_audio.py --chord C_major
  python generate_ks_audio.py --alpha 0.4 --rho 0.995   # 调参

调参经验值：
  alpha (亮度):   0.3 ~ 0.7，越大越暗（高频衰减越快）
  rho   (余音):   0.99 ~ 0.999，越接近 1 余音越长
"""

import os
import sys
import argparse

import numpy as np

# 确保项目根目录在路径中
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

import config
from dsp_guitar_core.synthesizer import (
    Synthesizer,
    CHORD_FREQUENCIES,
    generate_synthetic_ir,
)


def main():
    parser = argparse.ArgumentParser(
        description="Karplus-Strong 吉他拨弦合成"
    )
    parser.add_argument(
        "--chord",
        type=str,
        default="A_minor",
        choices=list(CHORD_FREQUENCIES.keys()),
        help="和弦名称",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=3.0,
        help="音频时长（秒）",
    )
    parser.add_argument(
        "--alpha",
        type=float,
        default=0.7,
        help="低通系数（亮度），越大越暗",
    )
    parser.add_argument(
        "--rho",
        type=float,
        default=0.997,
        help="增益衰减系数（余音长度），越接近 1 越长",
    )
    parser.add_argument(
        "--ir",
        action="store_true",
        help="启用合成琴体 IR 卷积（指数衰减正弦占位）",
    )
    args = parser.parse_args()

    synth = Synthesizer(sample_rate=config.SAMPLE_RATE)
    frequencies = CHORD_FREQUENCIES[args.chord]

    print(f"\n[KS] 合成和弦: {args.chord}")
    print(f"  - 频率: {frequencies}")
    print(f"  - 时长: {args.duration}s")
    print(f"  - alpha (亮度): {args.alpha}")
    print(f"  - rho   (余音): {args.rho}")

    # 可选琴体 IR 卷积
    ir = generate_synthetic_ir(sample_rate=config.SAMPLE_RATE) if args.ir else None
    if ir is not None:
        print(f"  - IR: 启用 (合成占位 IR, {len(ir)} 采样)")

    audio = synth.synthesize_ks_chord(
        frequencies=frequencies,
        duration=args.duration,
        alpha=args.alpha,
        rho=args.rho,
        ir=ir,
    )

    os.makedirs(config.SYNTHESIZED_OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(
        config.SYNTHESIZED_OUTPUT_DIR,
        f"ks_{args.chord}.wav",
    )
    synth.export_wav(
        signal=audio,
        sample_rate=config.SAMPLE_RATE,
        output_path=output_path,
        normalize=True,
    )

    print(f"\n[Done] KS 合成完成: {output_path}")
    print(f"A/B 对比参考: {config.SIMULATED_GUITAR_OUTPUT}")


if __name__ == "__main__":
    main()
