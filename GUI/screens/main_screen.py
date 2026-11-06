"""主界面（调参屏）"""
import pygame

from GUI.screens.base import Screen
from GUI.theme import BG, PANEL_LIGHT, ACCENT, TEXT, MUTED_TEXT, load_font


class Slider:
    """可拖拽滑杆，值变化时置 changed=True"""

    def __init__(self, label, x, y, w, min_v, max_v, value, fmt='{:.2f}'):
        self.label = label
        self.rect = pygame.Rect(x, y, w, 14)
        self.min_v = min_v
        self.max_v = max_v
        self.value = value
        self.fmt = fmt
        self.dragging = False
        self.changed = False

    def handle_event(self, event):
        hit = self.rect.inflate(0, 18).collidepoint(event.pos) if hasattr(event, 'pos') else False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and hit:
            self.dragging = True
            self._set_from_x(event.pos[0])
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.dragging = False
        elif event.type == pygame.MOUSEMOTION and self.dragging:
            self._set_from_x(event.pos[0])

    def _set_from_x(self, x):
        t = (x - self.rect.x) / max(1, self.rect.width)
        t = max(0.0, min(1.0, t))
        new = self.min_v + t * (self.max_v - self.min_v)
        if abs(new - self.value) > 1e-9:
            self.value = new
            self.changed = True

    def draw(self, surface, font):
        pygame.draw.rect(surface, PANEL_LIGHT, self.rect)
        t = (self.value - self.min_v) / max(1e-9, self.max_v - self.min_v)
        fill = pygame.Rect(self.rect.x, self.rect.y, int(self.rect.width * t), self.rect.height)
        pygame.draw.rect(surface, ACCENT, fill)
        pygame.draw.rect(surface, TEXT, self.rect, 1)
        label = font.render(f"{self.label}: {self.fmt.format(self.value)}", True, TEXT)
        surface.blit(label, (self.rect.x, self.rect.y - 24))


PRESETS = {
    '暖色': (0.60, 0.995),
    '明亮': (0.30, 0.997),
    '长余音': (0.50, 0.999),
}


class MainScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.font = load_font(22)
        self.big_font = load_font(40)
        cx = app.width // 2
        w = 420
        x = cx - w // 2
        self.alpha_slider = Slider('alpha 亮度', x, 170, w, 0.0, 1.0, self.ctx.engine.alpha)
        self.rho_slider = Slider('rho 余音', x, 220, w, 0.90, 1.0, self.ctx.engine.rho)
        self.vel_slider = Slider('力度 velocity', x, 270, w, 0.0, 1.0, self.ctx.velocity)
        self.gain_slider = Slider('音量 gain', x, 320, w, 0.0, 1.0, self.ctx.engine.master_gain)
        self.sliders = [self.alpha_slider, self.rho_slider, self.vel_slider, self.gain_slider]
        self.ir_btn = pygame.Rect(x, 368, 200, 40)
        self.preset_btns = [
            ('暖色', pygame.Rect(x + 214, 368, 60, 40)),
            ('明亮', pygame.Rect(x + 278, 368, 60, 40)),
            ('长余音', pygame.Rect(x + 342, 368, 60, 40)),
        ]
        self.start_btn = pygame.Rect(x, 430, w, 56)
        self._sync_engine()

    def _sync_engine(self):
        eng = self.ctx.engine
        if abs(eng.alpha - self.alpha_slider.value) > 1e-9:
            eng.set_alpha(self.alpha_slider.value)
        if abs(eng.rho - self.rho_slider.value) > 1e-9:
            eng.set_rho(self.rho_slider.value)
        if abs(eng.master_gain - self.gain_slider.value) > 1e-9:
            eng.set_master_gain(self.gain_slider.value)
        self.ctx.velocity = self.vel_slider.value
        self.ctx.rhythm.velocity_scale = self.vel_slider.value

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.ir_btn.collidepoint(event.pos):
                self.ctx.engine.enable_ir(not self.ctx.engine.ir_enabled())
                return None
            for name, rect in self.preset_btns:
                if rect.collidepoint(event.pos):
                    self._apply_preset(name)
                    return None
            if self.start_btn.collidepoint(event.pos):
                return 'switch:song_select'
        for s in self.sliders:
            s.handle_event(event)
        return None

    def _apply_preset(self, name):
        alpha, rho = PRESETS[name]
        self.alpha_slider.value = alpha
        self.rho_slider.value = rho
        self._sync_engine()

    def update(self, dt):
        self._sync_engine()

    def draw(self, surface):
        surface.fill(BG)
        title = self.big_font.render('DSP 吉他合成器', True, TEXT)
        surface.blit(title, (self.app.width // 2 - title.get_width() // 2, 60))
        sub = self.font.render('调参界面 —— 点击「开始演奏」进入选歌', True, MUTED_TEXT)
        surface.blit(sub, (self.app.width // 2 - sub.get_width() // 2, 120))

        ir_on = self.ctx.engine.ir_enabled()
        color = ACCENT if ir_on else PANEL_LIGHT
        pygame.draw.rect(surface, color, self.ir_btn)
        pygame.draw.rect(surface, TEXT, self.ir_btn, 1)
        ir_text = self.font.render(f'琴体 IR: {"开" if ir_on else "关"}', True, TEXT)
        surface.blit(ir_text, (self.ir_btn.x + 20, self.ir_btn.y + 10))

        for name, rect in self.preset_btns:
            pygame.draw.rect(surface, PANEL_LIGHT, rect)
            pygame.draw.rect(surface, TEXT, rect, 1)
            p_text = self.font.render(name, True, TEXT)
            surface.blit(p_text, (
                rect.x + (rect.width - p_text.get_width()) // 2,
                rect.y + (rect.height - p_text.get_height()) // 2,
            ))

        pygame.draw.rect(surface, ACCENT, self.start_btn)
        pygame.draw.rect(surface, TEXT, self.start_btn, 1)
        start_text = self.font.render('开始演奏', True, (0, 0, 0))
        surface.blit(start_text, (
            self.start_btn.x + (self.start_btn.width - start_text.get_width()) // 2,
            self.start_btn.y + (self.start_btn.height - start_text.get_height()) // 2,
        ))

        for s in self.sliders:
            s.draw(surface, self.font)
