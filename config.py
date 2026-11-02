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

# --- 流式实时合成参数 (Streaming Synth Params) ---
BLOCK_SIZE = 256                # 每块样本数：越小延迟越低，但 CPU 预算越紧
MASTER_GAIN = 0.9               # 主输出增益，配合软限幅防止削波
VOICE_ENERGY_THRESHOLD = 1e-5   # 声部能量阈值（约 -50dB，听不到即回收，避免声部累积）
MAX_VOICES = 48                 # 最大并发声部数（超出淘汰最安静的声部，保证 CPU 上界）
STRUM_DELAY = 0.012             # 扫弦相邻弦错位时间 (秒)
DEFAULT_VELOCITY = 0.6          # 固定扫弦力度 (0.0 ~ 1.0)