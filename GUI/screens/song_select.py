"""选歌界面（Phigros 式滚动列表）"""
import os

import pygame

import config
from GUI.screens.base import Screen
from GUI.theme import BG, PANEL_LIGHT, ACCENT, TEXT, MUTED_TEXT, load_font
from dsp_guitar_core.performance import StrumCommand
from dsp_guitar_core.synthesizer import CHORD_FREQUENCIES

FREE_PLAY = '自由演奏'
SONGS = [
    {'name': '安和桥', 'bpm': 63, 'preview_chord': 'E_minor',
     'difficulties': ['EASY'], 'color': (200, 120, 60),
     'backing': os.path.join(config.ASSETS_DIR, 'BGM', '宋冬野 - 安和桥.wav'),
     'timeline': os.path.join(config.ASSETS_DIR, 'charts', '安和桥_timeline.json')},
]


def _lerp_color(a, b, t):
    t = max(0.0, min(1.0, t))
    return (int(a[0] + (b[0] - a[0]) * t),
            int(a[1] + (b[1] - a[1]) * t),
            int(a[2] + (b[2] - a[2]) * t))


class SongSelectScreen(Screen):
    ITEM_H = 68

    def __init__(self, app):
        super().__init__(app)
        self.font = load_font(26)
        self.big_font = load_font(38)
        self.small_font = load_font(18)
        self.entries = [{'name': FREE_PLAY, 'free': True}] + [
            {'name': s['name'], 'bpm': s['bpm'],
             'difficulties': s['difficulties'], 'diff_index': 0,
             'color': s['color'], 'free': False,
             'preview_chord': s['preview_chord'],
             'backing': s['backing'],
             'timeline': s['timeline']}
            for s in SONGS
        ]
        self.index = 0
        self.scroll = 0.0
        self.center_y = app.height // 2

    def on_enter(self):
        self.index = 0
        self.scroll = float(self.index)

    # ---- 选择 / 难度 ----
    def _move(self, d):
        self.index = (self.index + d) % len(self.entries)

    def _change_diff(self, d):
        entry = self.entries[self.index]
        if entry['free']:
            return
        n = len(entry['difficulties'])
        entry['diff_index'] = (entry['diff_index'] + d) % n

    def _preview(self):
        entry = self.entries[self.index]
        if entry['free']:
            return
        chord = entry['preview_chord']
        freqs = list(CHORD_FREQUENCIES[chord])
        self.ctx.engine.strum(StrumCommand(chord, freqs, 'down', self.ctx.velocity))

    def _entry_at(self, pos):
        for i in range(len(self.entries)):
            y = self.center_y + (i - self.scroll) * self.ITEM_H
            if abs(y - pos[1]) <= self.ITEM_H // 2:
                return i
        return None

    def _select(self):
        entry = self.entries[self.index]
        self.ctx.free_play = entry['free']
        self.ctx.current_song = None if entry['free'] else entry['name']
        self.ctx.backing_path = None if entry['free'] else entry.get('backing')
        self.ctx.chord_segments = [] if entry['free'] else self._load_timeline(entry.get('timeline'))
        return 'switch:play'

    @staticmethod
    def _load_timeline(path):
        if not path:
            return []
        import json
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
            return data.get('chord_segments', [])
        except Exception:
            return []

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.ctx.stop_backing()
                return 'switch:main'
            if event.key in (pygame.K_DOWN, pygame.K_s):
                self._move(1)
            elif event.key in (pygame.K_UP, pygame.K_w):
                self._move(-1)
            elif event.key in (pygame.K_LEFT, pygame.K_a):
                self._change_diff(-1)
            elif event.key in (pygame.K_RIGHT, pygame.K_d):
                self._change_diff(1)
            elif event.key == pygame.K_p:
                self._preview()
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_KP_ENTER):
                return self._select()
        elif event.type == pygame.MOUSEWHEEL:
            self._move(-1 if event.y > 0 else 1)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            i = self._entry_at(event.pos)
            if i is not None:
                self.index = i
        return None

    def update(self, dt):
        target = float(self.index)
        self.scroll += (target - self.scroll) * min(1.0, dt * 12.0)

    def draw(self, surface):
        surface.fill(BG)
        title = self.big_font.render('选择曲目', True, TEXT)
        surface.blit(title, (self.app.width // 2 - title.get_width() // 2, 30))
        hint = self.small_font.render(
            '↑/↓ 选择   ←/→ 难度   P 预览   Enter 进入   Esc 返回', True, MUTED_TEXT)
        surface.blit(hint, (self.app.width // 2 - hint.get_width() // 2, 78))

        for i, entry in enumerate(self.entries):
            y = self.center_y + (i - self.scroll) * self.ITEM_H
            if y < -self.ITEM_H or y > self.app.height + self.ITEM_H:
                continue
            dist = abs(i - self.scroll)
            selected = (i == self.index)
            dim = max(0.35, 1.0 - 0.2 * min(dist, 3.0))
            card_w = int(520 * (1.12 if selected else dim))
            card_h = self.ITEM_H - 8
            rect = pygame.Rect(self.app.width // 2 - card_w // 2,
                               int(y) - card_h // 2, card_w, card_h)

            if selected:
                bg_c = ACCENT
            elif not entry['free']:
                bg_c = _lerp_color(PANEL_LIGHT, entry['color'], 0.25 * dim)
            else:
                bg_c = PANEL_LIGHT

            pygame.draw.rect(surface, bg_c, rect, border_radius=8)
            pygame.draw.rect(surface, TEXT if selected else MUTED_TEXT, rect,
                             2 if selected else 1, border_radius=8)

            name_c = (0, 0, 0) if selected else _lerp_color(TEXT, MUTED_TEXT, 1.0 - dim)
            name = self.font.render(entry['name'], True, name_c)
            surface.blit(name, (rect.x + 24, int(y) - name.get_height() // 2))

            if not entry['free']:
                diff = entry['difficulties'][entry['diff_index']]
                info = self.small_font.render(
                    f"BPM {entry['bpm']}  ·  {diff}", True, MUTED_TEXT)
                surface.blit(info, (rect.x + rect.width - info.get_width() - 20,
                                    int(y) - info.get_height() // 2))
