# [核心算法] 负责 FFT 分析、频谱提取、声音合成 (DSP 逻辑)
# 直接导入配置
import config

# 直接导入核心包模块
from dsp_guitar_core.synthesizer import Synthesizer
from dsp_guitar_core.extract_envelope import compute_spectral_envelope


if __name__ == '__main__':
    print(f"当前采样率: {config.SAMPLE_RATE}")