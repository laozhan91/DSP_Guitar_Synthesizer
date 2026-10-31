
"""
generate_synthesized_audio.py - 音频生成入口脚本
==================================================
功能：
  1. 加载第一阶段提取的频谱包络数据 (.npy)
  2. 使用 Synthesizer 类合成目标吉他和弦音频
  3. 导出为高保真 WAV 文件
  4. 若包络数据不存在，自动回退调用第一阶段提取流程

使用方式：
  python generate_synthesized_audio.py --chord Am --duration 3.0
  python generate_synthesized_audio.py --chord C --duration 2.5
  python generate_synthesized_audio.py --all  # 合成所有预设和弦

依赖：
  numpy, scipy, matplotlib (可选，用于可视化)
"""

import os
import sys
import argparse
import numpy as np

# 确保项目根目录在路径中
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from dsp_guitar_core.synthesizer import Synthesizer, CHORD_FREQUENCIES


def load_envelope_data(envelope_path: str) -> np.ndarray:
    """
    加载频谱包络数据。

    参数:
        envelope_path: .npy 文件路径

    返回:
        np.ndarray: 频谱包络数组

    异常:
        FileNotFoundError: 文件不存在时抛出
    """
    if not os.path.exists(envelope_path):
        raise FileNotFoundError(
            f"包络数据文件未找到: {envelope_path}\n"
            f"请先运行第一阶段的频谱提取流程生成该文件。"
        )
    envelope = np.load(envelope_path)
    print(f"[Info] 已加载频谱包络数据: {envelope_path}")
    print(f"  - 形状: {envelope.shape}")
    print(f"  - 数据类型: {envelope.dtype}")
    print(f"  - 振幅范围: [{envelope.min():.4f}, {envelope.max():.4f}]")
    return envelope


def auto_fallback_extract(envelope_path: str, assets_dir: str) -> np.ndarray:
    """
    自动回退: 若 .npy 不存在，尝试从 assets/ 中的原始 WAV 重新提取包络。

    注意: 此函数假设第一阶段的提取函数已可用。
    若第一阶段代码结构不同，请根据实际情况调整导入路径和函数名。

    参数:
        envelope_path: 目标 .npy 路径
        assets_dir: 素材目录路径

    返回:
        np.ndarray: 提取到的频谱包络
    """
    print("[Info] 包络数据不存在，尝试自动回退提取...")
    print("  提示: 请确保第一阶段的提取函数可导入，或手动运行提取脚本。")
    # 这里留一个接口，实际实现取决于第一阶段代码结构
    raise FileNotFoundError(
        "自动回退提取未实现。请手动运行第一阶段提取脚本生成 guitar_envelope_data.npy。"
    )


def synthesize_and_export(
    chord_name: str,
    duration: float,
    envelope_data: np.ndarray,
    sample_rate: int = 44100,
    waveform_type: str = 'sawtooth',
    output_dir: str = 'output'
) -> str:
    """
    合成指定和弦并导出 WAV。

    参数:
        chord_name:     和弦名称 (如 'A_minor', 'C_major')
        duration:       合成时长 (秒)
        envelope_data:  频谱包络数据
        sample_rate:    采样率
        waveform_type:  基础波形类型
        output_dir:     输出目录

    返回:
        str: 输出文件路径
    """
    # 初始化合成器
    synth = Synthesizer(sample_rate=sample_rate)

    # 获取和弦频率
    if chord_name not in CHORD_FREQUENCIES:
        raise ValueError(
            f"未知和弦: {chord_name}\n"
            f"可用和弦: {list(CHORD_FREQUENCIES.keys())}"
        )

    frequencies = CHORD_FREQUENCIES[chord_name]
    print(f"\n[Synthesizer] 开始合成和弦: {chord_name}")
    print(f"  - 频率: {frequencies}")
    print(f"  - 时长: {duration}s")
    print(f"  - 波形: {waveform_type}")
    print(f"  - 采样率: {sample_rate} Hz")

    # ADSR 参数（吉他拨弦优化）
    adsr_params = {
        'attack': 0.003,    # 拨弦瞬间极快起振
        'decay': 0.15,      # 明显的衰减过程
        'sustain_level': 0.5,  # 中等延音
        'release': 0.4      # 松手后余音消散
    }

    # 合成和弦
    audio = synth.synthesize_chord(
        frequencies=frequencies,
        duration=duration,
        waveform_type=waveform_type,
        adsr_params=adsr_params,
        spectral_envelope=envelope_data
    )

    # 导出 WAV
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f'synthesized_{chord_name}.wav')
    synth.export_wav(audio, sample_rate=sample_rate, output_path=output_path)

    print(f"\n[Done] 合成完成!")
    return output_path


def main():
    parser = argparse.ArgumentParser(
        description='DSP 吉他音频合成器 - 生成合成音频',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
可用和弦列表:
  A_minor  B_minor  C_major  D_major  E_major  F_major  G_major

示例:
  python generate_synthesized_audio.py --chord Am --duration 3.0
  python generate_synthesized_audio.py --chord C_major --waveform sine
  python generate_synthesized_audio.py --all
        """
    )

    parser.add_argument('--chord', '-c', type=str, default='A_minor',
                        help='和弦名称 (默认: A_minor)')
    parser.add_argument('--duration', '-d', type=float, default=3.0,
                        help='合成时长 (秒，默认: 3.0)')
    parser.add_argument('--waveform', '-w', type=str, default='sawtooth',
                        choices=['sine', 'square', 'sawtooth', 'triangle'],
                        help='基础波形类型 (默认: sawtooth)')
    parser.add_argument('--sample-rate', '-r', type=int, default=44100,
                        help='采样率 Hz (默认: 44100)')
    parser.add_argument('--envelope', '-e', type=str,
                        default=os.path.join('assets', 'guitar_envelope_data.npy'),
                        help='频谱包络文件路径')
    parser.add_argument('--output-dir', '-o', type=str, default='output',
                        help='输出目录 (默认: output)')
    parser.add_argument('--all', action='store_true',
                        help='合成所有预设和弦')

    args = parser.parse_args()

    # 加载包络数据
    try:
        envelope_data = load_envelope_data(args.envelope)
    except FileNotFoundError:
        envelope_data = auto_fallback_extract(args.envelope, os.path.join(project_root, 'assets'))

    if args.all:
        # 合成所有和弦
        for chord_name in CHORD_FREQUENCIES.keys():
            try:
                synthesize_and_export(
                    chord_name=chord_name,
                    duration=args.duration,
                    envelope_data=envelope_data,
                    sample_rate=args.sample_rate,
                    waveform_type=args.waveform,
                    output_dir=args.output_dir
                )
            except Exception as e:
                print(f"[Error] 合成 {chord_name} 失败: {e}")
    else:
        synthesize_and_export(
            chord_name=args.chord,
            duration=args.duration,
            envelope_data=envelope_data,
            sample_rate=args.sample_rate,
            waveform_type=args.waveform,
            output_dir=args.output_dir
        )


if __name__ == '__main__':
    main()