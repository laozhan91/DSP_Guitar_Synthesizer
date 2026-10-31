import os
import sys

# 获取项目根目录的绝对路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 自动将项目根目录和核心引擎包加入系统路径
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
    CORE_PACKAGE = os.path.join(BASE_DIR, 'dsp_guitar_core')
    if CORE_PACKAGE not in sys.path:
        sys.path.insert(0, CORE_PACKAGE)

# --- 资源路径 (Assets) ---
ASSETS_DIR = os.path.join(BASE_DIR, 'assets')
ENVELOPE_DATA_PATH = os.path.join(ASSETS_DIR, 'guitar_envelope_data.npz')
SIMULATED_GUITAR_OUTPUT = os.path.join(ASSETS_DIR, 'simulated_guitar_A_minor.wav')
SYNTHESIZED_OUTPUT_DIR = os.path.join(ASSETS_DIR, 'synthesized')
if not os.path.exists(SYNTHESIZED_OUTPUT_DIR):
    os.makedirs(SYNTHESIZED_OUTPUT_DIR)

# --- 音频参数 (Audio Params) ---
SAMPLE_RATE = 44100
N_FFT = 4096
MAX_FREQ = 8000.0
DURATION = 3.0

# --- 和弦频率定义 ---
CHORD_FREQUENCIES = {
    "A_minor": [220.00, 261.63, 329.63],
    "C_major": [261.63, 329.63, 392.00],
    "D_major": [293.66, 369.99, 440.00],
    "E_major": [329.63, 415.30, 493.88],
    "G_major": [196.00, 246.94, 329.63],
}