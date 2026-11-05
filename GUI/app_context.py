"""GUI 应用上下文
================
持有流式合成引擎、可视化环形缓冲与全局演奏参数，并启动/停止音频流。
音频回调：引擎渲染 → 写环形缓冲(只录弹奏) → 节奏/音序推进 → 混入伴奏 → 软限幅。
"""
import numpy as np
import sounddevice as sd

import config
from dsp_guitar_core.rhythm import RhythmEngine
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
        self.rhythm = RhythmEngine(self.engine, sample_rate=config.SAMPLE_RATE,
                                   bpm=63, pattern='安和桥')

        # 选歌 → 演奏 传递的上下文
        self.free_play = False
        self.current_song = None
        self.current_chart = None
        self.sequencer = None

        # 伴奏播放（混音到输出，但不进频谱环形缓冲）
        self.backing = None
        self._backing_audio = None
        self._backing_pos = 0
        self.backing_gain = 0.5
        self.backing_path = None
        self.chord_segments = []   # [{start, end, chord}]

    def _audio_callback(self, outdata, frames, time, status):
        if status:
            print(status, flush=True)
        self.engine.process(outdata, frames)
        # 频谱只录自己弹奏的 KS 输出（伴奏混音在之后，不进 ring）
        self.ring.write(outdata[:frames, 0])
        if self.sequencer is not None:
            self.sequencer.advance(frames)
        self.rhythm.advance(frames)
        if self.backing is not None:
            self._mix_backing(outdata, frames)
        # 软限幅防止混音削波（ring 已在上方记录纯 KS 输出，不受影响）
        np.tanh(outdata[:, 0], out=outdata[:, 0])

    def load_backing(self, path, gain=0.5):
        """加载伴奏 WAV（转 float32 单声道，必要时重采样到 SAMPLE_RATE）。"""
        from scipy.io import wavfile
        from scipy.signal import resample

        sr, data = wavfile.read(path)
        if data.ndim == 2:
            mono = data.astype(np.float32).mean(axis=1)
        else:
            mono = data.astype(np.float32)
        if data.dtype == np.int16:
            mono /= 32768.0
        if sr != config.SAMPLE_RATE:
            n = int(round(len(mono) * config.SAMPLE_RATE / sr))
            mono = resample(mono, n).astype(np.float32)
        self._backing_audio = np.ascontiguousarray(mono, dtype=np.float32)
        self._backing_pos = 0
        self.backing_gain = float(gain)
        self.backing = self._backing_audio
        return self._backing_audio.shape[0] / config.SAMPLE_RATE

    def _mix_backing(self, outdata, frames):
        """把伴奏混入输出（只加到 outdata，不写入 ring）"""
        if self._backing_audio is None:
            self.backing = None
            return
        n = self._backing_audio.shape[0]
        pos = self._backing_pos
        end = min(pos + frames, n)
        avail = end - pos
        if avail > 0:
            outdata[:avail, 0] += self._backing_audio[pos:end] * self.backing_gain
            self._backing_pos = end
        if self._backing_pos >= n:
            self.backing = None

    def toggle_backing(self):
        """切换伴奏：开着则停，关着则加载当前曲目的 backing_path。"""
        if self.backing is not None:
            self.backing = None
            return False
        if not self.backing_path:
            return False
        self.load_backing(self.backing_path)
        return True

    def backing_position(self):
        """当前伴奏播放位置（秒）"""
        return self._backing_pos / config.SAMPLE_RATE

    def backing_duration(self):
        """伴奏总时长（秒）"""
        if self._backing_audio is None:
            return 0.0
        return self._backing_audio.shape[0] / config.SAMPLE_RATE

    def seek_backing(self, seconds):
        """跳转到伴奏指定位置（秒）"""
        if self._backing_audio is None:
            return
        n = self._backing_audio.shape[0]
        self._backing_pos = max(0, min(n, int(seconds * config.SAMPLE_RATE)))

    def stop_backing(self):
        """停止伴奏播放"""
        self.backing = None

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
