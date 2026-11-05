"""乐谱加载与音序器
====================
把 chart.json 转成「按时间排序、命令预构建」的事件序列，由音频回调线程按
样本时钟推进派发，保证节奏与音频严格对齐，且回调内零分配（派发只做 O(1)
方法调用，StrumCommand/MuteCommand 在加载阶段就已构建好）。
"""
from dataclasses import dataclass
from typing import List, Union

from .performance import StrumCommand, MuteCommand
from .synthesizer import CHORD_FREQUENCIES


@dataclass
class ChartEvent:
    sample: int                                  # 相对曲目起点的样本时间
    cmd: Union[StrumCommand, MuteCommand]        # 预构建好的命令


def load_chart(path: str, sample_rate: int) -> List[ChartEvent]:
    """读取 chart.json，返回按样本时间排序的 ChartEvent 列表。

    和弦切换时自动插入旧和弦的 MuteCommand，避免相邻和弦余音混叠。
    """
    import json

    with open(path, encoding='utf-8') as f:
        data = json.load(f)

    events: List[ChartEvent] = []
    prev_chord = None
    for ev in data['events']:
        sample = int(round(ev['time_ms'] / 1000.0 * sample_rate))
        if ev['type'] == 'strum':
            chord = ev['chord']
            if prev_chord is not None and prev_chord != chord:
                events.append(ChartEvent(sample, MuteCommand(prev_chord)))
            freqs = CHORD_FREQUENCIES[chord]
            events.append(ChartEvent(
                sample,
                StrumCommand(chord, list(freqs), ev['direction'], float(ev['velocity'])),
            ))
            prev_chord = chord
        elif ev['type'] == 'mute':
            events.append(ChartEvent(sample, MuteCommand(ev['chord'])))
            prev_chord = None

    events.sort(key=lambda e: e.sample)
    return events


class SongSequencer:
    """样本时钟驱动的曲谱播放器：由音频回调调用 advance() 推进"""

    def __init__(self, engine, events: List[ChartEvent], sample_rate: int):
        self.engine = engine
        self.events = events
        self.sample_rate = sample_rate
        self._next = 0
        self._pos = 0

    def advance(self, frames: int):
        """音频回调调用：推进 frames 个样本并派发到期事件"""
        self._pos += frames
        while self._next < len(self.events) and self.events[self._next].sample <= self._pos:
            ev = self.events[self._next]
            if isinstance(ev.cmd, StrumCommand):
                self.engine.strum(ev.cmd)
            elif isinstance(ev.cmd, MuteCommand):
                self.engine.mute(ev.cmd)
            self._next += 1

    def elapsed_seconds(self) -> float:
        return self._pos / self.sample_rate

    def upcoming(self, limit: int = 4):
        """返回尚未触发的后续事件（供和弦提示 / 判定使用）"""
        return self.events[self._next:self._next + limit]

    @property
    def finished(self) -> bool:
        return self._next >= len(self.events)
