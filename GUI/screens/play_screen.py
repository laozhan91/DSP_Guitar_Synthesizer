"""演奏界面 + 实时频谱"""
import numpy as np
import pygame

import config
from GUI.screens.base import Screen
from GUI.theme import BG, TEXT, MUTED_TEXT, ACCENT, load_font
from dsp_guitar_core.performance import PerformanceStateMachine, StrumCommand, MuteCommand
from dsp_guitar_core.synthesizer import CHORD_FREQUENCIES, OPEN_STRING_FREQUENCIES

KEY_CHORD = {
    pygame.K_a: 'A_minor',
    pygame.K_s: 'C_major',
    pygame.K_d: 'G_major',
    pygame.K_f: 'F_major',
}

N_BARS = 96
F_MIN = 60.0
F_MAX = 8000.0
SPEC_N = 2048


class PlayScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.font = load_font(20)
        self.big_font = load_font(30)
        self.small_font = load_font(16)
        self.state_machine = PerformanceStateMachine(CHORD_FREQUENCIES, OPEN_STRING_FREQUENCIES)
        self._win = np.hanning(SPEC_N).astype(np.float32)
        self._edges = np.geomspace(F_MIN, F_MAX, N_BARS + 1)
        self._freqs = np.fft.rfftfreq(SPEC_N, d=1.0 / config.SAMPLE_RATE)

        # STFT 瀑布图状态（3D 瀑布：频谱切片随时间向下级联）
        self._wf_depth = 48
        self._wf_slices = []
        self._bar_band_idx = np.clip(
            np.searchsorted(self._edges, self._freqs, side='right') - 1,
            0, N_BARS - 1)

    def on_enter(self):
        # 自动演奏暂不启用：后续加入歌曲音频后，再按需创建 SongSequencer 挂到 ctx.sequencer
        self.state_machine = PerformanceStateMachine(CHORD_FREQUENCIES, OPEN_STRING_FREQUENCIES)
        self.ctx.sequencer = None

    def _dispatch(self, cmd):
        if isinstance(cmd, StrumCommand):
            self.ctx.engine.strum(cmd)
        elif isinstance(cmd, MuteCommand):
            self.ctx.engine.mute(cmd)

    def _strum(self, direction):
        for cmd in self.state_machine.handle_strum(direction, self.ctx.velocity):
            self._dispatch(cmd)

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return 'switch:song_select'
            if event.key in KEY_CHORD:
                for cmd in self.state_machine.handle_chord_press(KEY_CHORD[event.key]):
                    self._dispatch(cmd)
                return None
            if event.key in (pygame.K_SPACE, pygame.K_PERIOD):
                self._strum('down')
            elif event.key == pygame.K_COMMA:
                self._strum('up')
        elif event.type == pygame.KEYUP:
            if event.key in KEY_CHORD:
                for cmd in self.state_machine.handle_chord_release(KEY_CHORD[event.key]):
                    self._dispatch(cmd)
        return None

    def update(self, dt):
        pass

    # ---- 布局常量（屏幕 960x540）----
    PANEL = (60, 86, 840, 240)          # 频谱卡片
    WF_PANEL = (60, 338, 840, 160)      # STFT 瀑布图卡片
    AXIS_LEFT, AXIS_RIGHT, AXIS_TOP, AXIS_BOTTOM = 52, 10, 30, 28
    WF_AXIS_LEFT, WF_AXIS_RIGHT, WF_AXIS_TOP, WF_AXIS_BOTTOM = 46, 8, 24, 4
    DB_MIN, DB_MAX = -80.0, 0.0
    FREQ_TICKS = (100, 200, 500, 1000, 2000, 5000, 8000)
    BAR_HEADROOM = 6                    # 频谱柱上下留空（像素）

    def _plot_rect(self):
        x, y, w, h = self.PANEL
        return (x + self.AXIS_LEFT, y + self.AXIS_TOP,
                w - self.AXIS_LEFT - self.AXIS_RIGHT,
                h - self.AXIS_TOP - self.AXIS_BOTTOM)

    def draw(self, surface):
        surface.fill(BG)
        title_text = '自由演奏' if self.ctx.free_play else f'曲目: {self.ctx.current_song}'
        title = self.big_font.render(title_text, True, TEXT)
        surface.blit(title, (30, 20))
        hint = self.small_font.render(
            'A/S/D/F 和弦  ·  空格/句号 下扫  ·  逗号 上扫  ·  Esc 返回', True, MUTED_TEXT)
        surface.blit(hint, (30, 54))
        self._draw_spectrum(surface)
        self._draw_waterfall(surface)
        self._draw_status(surface)

    def _draw_spectrum(self, surface):
        x, y, w, h = self.PANEL
        px, py, pw, ph = self._plot_rect()
        grid = (55, 55, 66)

        pygame.draw.rect(surface, (10, 10, 14), (x, y, w, h), 0, border_radius=8)
        panel_title = self.font.render('实时频谱', True, TEXT)
        surface.blit(panel_title, (x + 16, y + 7))

        # dB 横向网格线 + 左侧刻度
        for db in (-80, -60, -40, -20, 0):
            yy = py + int((1.0 - (db - self.DB_MIN) / (self.DB_MAX - self.DB_MIN)) * ph)
            pygame.draw.line(surface, grid, (px, yy), (px + pw, yy), 1)
            label = self.small_font.render(f'{db}', True, MUTED_TEXT)
            surface.blit(label, (x + 6, yy - 8))

        # 频率纵向网格线 + 底部刻度（对数轴）
        for f in self.FREQ_TICKS:
            t = np.log(f / F_MIN) / np.log(F_MAX / F_MIN)
            xx = px + int(t * pw)
            pygame.draw.line(surface, grid, (xx, py), (xx, py + ph), 1)
            label = self.small_font.render(
                f'{int(f)}' if f < 1000 else f'{int(f // 1000)}k', True, MUTED_TEXT)
            surface.blit(label, (xx - label.get_width() // 2, py + ph + 6))

        # 频谱柱
        data = self.ctx.ring.latest(SPEC_N)
        n = len(data)
        if n < SPEC_N:
            data = np.concatenate((np.zeros(SPEC_N - n, dtype=np.float32), data))
        spec = np.abs(np.fft.rfft(data * self._win))
        spec_db = 20.0 * np.log10(spec + 1e-8)

        bar_w = pw / N_BARS
        head = self.BAR_HEADROOM
        usable = ph - 2 * head
        base_y = py + ph - head
        for i in range(N_BARS):
            mask = (self._freqs >= self._edges[i]) & (self._freqs < self._edges[i + 1])
            val = float(np.max(spec_db[mask])) if np.any(mask) else self.DB_MIN
            level = max(0.0, min(1.0, (val - self.DB_MIN) / (self.DB_MAX - self.DB_MIN)))
            bh = int(level * usable)
            bx = px + int(i * bar_w)
            pygame.draw.rect(surface, ACCENT,
                             (bx, base_y - bh, max(1, int(bar_w) - 1), bh))

        pygame.draw.rect(surface, MUTED_TEXT, (x, y, w, h), 1, border_radius=8)

    def _draw_status(self, surface):
        x, y, w, h = self.WF_PANEL
        chord = self.state_machine.current_chord or '空弦 EADGBE'
        ir = '开' if self.ctx.engine.ir_enabled() else '关'
        mode = '自由演奏' if self.ctx.free_play else f'曲目: {self.ctx.current_song}'
        text = f'{mode}    和弦: {chord}    力度: {self.ctx.velocity:.2f}    IR: {ir}'
        label = self.font.render(text, True, TEXT)
        surface.blit(label, (x, y + h + 12))

    def _draw_waterfall(self, surface):
        x, y, w, h = self.WF_PANEL
        axis_left = self.WF_AXIS_LEFT
        axis_top = self.WF_AXIS_TOP
        axis_right = self.WF_AXIS_RIGHT
        axis_bottom = self.WF_AXIS_BOTTOM
        px, py = x + axis_left, y + axis_top
        pw = w - axis_left - axis_right
        ph = h - axis_top - axis_bottom

        pygame.draw.rect(surface, (10, 10, 14), (x, y, w, h), 0, border_radius=8)
        panel_title = self.font.render('STFT 瀑布图', True, TEXT)
        surface.blit(panel_title, (x + 16, y + 5))

        # 计算当前帧频谱切片（log 频段峰值 → 0..1 归一化）
        data = self.ctx.ring.latest(SPEC_N)
        n = len(data)
        if n < SPEC_N:
            data = np.concatenate((np.zeros(SPEC_N - n, dtype=np.float32), data))
        mag = np.abs(np.fft.rfft(data * self._win)).astype(np.float64)
        col = np.zeros(N_BARS, dtype=np.float64)
        np.maximum.at(col, self._bar_band_idx, mag)
        db = 20.0 * np.log10(col + 1e-8)
        levels = np.clip((db - self.DB_MIN) / (self.DB_MAX - self.DB_MIN), 0.0, 1.0)

        self._wf_slices.append(levels)
        if len(self._wf_slices) > self._wf_depth:
            self._wf_slices.pop(0)

        # 3D 瀑布：新切片在顶部，随时间向下级联；越新越亮
        total = len(self._wf_slices)
        amp_scale = ph * 0.55
        bar_w = pw / N_BARS
        dark = (24, 24, 32)
        for i in range(total):
            p = i / max(1, total - 1)          # 0=最旧(最下面) 1=最新(最上面)
            y_base = py + amp_scale + (ph - amp_scale) * (1.0 - p)
            color = (int(dark[0] + (ACCENT[0] - dark[0]) * p),
                     int(dark[1] + (ACCENT[1] - dark[1]) * p),
                     int(dark[2] + (ACCENT[2] - dark[2]) * p))
            arr = self._wf_slices[i]
            pts = [(px + int((j + 0.5) * bar_w),
                    int(y_base - float(arr[j]) * amp_scale)) for j in range(N_BARS)]
            pygame.draw.lines(surface, color, False, pts, 1)

        # 左侧频率刻度（对数）
        for f in (60, 1000, 8000):
            t = np.log(f / F_MIN) / np.log(F_MAX / F_MIN)
            yy = py + ph - int(t * ph)
            label = self.small_font.render(
                f'{int(f)}' if f < 1000 else f'{int(f // 1000)}k', True, MUTED_TEXT)
            surface.blit(label, (x + 4, yy - 8))

        pygame.draw.rect(surface, MUTED_TEXT, (x, y, w, h), 1, border_radius=8)
