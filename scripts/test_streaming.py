"""无头流式合成测试
====================
不依赖 pynput，直接驱动 StreamingGuitarSynth：
  - 定时触发扫弦（空弦 / 和弦交替、方向交替）
  - 定时制音
  - 运行数秒后报告 CPU 负载与 xrun 次数

用法：
    python scripts/test_streaming.py
"""
import time
import sys
import os

import sounddevice as sd

# 把项目根目录加入 sys.path，便于直接运行脚本
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import config
from dsp_guitar_core.synthesizer import CHORD_FREQUENCIES, OPEN_STRING_FREQUENCIES
from dsp_guitar_core.performance import StrumCommand, MuteCommand
from dsp_guitar_core.streaming_synth import StreamingGuitarSynth


def main():
    engine = StreamingGuitarSynth(
        sample_rate=config.SAMPLE_RATE,
        alpha=0.7,
        rho=0.997,
        master_gain=config.MASTER_GAIN,
        energy_threshold=config.VOICE_ENERGY_THRESHOLD,
        strum_delay=config.STRUM_DELAY,
        use_ir=False,
    )

    stats = {'underflows': 0}

    def callback(outdata, frames, time_info, status):
        if status:
            if getattr(status, 'output_underflow', False):
                stats['underflows'] += 1
            print(status, flush=True)
        engine.process(outdata, frames)

    stream = sd.OutputStream(
        samplerate=config.SAMPLE_RATE,
        channels=1,
        dtype='float32',
        blocksize=config.BLOCK_SIZE,
        callback=callback,
    )
    stream.start()

    a_minor = list(CHORD_FREQUENCIES['A_minor'])
    open_strings = list(OPEN_STRING_FREQUENCIES)

    t0 = time.time()
    seq = 0
    print("流式合成测试运行中（约 8 秒）...")
    try:
        while time.time() - t0 < 8.0:
            direction = 'down' if seq % 2 == 0 else 'up'
            if seq % 4 in (0, 1):
                engine.strum(StrumCommand('__open__', open_strings, direction, 0.6))
            else:
                engine.strum(StrumCommand('A_minor', a_minor, direction, 0.6))
            # 偶尔制音
            if seq % 3 == 2:
                engine.mute(MuteCommand('A_minor'))
                engine.mute(MuteCommand('__open__'))
            seq += 1
            time.sleep(0.35)
    finally:
        time.sleep(0.5)  # 让最后一声自然衰减
        stream.stop()
        cpu_load = stream.cpu_load
        stream.close()

    print("\n测试完成：")
    print(f"  触发扫弦次数: {seq}")
    print(f"  CPU 负载: {cpu_load:.3f}")
    print(f"  xrun (output_underflow) 次数: {stats['underflows']}")
    print(f"  剩余声部数: {len(engine.voices)}")


if __name__ == '__main__':
    main()
