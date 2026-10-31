import numpy as np
import matplotlib.pyplot as plt
from scipy.io import wavfile
from scipy.signal import medfilt, hilbert
from scipy.interpolate import interp1d

def load_wav(path: str):
    """读取 wav 文件，返回采样率和单声道浮点数组"""
    sample_rate, data = wavfile.read(path)

    if data.ndim == 2:
        data = data[:, 0]

    if data.dtype == np.int16:
        data = data.astype(np.float32) / 32768.0
    elif data.dtype == np.int32:
        data = data.astype(np.float32) / 2147483648.0
    else:
        data = data.astype(np.float32)

    return sample_rate, data

def get_fft(data: np.ndarray, sample_rate: int):
    """计算并返回正频率部分的频率轴和幅度"""
    N = len(data)
    fft_data = np.fft.fft(data)
    freqs = np.fft.fftfreq(N, d=1 / sample_rate)
    
    half = N // 2
    freqs = freqs[:half]
    magnitude = np.abs(fft_data[:half]) * 2 / N
    
    return freqs, magnitude

def extract_envelope(magnitude: np.ndarray, window_size: int = 150):
    """
    基于峰值检测与平滑插值的经典包络提取算法
    完美适配吉他等乐器不均匀的泛音分布
    """
    # 1. 找出所有的局部峰值
    peaks = []
    for i in range(1, len(magnitude) - 1):
        if magnitude[i] > magnitude[i-1] and magnitude[i] > magnitude[i+1]:
            peaks.append(i)
            
    if len(peaks) < 2:
        return np.zeros_like(magnitude)

    # 2. 在极坐标下用窗口大小对峰值进行平滑采样
    x_peaks = np.array(peaks)
    y_peaks = magnitude[x_peaks]
    
    # 3. 用插值函数重新采样成平滑的曲线
    f = interp1d(x_peaks, y_peaks, kind='cubic', fill_value='extrapolate')
    x_smooth = np.linspace(0, len(magnitude) - 1, len(magnitude))
    envelope = f(x_smooth)
    
    # 4. 使用平滑滤波（类似 cepstral smoothing 的直观表现）
    # 保证窗口是奇数且大于 0
    if window_size % 2 == 0:
        window_size += 1
    if window_size > len(magnitude):
        window_size = len(magnitude) // 2 * 2 + 1
        
    from scipy.ndimage import uniform_filter1d
    envelope = uniform_filter1d(envelope, size=window_size)
    
    return envelope

def plot_waveform(data: np.ndarray, sample_rate: int):
    """画音频波形图"""
    time_axis = np.arange(len(data)) / sample_rate

    plt.figure(figsize=(10, 3))
    plt.plot(time_axis, data)
    plt.title("Audio Waveform")
    plt.xlabel("Time (s)")
    plt.ylabel("Amplitude")
    plt.grid(True)
    plt.tight_layout()
    plt.show()

def plot_spectrum_with_envelope(data: np.ndarray, sample_rate: int):
    """画带包络线的频谱图"""
    freqs, magnitude = get_fft(data, sample_rate)
    envelope = extract_envelope(magnitude, window_size=150)

    plt.figure(figsize=(12, 6))
    plt.plot(freqs, magnitude, label='Magnitude', alpha=0.6)
    plt.plot(freqs, envelope, 'r-', linewidth=2.5, label='Spectral Envelope')
    plt.title("Audio Magnitude Spectrum with Envelope")
    plt.xlabel("Frequency (Hz)")
    plt.ylabel("Magnitude")
    plt.xlim(0, 3000)
    plt.ylim(0, max(magnitude) * 1.2) # 优化 Y 轴范围，让图更饱满
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.show()