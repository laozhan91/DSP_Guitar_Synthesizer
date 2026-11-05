"""GUI 主题与字体工具"""
import pygame

BG = (18, 18, 24)
PANEL = (32, 32, 42)
PANEL_LIGHT = (46, 46, 58)
ACCENT = (200, 120, 60)
ACCENT_HOVER = (230, 150, 90)
TEXT = (235, 235, 235)
MUTED_TEXT = (140, 140, 150)
GREEN = (120, 200, 120)
RED = (220, 90, 90)


def load_font(size):
    """加载支持中文的字体，找不到时回退到 pygame 默认字体"""
    for name in ('microsoftyahei', 'simhei', 'simsun', 'dengxian'):
        path = pygame.font.match_font(name)
        if path:
            return pygame.font.Font(path, size)
    return pygame.font.Font(None, size)
