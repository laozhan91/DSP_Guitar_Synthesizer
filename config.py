import os
import sys

# 获取项目根目录的绝对路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 将项目根目录加入系统路径，确保 dsp_guitar_core 等包可被导入
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

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