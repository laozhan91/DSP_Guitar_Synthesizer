"""
DSP 吉他合成器 - 主入口

用法：
    python main.py                   # 默认模式：检查包络、合成 A minor 和弦并导出 WAV
    python main.py --play            # 键盘演奏模式：使用 A/S/D/F 键实时弹奏
    python main.py --extract         # 单独运行包络提取流程
"""

import os
import sys
import argparse
import numpy as np
import config

from dsp_guitar_core.synthesizer import Synthesizer, CHORD_FREQUENCIES
from dsp_guitar_core.extract_envelope import (
    load_wav_mono_float32,
    extract_sustain_segment,
    compute_spectral_envelope,
    save_envelope_data,
)


def extract_and_save_envelope():
    """提取并保存频谱包络数据"""
    print("\n未找到包络数据，开始提取...")
    if not os.path.isfile(config.SIMULATED_GUITAR_OUTPUT):
        print(f"模拟吉他音频不存在: {config.SIMULATED_GUITAR_OUTPUT}")
        print("请先运行脚本生成模拟音频。")
        sys.exit(1)

    fs, audio = load_wav_mono_float32(config.SIMULATED_GUITAR_OUTPUT)
    sustain = extract_sustain_segment(audio, fs)
    envelope_data = compute_spectral_envelope(
        sustain,
        fs=fs,
        n_fft=config.N_FFT,
        max_freq=config.MAX_FREQ,
    )
    save_envelope_data(envelope_data, config.ENVELOPE_DATA_PATH)
    print("包络提取完成！")


def load_envelope_data():
    """加载并返回频谱包络数据"""
    # 使用 numpy 推荐的方式读取 npz 文件，按键名直接访问
    with np.load(config.ENVELOPE_DATA_PATH) as envelope_obj:
        return envelope_obj['envelope_mags']


def run_default_mode():
    """默认模式：合成和弦并导出 WAV"""
    synth = Synthesizer(sample_rate=config.SAMPLE_RATE)
    print("\n开始合成并导出 WAV 文件...")

    # 获取 A minor 和弦频率
    chord_name = "A_minor"
    frequencies = CHORD_FREQUENCIES[chord_name]
    print(f"  和弦: {chord_name}")
    print(f"  频率: {frequencies}")

    # 合成和弦
    audio_signal = synth.synthesize_guitar_chord(
        frequencies=frequencies,
        duration=config.DURATION,
    )

    output_path = os.path.join(
        config.SYNTHESIZED_OUTPUT_DIR,
        "synthesized_A_minor.wav"
    )
    
    # 导出 WAV
    synth.export_wav(
        signal=audio_signal,
        sample_rate=config.SAMPLE_RATE,
        output_path=output_path,
        normalize=True
    )

    print(f"\n合成完成！输出文件: {output_path}")


def run_play_mode():
    """键盘演奏模式"""
    # 动态导入，避免不安装 pynput 时报错
    try:
        from dsp_guitar_core.keyboard_controller import KeyboardController
    except ImportError as e:
        print(f"缺少键盘演奏依赖: {e.name}")
        print("请安装: pip install sounddevice pynput")
        sys.exit(1)

    controller = KeyboardController()
    controller.run()


def main():
    print("=" * 50)
    print("  DSP 吉他合成器")
    print("=" * 50)

    # 确保输出目录存在
    os.makedirs(config.SYNTHESIZED_OUTPUT_DIR, exist_ok=True)

    # 解析命令行参数
    parser = argparse.ArgumentParser(description="DSP Guitar Synthesizer")
    parser.add_argument("--play", action="store_true", help="开启键盘演奏模式")
    parser.add_argument("--extract", action="store_true", help="单独执行频谱包络提取")
    args = parser.parse_args()

    # 检查包络数据是否已存在，不存在则提取
    if not os.path.isfile(config.ENVELOPE_DATA_PATH) or args.extract:
        extract_and_save_envelope()
        if args.extract:
            return  # 如果是单独提取模式，执行完后直接退出

    # 检查并加载频谱包络（当前吉他拨弦模型暂不使用，保留供扩展）
    load_envelope_data()
    print(f"已加载包络数据: {config.ENVELOPE_DATA_PATH}")

    # 根据参数选择运行模式
    if args.play:
        run_play_mode()
    else:
        run_default_mode()


if __name__ == "__main__":
    main()