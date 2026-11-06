"""演奏界面 + 实时频谱"""
import math

import numpy as np
import pygame

import config
from GUI.screens.base import Screen
from GUI.theme import BG, TEXT, MUTED_TEXT, ACCENT, load_font
from dsp_guitar_core.fingering import CHORD_FINGERING
from dsp_guitar_core.performance import PerformanceStateMachine, StrumCommand, MuteCommand
from dsp_guitar_core.rhythm import PATTERN_NAMES
from dsp_guitar_core.synthesizer import CHORD_FREQUENCIES, OPEN_STRING_FREQUENCIES

# 安和桥（G 调）和弦映射：Em / D / G / C
KEY_CHORD = {
    pygame.K_a: 'E_minor',
    pygame.K_s: 'D_major',
    pygame.K_d: 'G_major',
    pygame.K_f: 'C_major',
}
# 和弦 → 按键字母
CHORD_TO_KEY = {chord: pygame.key.name(key).upper() for key, chord in KEY_CHORD.items()}

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
        self._held = []  # 按住的左手和弦（支持多键换弦）
        self._win = np.hanning(SPEC_N).astype(np.float32)
        self._edges = np.geomspace(F_MIN, F_MAX, N_BARS + 1)
        self._freqs = np.fft.rfftfreq(SPEC_N, d=1.0 / config.SAMPLE_RATE)

        # STFT 瀑布图状态（3D 瀑布：频谱切片随时间向下级联）
        self._wf_depth = 48
        self._wf_slices = []
        self._bar_band_idx = np.clip(
            np.searchsorted(self._edges, self._freqs, side='right') - 1,
            0, N_BARS - 1)

        # G-3 吉他指板动画状态
        self._anim_t = 0.0
        self._string_exc = np.zeros(6, dtype=np.float32)
        self._str_freq = [2.5 + 0.5 * i for i in range(6)]
        self._str_phase = [0.0, 1.3, 2.4, 0.7, 2.9, 1.7]
        self._last_strum_count = self.ctx.rhythm.strum_count
        self._arrow_dir = None
        self._arrow_timer = 0.0
        self._seeking = False
        self._vol_dragging = False
        gx, gy, gw, gh = self.GUITAR_PANEL
        self.vol_rect = pygame.Rect(gx + 20, gy + 326, gw - 40, 12)

    def on_enter(self):
        # 自动演奏暂不启用：后续加入歌曲音频后，再按需创建 SongSequencer 挂到 ctx.sequencer
        self.state_machine = PerformanceStateMachine(CHORD_FREQUENCIES, OPEN_STRING_FREQUENCIES)
        self._held = []
        self.ctx.rhythm.set_chord(None)
        self.ctx.sequencer = None
        self._string_exc[:] = 0.0
        self._arrow_dir = None
        self._arrow_timer = 0.0
        self._last_strum_count = self.ctx.rhythm.strum_count

    def _dispatch(self, cmd):
        if isinstance(cmd, StrumCommand):
            self.ctx.engine.strum(cmd)
        elif isinstance(cmd, MuteCommand):
            self.ctx.engine.mute(cmd)

    def _chord_down(self, name):
        if name in self._held:
            return
        self._held.append(name)
        for cmd in self.state_machine.handle_chord_press(name):
            self._dispatch(cmd)
        if not self.ctx.free_play:
            self.ctx.rhythm.set_chord(name)

    def _chord_up(self, name):
        if name not in self._held:
            return
        self._held.remove(name)
        active = self._held[-1] if self._held else None
        if active is None:
            for cmd in self.state_machine.handle_chord_release(name):
                self._dispatch(cmd)
            if not self.ctx.free_play:
                self.ctx.rhythm.set_chord(None)
        elif active != name:
            # 回到之前还按着的和弦（换弦回落）
            for cmd in self.state_machine.handle_chord_press(active):
                self._dispatch(cmd)
            if not self.ctx.free_play:
                self.ctx.rhythm.set_chord(active)

    def _strum(self, direction):
        """自由演奏：右手手动扫弦（. 下扫 / , 上扫）"""
        for cmd in self.state_machine.handle_strum(direction, self.ctx.velocity):
            self._dispatch(cmd)
        self._arrow_dir = direction
        self._arrow_timer = 0.35
        self._pluck(direction)

    def _cycle_pattern(self, d):
        names = PATTERN_NAMES
        i = names.index(self.ctx.rhythm.pattern)
        self.ctx.rhythm.set_pattern(names[(i + d) % len(names)])

    def _seek_to(self, x):
        r = self.PROGRESS_RECT
        dur = self.ctx.backing_duration()
        if dur <= 0:
            return
        frac = (x - r.x) / r.width
        frac = max(0.0, min(1.0, frac))
        self.ctx.seek_backing(frac * dur)

    def _set_volume_from_x(self, x):
        r = self.vol_rect
        t = (x - r.x) / r.width
        self.ctx.backing_gain = max(0.0, min(1.0, t))

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.ctx.stop_backing()
                return 'switch:song_select'
            if event.key in KEY_CHORD:
                self._chord_down(KEY_CHORD[event.key])
                return None
            if self.ctx.free_play:
                if event.key in (pygame.K_SPACE, pygame.K_PERIOD):
                    self._strum('down')
                elif event.key == pygame.K_COMMA:
                    self._strum('up')
                return None
            if event.key == pygame.K_LEFTBRACKET:
                self._cycle_pattern(-1)
            elif event.key == pygame.K_RIGHTBRACKET:
                self._cycle_pattern(1)
            elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                self.ctx.rhythm.set_bpm(max(60, self.ctx.rhythm.bpm - 10))
            elif event.key in (pygame.K_EQUALS, pygame.K_KP_PLUS):
                self.ctx.rhythm.set_bpm(min(200, self.ctx.rhythm.bpm + 10))
            elif event.key == pygame.K_b:
                self.ctx.toggle_backing()
        elif event.type == pygame.KEYUP:
            if event.key in KEY_CHORD:
                self._chord_up(KEY_CHORD[event.key])
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.PROGRESS_RECT.collidepoint(event.pos):
                self._seeking = True
                self._seek_to(event.pos[0])
            elif self.vol_rect.collidepoint(event.pos):
                self._vol_dragging = True
                self._set_volume_from_x(event.pos[0])
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._seeking = False
            self._vol_dragging = False
        elif event.type == pygame.MOUSEMOTION:
            if self._seeking:
                self._seek_to(event.pos[0])
            elif self._vol_dragging:
                self._set_volume_from_x(event.pos[0])
        return None

    def update(self, dt):
        self._anim_t += dt
        if self.ctx.rhythm.strum_count != self._last_strum_count:
            self._last_strum_count = self.ctx.rhythm.strum_count
            self._arrow_dir = self.ctx.rhythm.last_direction
            self._arrow_timer = 0.35
            self._pluck(self.ctx.rhythm.last_direction)
        self._string_exc *= np.exp(-dt * 6.0)
        self._arrow_timer = max(0.0, self._arrow_timer - dt)

    def _pluck(self, direction):
        if direction == 'down':
            w = np.array([1.0, 0.85, 0.72, 0.60, 0.50, 0.42], dtype=np.float32)
        else:
            w = np.array([0.42, 0.50, 0.60, 0.72, 0.85, 1.0], dtype=np.float32)
        self._string_exc = np.maximum(self._string_exc, w)

    # ---- 布局常量（屏幕 960x540）----
    PANEL = (60, 86, 560, 230)          # 频谱卡片
    WF_PANEL = (60, 326, 560, 150)      # STFT 瀑布图卡片
    GUITAR_PANEL = (640, 86, 260, 390)  # 吉他指板面板
    PROGRESS_RECT = pygame.Rect(60, 510, 700, 14)  # 播放进度条
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
        if self.ctx.free_play:
            hint_text = 'A/S/D/F 按和弦  ·  空格/句号 下扫  ·  逗号 上扫  ·  Esc 返回'
        else:
            hint_text = 'A/S/D/F 和弦  [ ] 节奏  -/= BPM  B 伴奏  Esc 返回'
        hint = self.small_font.render(hint_text, True, MUTED_TEXT)
        surface.blit(hint, (30, 54))
        self._draw_spectrum(surface)
        self._draw_waterfall(surface)
        self._draw_guitar(surface)
        self._draw_status(surface)
        self._draw_progress(surface)
        self._draw_volume(surface)

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
        held = self.state_machine.current_chord
        held_disp = CHORD_TO_KEY.get(held, held) if held else '空弦'
        ir = '开' if self.ctx.engine.ir_enabled() else '关'
        backing = '开' if self.ctx.backing is not None else '关'
        mode = '自由演奏' if self.ctx.free_play else f'曲目: {self.ctx.current_song}'
        r = self.ctx.rhythm
        if self.ctx.free_play:
            text = f'{mode}  按:{held_disp}  伴奏:{backing}  IR:{ir}'
        else:
            text = f'{mode}  按:{held_disp}  {r.pattern}{int(r.bpm)}BPM  伴奏:{backing}  IR:{ir}'
        label = self.font.render(text, True, TEXT)
        surface.blit(label, (x, y + h + 6))

    def _draw_progress(self, surface):
        r = self.PROGRESS_RECT
        dur = self.ctx.backing_duration()
        pos = self.ctx.backing_position()
        pygame.draw.rect(surface, (30, 30, 40), r, border_radius=4)
        if dur > 0:
            frac = max(0.0, min(1.0, pos / dur))
            fill = pygame.Rect(r.x, r.y, int(r.width * frac), r.height)
            pygame.draw.rect(surface, ACCENT, fill, border_radius=4)
        pygame.draw.rect(surface, MUTED_TEXT, r, 1, border_radius=4)
        t = f'{int(pos // 60):02d}:{int(pos % 60):02d} / {int(dur // 60):02d}:{int(dur % 60):02d}'
        label = self.small_font.render(t, True, TEXT)
        surface.blit(label, (r.x + r.width + 12, r.y - 4))

    def _draw_volume(self, surface):
        r = self.vol_rect
        pygame.draw.rect(surface, (46, 46, 58), r, border_radius=4)
        fill = pygame.Rect(r.x, r.y, int(r.width * self.ctx.backing_gain), r.height)
        pygame.draw.rect(surface, ACCENT, fill, border_radius=4)
        pygame.draw.rect(surface, MUTED_TEXT, r, 1, border_radius=4)
        label = self.small_font.render(f'伴奏音量 {int(self.ctx.backing_gain * 100)}%', True, TEXT)
        surface.blit(label, (r.x, r.y - 20))

    @staticmethod
    def _fade(color, alpha):
        a = max(0.0, min(1.0, alpha))
        return (int(color[0] * a), int(color[1] * a), int(color[2] * a))

    def _expected_chord(self):
        if not self.ctx.chord_segments:
            return None
        t = self.ctx.backing_position()
        for seg in self.ctx.chord_segments:
            if seg['start'] <= t < seg['end']:
                return seg['chord']
        return None

    def _next_chord_info(self):
        if not self.ctx.chord_segments:
            return None
        t = self.ctx.backing_position()
        for seg in self.ctx.chord_segments:
            if seg['start'] > t:
                return seg['chord'], seg['start'] - t
        return None

    def _draw_guitar(self, surface):
        x, y, w, h = self.GUITAR_PANEL
        pygame.draw.rect(surface, (10, 10, 14), (x, y, w, h), 0, border_radius=8)
        pygame.draw.rect(surface, MUTED_TEXT, (x, y, w, h), 1, border_radius=8)

        title = self.font.render('吉他指板', True, TEXT)
        surface.blit(title, (x + 16, y + 8))

        held = self.state_machine.current_chord
        expected = self._expected_chord()
        target = expected if expected else held
        if expected:
            letter = CHORD_TO_KEY.get(expected)
            prompt = self.font.render(f'按 {letter}' if letter else '按 ?', True, ACCENT)
        else:
            prompt = self.small_font.render(held or '空弦 EADGBE', True, MUTED_TEXT)
        surface.blit(prompt, (x + 16, y + 34))

        nxt = self._next_chord_info()
        if nxt:
            next_chord, sec = nxt
            n_txt = CHORD_TO_KEY.get(next_chord, next_chord)
            nlabel = self.small_font.render(f'下一: {n_txt}  {sec:.1f}s', True, MUTED_TEXT)
            surface.blit(nlabel, (x + 16, y + 58))

        nut_y = y + 110
        fret_h = 38
        string_xs = [x + 40 + i * 36 for i in range(6)]
        bottom = nut_y + 5 * fret_h

        # 品线 + 琴枕
        for j in range(6):
            yy = nut_y + j * fret_h
            if j == 0:
                pygame.draw.line(surface, (200, 180, 150), (x + 20, yy), (x + w - 20, yy), 2)
            else:
                pygame.draw.line(surface, (90, 90, 100), (x + 20, yy), (x + w - 20, yy), 1)
        # 品号
        for j in range(1, 6):
            num = self.small_font.render(str(j), True, MUTED_TEXT)
            surface.blit(num, (x + 10, nut_y + (j - 1) * fret_h + fret_h // 2 - 8))

        fingering = CHORD_FINGERING.get(target) if target else [0] * 6
        for i in range(6):
            sx = string_xs[i]
            pygame.draw.line(surface, (140, 140, 150), (sx, nut_y), (sx, bottom), 1)
            exc = float(self._string_exc[i])
            if exc > 0.01:
                amp = exc * 5.0
                pts = [(int(sx + amp * math.sin(2 * math.pi * self._str_freq[i] * self._anim_t + self._str_phase[i])),
                        int(nut_y + (bottom - nut_y) * k / 20)) for k in range(21)]
                pygame.draw.lines(surface, ACCENT, False, pts, 2)
            fret = fingering[i]
            if fret is None or fret < 0:
                xl = self.small_font.render('X', True, (220, 90, 90))
                surface.blit(xl, (sx - 6, nut_y - 24))
            elif fret == 0:
                pygame.draw.circle(surface, TEXT, (sx, nut_y - 12), 5, 1)
            else:
                cy = nut_y + (fret - 1) * fret_h + fret_h // 2
                pygame.draw.circle(surface, ACCENT, (sx, cy), 7)

        # 扫弦方向箭头（右上角）
        if self._arrow_dir and self._arrow_timer > 0:
            alpha = min(1.0, self._arrow_timer / 0.15)
            color = self._fade(ACCENT, alpha)
            cx, cy = x + w - 32, y + 32
            if self._arrow_dir == 'down':
                pts = [(cx, cy - 11), (cx - 11, cy + 9), (cx + 11, cy + 9)]
            else:
                pts = [(cx, cy + 11), (cx - 11, cy - 9), (cx + 11, cy - 9)]
            pygame.draw.polygon(surface, color, pts)

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
