# [交互控制] 监听键盘，把按键映射为演奏动作（状态机 + 流式合成引擎）
# dsp_guitar_core/keyboard_controller.py
import sounddevice as sd
from pynput import keyboard

import config
from .synthesizer import CHORD_FREQUENCIES, OPEN_STRING_FREQUENCIES
from .performance import (
    PerformanceStateMachine, StrumCommand, MuteCommand,
)
from .streaming_synth import StreamingGuitarSynth

# 键位与和弦的映射关系（左手）
KEY_CHORD_MAP = {
    'a': 'A_minor',
    's': 'C_major',
    'd': 'G_major',
    'f': 'F_major',
}

# 扫弦键（右手）：直接按 ',' 与 '.'，无需 Shift
STRUM_UP_CHAR = ','    # 上扫（高音弦先响）
STRUM_DOWN_CHAR = '.'  # 下扫（低音弦先响）


class KeyboardController:
    def __init__(self, use_ir: bool = False, alpha: float = 0.7,
                 rho: float = 0.997, velocity: float = None):
        # 流式合成引擎（DSP 全部在音频回调线程内执行）
        self.engine = StreamingGuitarSynth(
            sample_rate=config.SAMPLE_RATE,
            alpha=alpha,
            rho=rho,
            master_gain=config.MASTER_GAIN,
            energy_threshold=config.VOICE_ENERGY_THRESHOLD,
            strum_delay=config.STRUM_DELAY,
            use_ir=use_ir,
            max_voices=config.MAX_VOICES,
        )
        self.use_ir = use_ir
        self.alpha = alpha
        self.rho = rho
        self.velocity = config.DEFAULT_VELOCITY if velocity is None else velocity

        # 演奏状态机：把按键事件翻译成引擎命令
        self.state_machine = PerformanceStateMachine(
            chord_freqs=CHORD_FREQUENCIES,
            open_freqs=OPEN_STRING_FREQUENCIES,
        )

        self.pressed_keys = set()  # 防止按键连发（pynput 按住会重复 on_press）

    # --------------------------------------------------
    # 音频回调
    # --------------------------------------------------
    def _audio_callback(self, outdata, frames, time, status):
        if status:
            print(status, flush=True)
        self.engine.process(outdata, frames)

    # --------------------------------------------------
    # 命令分发：状态机输出 -> 引擎
    # --------------------------------------------------
    def _dispatch(self, cmds):
        for cmd in cmds:
            if isinstance(cmd, StrumCommand):
                self.engine.strum(cmd)
            elif isinstance(cmd, MuteCommand):
                self.engine.mute(cmd)

    def _do_strum(self, direction):
        self._dispatch(self.state_machine.handle_strum(direction, self.velocity))

    def _do_chord_press(self, name):
        self._dispatch(self.state_machine.handle_chord_press(name))

    def _do_chord_release(self, name):
        self._dispatch(self.state_machine.handle_chord_release(name))

    # --------------------------------------------------
    # 键盘事件
    # --------------------------------------------------
    def on_press(self, key):
        if key == keyboard.Key.esc:
            return False  # 返回 False 停止监听，退出演奏模式

        try:
            char = key.char.lower()
        except AttributeError:
            return

        if char in (STRUM_UP_CHAR, STRUM_DOWN_CHAR):
            if char not in self.pressed_keys:
                self.pressed_keys.add(char)
                direction = 'up' if char == STRUM_UP_CHAR else 'down'
                self._do_strum(direction)
        elif char in KEY_CHORD_MAP and char not in self.pressed_keys:
            self.pressed_keys.add(char)
            self._do_chord_press(KEY_CHORD_MAP[char])

    def on_release(self, key):
        try:
            char = key.char.lower()
        except AttributeError:
            return
        if char in self.pressed_keys:
            self.pressed_keys.discard(char)
        if char in KEY_CHORD_MAP:
            self._do_chord_release(KEY_CHORD_MAP[char])

    # --------------------------------------------------
    # 启动
    # --------------------------------------------------
    def run(self):
        stream = sd.OutputStream(
            samplerate=config.SAMPLE_RATE,
            channels=1,
            dtype='float32',
            blocksize=config.BLOCK_SIZE,
            callback=self._audio_callback,
        )
        stream.start()

        print(f"琴体 IR: {'启用' if self.use_ir else '关闭'} | alpha: {self.alpha} | rho: {self.rho} | 力度: {self.velocity:.2f}")
        print("演奏模式已启动：")
        print("  左手 A/S/D/F = 按住和弦（不发声）")
        print("  右手 . = 下扫  , = 上扫（没按和弦时扫空弦）")
        print("  松开字母键 = 制音；按 Esc 退出")

        listener = keyboard.Listener(on_press=self.on_press, on_release=self.on_release)
        listener.start()

        listener.join()
        stream.stop()
        stream.close()
        print("已退出。")