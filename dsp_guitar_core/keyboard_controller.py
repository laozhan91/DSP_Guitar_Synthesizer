# [交互控制] 负责监听键盘事件，映射按键到音符频率
# dsp_guitar_core/keyboard_controller.py
import numpy as np
import sounddevice as sd
from pynput import keyboard
import threading

import config
from .synthesizer import Synthesizer, CHORD_FREQUENCIES, generate_synthetic_ir

# 键位与和弦的映射关系
KEY_CHORD_MAP = {
    'a': 'A_minor',
    's': 'C_major',
    'd': 'G_major',
    'f': 'F_major',
}

class KeyboardController:
    def __init__(self, use_ir: bool = False, alpha: float = 0.7, rho: float = 0.997):
        # 初始化合成器
        self.synth = Synthesizer(sample_rate=config.SAMPLE_RATE)

        # 可选琴体 IR（短促低频暖色冲激）
        self.ir = generate_synthetic_ir(sample_rate=config.SAMPLE_RATE) if use_ir else None

        # KS 合成参数
        self.alpha = alpha
        self.rho = rho

        # 音频流缓冲区与锁
        self.active_voices = {}  # {chord_name: {'pos': int, 'buffer': array}}
        self.lock = threading.Lock()
        self.pressed_keys = set() # 防止按键连发

    def _audio_callback(self, outdata, frames, time, status):
        """音频底层回调，负责混音和输出"""
        if status:
            print(status)
        
        # 初始化当前帧缓冲
        buf = np.zeros(frames, dtype=np.float32)
        finished_keys = []
        
        with self.lock:
            for k, voice in self.active_voices.items():
                start = voice['pos']
                end = start + frames
                data = voice['buffer'][start:end]
                
                # 混音叠加
                buf[:len(data)] += data
                voice['pos'] += len(data)
                
                # 检查是否播放完毕
                if voice['pos'] >= len(voice['buffer']):
                    finished_keys.append(k)
                    
        # 清理已播放完毕的和弦
        for k in finished_keys:
            del self.active_voices[k]
            
        # 限制音量，防止削波
        outdata[:, 0] = np.clip(buf, -1.0, 1.0)

    def _play_chord(self, chord_name):
        """触发和弦合成并加入播放队列"""
        if chord_name not in CHORD_FREQUENCIES:
            return

        freqs = CHORD_FREQUENCIES[chord_name]
        # 使用 Karplus-Strong 拨弦物理模型（可选琴体 IR）
        audio = self.synth.synthesize_ks_chord(
            frequencies=freqs,
            duration=2.0,
            alpha=self.alpha,
            rho=self.rho,
            ir=self.ir,
        )
        
        with self.lock:
            # 如果已经在播放则重置位置
            if chord_name in self.active_voices:
                self.active_voices[chord_name]['pos'] = 0
            else:
                self.active_voices[chord_name] = {
                    'buffer': audio.astype(np.float32),
                    'pos': 0
                }

    def on_press(self, key):
        """键盘按下事件"""
        if key == keyboard.Key.esc:
            return False  # 返回 False 停止监听，退出演奏模式
        try:
            char = key.char.lower()
            if char in KEY_CHORD_MAP and char not in self.pressed_keys:
                self.pressed_keys.add(char)
                self._play_chord(KEY_CHORD_MAP[char])
        except AttributeError:
            pass

    def on_release(self, key):
        """键盘松开事件"""
        try:
            char = key.char.lower()
            if char in self.pressed_keys:
                self.pressed_keys.discard(char)
        except AttributeError:
            pass

    def run(self):
        """启动音频流与键盘监听"""
        stream = sd.OutputStream(samplerate=config.SAMPLE_RATE, channels=1, 
                                 dtype='float32', callback=self._audio_callback)
        stream.start()
        
        print(f"琴体 IR: {'启用' if self.ir is not None else '关闭'} | alpha: {self.alpha} | rho: {self.rho}")
        print("键盘演奏模式已启动！按下 A/S/D/F 键弹奏和弦。按 Esc 退出。")
        
        # 监听键盘，按 Esc 退出
        listener = keyboard.Listener(on_press=self.on_press, on_release=self.on_release)
        listener.start()
        
        listener.join()
        stream.stop()
        stream.close()
        print("已退出。")