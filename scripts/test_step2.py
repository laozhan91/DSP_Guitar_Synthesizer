
"""
test_step2.py - 合成效果验证脚本
=================================
功能：
  1. 加载原始真实吉他音频
  2. 加载合成吉他音频
  3. 绘制波形对比图
  4. 绘制频谱对比图（STFT 时频图）
  5. 计算频谱相似度指标（如频谱质心、频谱滚降点等）

使用方式：
  python test_step2.py --original assets/guitar-chord-in-a-minor.wav \
                       --synthesized output/synthesized_A_minor.wav
"""

import os
import sys
import argparse
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.io import wavfile
from scipy.signal import stft
from typing import Tuple

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['WenQuanYi Zen Hei', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)


def load_wav(filepath: str) -> Tuple[np.ndarray, int]:
    """
    加载 WAV 文件。

    参数:
        filepath: WAV 文件路径

    返回:
        (signal, sample_rate): 音频信号数组和采样率
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"WAV 文件未找到: {filepath}")

    sample_rate, data = wavfile.read(filepath)

    # 如果是立体声，取左声道
    if len(data.shape) > 1:
        data = data[:, 0]

    # 转换为 float64 并归一化到 [-1, 1]
    if data.dtype == np.int16:
        signal = data.astype(np.float64) / 32768.0
    elif data.dtype == np.int32:
        signal = data.astype(np.float64) / 2147483648.0
    elif data.dtype == np.float32 or data.dtype == np.float64:
        signal = data.astype(np.float64)
    else:
        signal = data.astype(np.float64)

    print(f"[Info] 加载文件: {filepath}")
    print(f"  - 采样率: {sample_rate} Hz")
    print(f"  - 采样数: {len(signal)}")
    print(f"  - 时长: {len(signal) / sample_rate:.3f} s")
    print(f"  - 振幅范围: [{signal.min():.4f}, {signal.max():.4f}]")

    return signal, sample_rate


def compute_spectral_features(signal: np.ndarray, sample_rate: int) -> dict:
    """
    计算频谱特征指标。

    参数:
        signal:     音频信号
        sample_rate: 采样率

    返回:
        dict: 包含频谱质心、滚降点、频谱通量等特征
    """
    # STFT 计算
    n_fft = 2048
    hop_length = n_fft // 4
    f, t, Zxx = stft(signal, fs=sample_rate, n_fft=n_fft, hop_length=hop_length)

    # 幅度谱
    magnitude = np.abs(Zxx)
    power = magnitude ** 2

    # 频谱质心 (Spectral Centroid)
    spectral_centroid = np.sum(f * power, axis=0) / (np.sum(power, axis=0) + 1e-10)

    # 频谱滚降点 (Spectral Roll-off) - 85% 能量截止频率
    cumulative_sum = np.cumsum(power, axis=0)
    spectral_rolloff = np.zeros_like(spectral_centroid)
    for i in range(power.shape[1]):
        idx = np.searchsorted(cumulative_sum[:, i], 0.85 * cumulative_sum[-1, i])
        spectral_rolloff[i] = f[min(idx, len(f) - 1)]

    # 频谱通量 (Spectral Flux) - 帧间能量变化
    spectral_flux = np.zeros_like(spectral_centroid)
    for i in range(1, power.shape[1]):
        spectral_flux[i] = np.sum(np.abs(power[:, i] - power[:, i - 1]))

    return {
        'centroid_mean': np.mean(spectral_centroid),
        'centroid_std': np.std(spectral_centroid),
        'rolloff_mean': np.mean(spectral_rolloff),
        'rolloff_std': np.std(spectral_rolloff),
        'flux_mean': np.mean(spectral_flux),
        'flux_std': np.std(spectral_flux),
        'frequencies': f,
        'time': t,
        'Zxx': Zxx
    }


def plot_waveform_comparison(
    original: np.ndarray,
    synthesized: np.ndarray,
    sample_rate: int,
    save_path: str
):
    """绘制原始与合成音频的波形对比图。"""
    fig, axes = plt.subplots(2, 1, figsize=(12, 6), sharex=True)

    # 截取相同长度
    min_len = min(len(original), len(synthesized))
    orig_plot = original[:min_len]
    synth_plot = synthesized[:min_len]

    t = np.arange(min_len) / sample_rate

    axes[0].plot(t, orig_plot, color='#2196F3', linewidth=0.5, label='原始吉他')
    axes[0].set_ylabel('振幅', fontsize=11)
    axes[0].set_title('波形对比: 原始吉他 vs 合成吉他', fontsize=14, fontweight='bold')
    axes[0].legend(loc='upper right', fontsize=10)
    axes[0].set_xlim(0, t[-1])
    axes[0].grid(True, alpha=0.3)

    axes[1].plot(t, synth_plot, color='#FF5722', linewidth=0.5, label='合成吉他')
    axes[1].set_xlabel('时间 (秒)', fontsize=11)
    axes[1].set_ylabel('振幅', fontsize=11)
    axes[1].legend(loc='upper right', fontsize=10)
    axes[1].set_xlim(0, t[-1])
    axes[1].grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"[Info] 波形对比图已保存: {save_path}")


def plot_spectrogram_comparison(
    original: np.ndarray,
    synthesized: np.ndarray,
    sample_rate: int,
    save_path: str
):
    """绘制原始与合成音频的频谱图(STFT)对比。"""
    n_fft = 2048
    hop_length = n_fft // 4

    f_orig, t_orig, Z_orig = stft(original, fs=sample_rate, n_fft=n_fft, hop_length=hop_length)
    f_synth, t_synth, Z_synth = stft(synthesized, fs=sample_rate, n_fft=n_fft, hop_length=hop_length)

    # 取对数幅度谱 (dB)
    magnitude_orig = 20 * np.log10(np.abs(Z_orig) + 1e-10)
    magnitude_synth = 20 * np.log10(np.abs(Z_synth) + 1e-10)

    # 截取相同时间长度
    min_t = min(len(t_orig), len(t_synth))

    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

    # 原始吉他频谱图
    c1 = axes[0].pcolormesh(t_orig[:min_t], f_orig, magnitude_orig[:, :min_t],
                            shading='gouraud', cmap='viridis')
    axes[0].set_ylabel('频率 (Hz)', fontsize=11)
    axes[0].set_title('频谱图对比: 原始吉他 vs 合成吉他', fontsize=14, fontweight='bold')
    axes[0].set_ylim(0, sample_rate / 4)  # 只显示到奈奎斯特频率的一半
    fig.colorbar(c1, ax=axes[0], label='幅度 (dB)')

    # 合成吉他频谱图
    c2 = axes[1].pcolormesh(t_synth[:min_t], f_synth, magnitude_synth[:, :min_t],
                            shading='gouraud', cmap='plasma')
    axes[1].set_xlabel('时间 (秒)', fontsize=11)
    axes[1].set_ylabel('频率 (Hz)', fontsize=11)
    fig.colorbar(c2, ax=axes[1], label='幅度 (dB)')

    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"[Info] 频谱对比图已保存: {save_path}")


def plot_spectrum_overlay(
    original: np.ndarray,
    synthesized: np.ndarray,
    sample_rate: int,
    save_path: str
):
    """绘制叠加频谱对比（同一张图显示两条频谱曲线）。"""
    # 使用 FFT 计算平均频谱
    n_fft = 8192
    f_orig, P_orig = _average_spectrum(original, n_fft, sample_rate)
    f_synth, P_synth = _average_spectrum(synthesized, n_fft, sample_rate)

    # 取相同频率范围
    min_len = min(len(f_orig), len(f_synth))

    plt.figure(figsize=(12, 6))
    plt.semilogy(f_orig[:min_len], P_orig[:min_len] + 1e-10,
                 color='#2196F3', linewidth=1.5, label='原始吉他')
    plt.semilogy(f_synth[:min_len], P_synth[:min_len] + 1e-10,
                 color='#FF5722', linewidth=1.5, label='合成吉他')
    plt.xlabel('频率 (Hz)', fontsize=12)
    plt.ylabel('功率谱密度', fontsize=12)
    plt.title('频谱叠加对比: 原始吉他 vs 合成吉他', fontsize=14, fontweight='bold')
    plt.legend(fontsize=11)
    plt.xlim(0, sample_rate / 4)
    plt.grid(True, alpha=0.3, which='both')
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"[Info] 频谱叠加图已保存: {save_path}")


def _average_spectrum(signal: np.ndarray, n_fft: int, sample_rate: int) -> Tuple[np.ndarray, np.ndarray]:
    """计算信号的平均功率谱。"""
    f, _, Zxx = stft(signal, fs=sample_rate, n_fft=n_fft, nperseg=n_fft)
    power = np.abs(Zxx) ** 2
    avg_power = np.mean(power, axis=1)
    return f, avg_power


def print_similarity_report(features_orig: dict, features_synth: dict):
    """打印频谱特征相似度报告。"""
    print("\n" + "=" * 60)
    print("频谱特征相似度报告")
    print("=" * 60)
    print(f"{'特征指标':<20} {'原始吉他':<15} {'合成吉他':<15} {'差异':<10}")
    print("-" * 60)

    metrics = [
        ('频谱质心 (Hz)', 'centroid_mean', 'centroid_std'),
        ('频谱滚降 (Hz)', 'rolloff_mean', 'rolloff_std'),
        ('频谱通量', 'flux_mean', 'flux_std'),
    ]

    for name, mean_key, std_key in metrics:
        orig_val = features_orig[mean_key]
        synth_val = features_synth[mean_key]
        orig_err = features_orig[std_key]
        synth_err = features_synth[std_key]
        diff = abs(orig_val - synth_val) / max(orig_val, 1e-10) * 100
        print(f"{name:<20} {orig_val:<15.2f} {synth_val:<15.2f} {diff:<10.1f}%")

    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description='DSP 吉他合成效果验证 - 波形与频谱对比',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python test_step2.py --original assets/guitar-chord-in-a-minor.wav \\
                       --synthesized output/synthesized_A_minor.wav
        """
    )

    parser.add_argument('--original', '-o', type=str, required=True,
                        help='原始吉他 WAV 文件路径')
    parser.add_argument('--synthesized', '-s', type=str, required=True,
                        help='合成吉他 WAV 文件路径')
    parser.add_argument('--output-dir', '-d', type=str, default='output',
                        help='图表输出目录')

    args = parser.parse_args()

    # 创建输出目录
    os.makedirs(args.output_dir, exist_ok=True)

    # 加载音频
    try:
        orig_signal, orig_sr = load_wav(args.original)
        synth_signal, synth_sr = load_wav(args.synthesized)
    except FileNotFoundError as e:
        print(f"[Error] {e}")
        sys.exit(1)

    # 统一采样率
    if orig_sr != synth_sr:
        print(f"[Warning] 采样率不一致 ({orig_sr} vs {synth_sr})，统一为 {orig_sr} Hz")
        # 简单重采样（实际项目可用 librosa.resample）
        ratio = synth_sr / orig_sr
        from scipy.signal import resample
        synth_signal = resample(synth_signal, int(len(synth_signal) / ratio))
        synth_sr = orig_sr

    # 截取相同长度
    min_len = min(len(orig_signal), len(synth_signal))
    orig_signal = orig_signal[:min_len]
    synth_signal = synth_signal[:min_len]

    print(f"\n对比时长: {min_len / orig_sr:.3f} s")

    # 计算频谱特征
    print("\n计算频谱特征...")
    features_orig = compute_spectral_features(orig_signal, orig_sr)
    features_synth = compute_spectral_features(synth_signal, orig_sr)

    # 打印相似度报告
    print_similarity_report(features_orig, features_synth)

    # 绘制对比图
    print("\n生成对比图表...")
    plot_waveform_comparison(
        orig_signal, synth_signal, orig_sr,
        os.path.join(args.output_dir, 'waveform_comparison.png')
    )
    plot_spectrogram_comparison(
        orig_signal, synth_signal, orig_sr,
        os.path.join(args.output_dir, 'spectrogram_comparison.png')
    )
    plot_spectrum_overlay(
        orig_signal, synth_signal, orig_sr,
        os.path.join(args.output_dir, 'spectrum_overlay.png')
    )

    print("\n[Done] 验证完成! 所有图表已保存到 output/ 目录。")


if __name__ == '__main__':
    main()