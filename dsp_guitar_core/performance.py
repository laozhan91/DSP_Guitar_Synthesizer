"""演奏状态机（Performance State Machine）
=========================================
把底层键盘事件翻译成流式引擎能执行的「命令」，使键盘层与 DSP 层解耦。

设计目标（可扩展性）：
  - 事件（用户动作）与命令（引擎动作）分离：后续新增演奏技巧
    （滑弦、推弦、闷音、点弦等）时，只需新增 handle_xxx 方法并返回
    新命令，DSP 引擎单独实现该命令即可，互不影响。
  - 状态机只维护极少的演奏上下文（当前按住的弦/和弦），不持有任何
    DSP 状态，DSP 状态全部在流式引擎内部。

状态：
  current_chord: 左手按下的和弦名（None 表示空弦 EADGBE）

命令：
  StrumCommand: 对一组弦扫弦（方向 + 力度）
  MuteCommand:  对一组弦制音（余音快速衰减）
"""
from dataclasses import dataclass
from typing import List, Optional, Sequence

# 空弦组的标签（区别于具体和弦名）
OPEN_GROUP = '__open__'


@dataclass(frozen=True)
class StrumCommand:
    """扫弦命令：对 freqs 中的每根弦按方向错位拨弦"""
    group: str                 # 归属组（和弦名或 OPEN_GROUP），用于制音定位
    freqs: Sequence[float]     # 各弦基频 (Hz)
    direction: str             # 'up' | 'down'
    velocity: float            # 力度 0.0 ~ 1.0


@dataclass(frozen=True)
class MuteCommand:
    """制音命令：让 group 对应的所有声部快速衰减"""
    group: str


class PerformanceStateMachine:
    """演奏状态机：把用户动作映射为引擎命令"""

    def __init__(self, chord_freqs: dict, open_freqs: Sequence[float]):
        self.chord_freqs = chord_freqs
        self.open_freqs = list(open_freqs)
        self.current_chord: Optional[str] = None  # None = 空弦

    # --------------------------------------------------
    # 事件处理（新增演奏技巧时在此扩展）
    # --------------------------------------------------

    def handle_chord_press(self, name: str) -> List[object]:
        """左手按下和弦：只选弦不发声；换弦时制掉旧弦余音"""
        cmds: List[object] = []
        if self.current_chord is not None and self.current_chord != name:
            cmds.append(MuteCommand(self.current_chord))
        elif self.current_chord is None:
            # 从空弦过渡到按弦：制掉空弦余音
            cmds.append(MuteCommand(OPEN_GROUP))
        self.current_chord = name
        return cmds

    def handle_chord_release(self, name: str) -> List[object]:
        """左手松开和弦：制音"""
        if name == self.current_chord:
            self.current_chord = None
            return [MuteCommand(name)]
        return []

    def handle_strum(self, direction: str, velocity: float) -> List[object]:
        """右手扫弦：对当前弦组（按弦或空弦）发声"""
        if self.current_chord is not None:
            group = self.current_chord
            freqs = self.chord_freqs[group]
        else:
            group = OPEN_GROUP
            freqs = self.open_freqs
        return [StrumCommand(
            group=group,
            freqs=list(freqs),
            direction=direction,
            velocity=velocity,
        )]
