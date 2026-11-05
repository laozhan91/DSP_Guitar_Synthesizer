"""节奏引擎：按住和弦后按内置节奏模板自动扫弦
============================================
样本时钟驱动（由音频回调 advance），只有当前按住和弦时才发声；
演奏者只需按左手和弦，无需手动上下扫。

节奏模板定义在 16 分音符网格上：一个 4/4 小节 = 16 个槽，
每个扫弦点记 (槽位, 方向, 力度)。advance() 按槽时长循环推进，
到点派发 StrumCommand（只在有和弦按住时）。
"""
from dataclasses import dataclass
from typing import List, Optional

from .performance import StrumCommand
from .synthesizer import CHORD_FREQUENCIES, OPEN_STRING_FREQUENCIES


@dataclass
class RhythmStep:
    samples: int                  # 本步持续样本数
    direction: Optional[str]      # 'down' / 'up' / None（静默步）
    velocity: float


# 16 分网格（一小节 16 槽）上的扫弦点：[(槽位, 方向, 力度)]
PATTERNS = {
    '民谣': [(0, 'down', 0.70), (4, 'down', 0.60), (6, 'up', 0.50),
             (8, 'up', 0.50), (12, 'down', 0.60), (14, 'up', 0.50)],
    '8分': [(0, 'down', 0.70), (2, 'up', 0.50), (4, 'down', 0.70),
            (6, 'up', 0.50), (8, 'down', 0.70), (10, 'up', 0.50),
            (12, 'down', 0.70), (14, 'up', 0.50)],
    '16分': [(i, ('down' if i % 2 == 0 else 'up'),
              (0.60 if i % 2 == 0 else 0.45)) for i in range(16)],
    '附点': [(0, 'down', 0.70), (3, 'up', 0.45), (6, 'down', 0.65),
             (9, 'up', 0.45), (12, 'down', 0.60), (15, 'up', 0.40)],
}

PATTERN_NAMES = list(PATTERNS.keys())


def _build_steps(pattern_name: str, bpm: float, sample_rate: int) -> List[RhythmStep]:
    """把 16 分网格扫弦点展开为循环步列表（总时长恰为一小节）"""
    events = PATTERNS[pattern_name]
    slot_samples = max(1, int(round((60.0 / bpm / 4.0) * sample_rate)))
    steps: List[RhythmStep] = []
    prev = 0
    for slot, direction, velocity in events:
        if slot > prev:
            steps.append(RhythmStep((slot - prev) * slot_samples, None, 0.0))
        steps.append(RhythmStep(slot_samples, direction, velocity))
        prev = slot + 1
    if prev < 16:
        steps.append(RhythmStep((16 - prev) * slot_samples, None, 0.0))
    return steps


class RhythmEngine:
    """样本时钟驱动的节奏引擎：按住和弦后按模板自动扫弦"""

    def __init__(self, engine, sample_rate=44100, bpm=120, pattern='民谣',
                 chord_freqs=None, open_freqs=None):
        self.engine = engine
        self.sample_rate = sample_rate
        self.bpm = float(bpm)
        self.pattern = pattern
        self.chord_freqs = chord_freqs or CHORD_FREQUENCIES
        self.open_freqs = open_freqs or OPEN_STRING_FREQUENCIES
        self.current_chord: Optional[str] = None
        self.last_direction: Optional[str] = None
        self.strum_count = 0
        self._steps = _build_steps(pattern, self.bpm, sample_rate)
        self._step = 0
        self._remaining = self._steps[0].samples if self._steps else 0

    def set_chord(self, name: Optional[str]):
        """设置当前按住的和弦（None = 无和弦，静默）"""
        self.current_chord = name

    def set_pattern(self, name: str):
        if name not in PATTERNS:
            return
        self.pattern = name
        self._steps = _build_steps(name, self.bpm, self.sample_rate)
        self._step = 0
        self._remaining = self._steps[0].samples if self._steps else 0

    def set_bpm(self, bpm: float):
        self.bpm = float(bpm)
        self._steps = _build_steps(self.pattern, self.bpm, self.sample_rate)
        self._step = 0
        self._remaining = self._steps[0].samples if self._steps else 0

    def advance(self, frames: int):
        """音频回调调用：推进 frames 个样本，到点自动扫弦"""
        while self._steps and frames >= self._remaining:
            frames -= self._remaining
            step = self._steps[self._step]
            if step.direction is not None and self.current_chord is not None:
                self._fire(step)
            self._step = (self._step + 1) % len(self._steps)
            self._remaining = self._steps[self._step].samples
        if self._steps:
            self._remaining -= frames

    def _fire(self, step: RhythmStep):
        group = self.current_chord
        freqs = self.chord_freqs[group]
        self.engine.strum(StrumCommand(group, freqs, step.direction, step.velocity))
        self.last_direction = step.direction
        self.strum_count += 1
