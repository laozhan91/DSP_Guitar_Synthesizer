"""GUI 应用上下文
================
持有流式合成引擎、可视化环形缓冲与全局演奏参数，并启动/停止音频流。
音频回调只做两件事：引擎渲染 + 写环形缓冲（均零分配）。
"""
import sounddevice as sd

import config
from dsp_guitar_core.streaming_synth import StreamingGuitarSynth
from GUI.visual import VisualRingBuffer

# 可视化缓冲：约 93ms @ 44100，足够画频谱
VISUAL_RING_CAPACITY = 4096


class AppContext:
    def __init__(self, use_ir=False, alpha=0.7, rho=0.997,
                 velocity=None, master_gain=None):
        self.engine = StreamingGuitarSynth(
            sample_rate=config.SAMPLE_RATE,
            alpha=alpha,
            rho=rho,
            master_gain=config.MASTER_GAIN if master_gain is None else master_gain,
            energy_threshold=config.VOICE_ENERGY_THRESHOLD,
            strum_delay=config.STRUM_DELAY,
            use_ir=use_ir,
            max_voices=config.MAX_VOICES,
        )
        self.ring = VisualRingBuffer(capacity=VISUAL_RING_CAPACITY)
        self.velocity = config.DEFAULT_VELOCITY if velocity is None else velocity
        self.stream = None

        # 选歌 → 演奏 传递的上下文
        self.free_play = False
        self.current_song = None
        self.current_chart = None
        self.sequencer = None

    def _audio_callback(self, outdata, frames, time, status):
        if status:
            print(status, flush=True)
        self.engine.process(outdata, frames)
        self.ring.write(outdata[:frames, 0])
        if self.sequencer is not None:
            self.sequencer.advance(frames)

    def start_audio(self):
        if self.stream is not None:
            return
        self.stream = sd.OutputStream(
            samplerate=config.SAMPLE_RATE,
            channels=1,
            dtype='float32',
            blocksize=config.BLOCK_SIZE,
            callback=self._audio_callback,
        )
        self.stream.start()

    def stop_audio(self):
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()
            self.stream = None
