"""屏幕基类"""
import pygame


class Screen:
    """GUI 屏幕基类：handle_event 返回动作字符串（如 'switch:song_select'）驱动 App 切屏"""

    def __init__(self, app):
        self.app = app
        self.ctx = app.ctx

    def on_enter(self):
        """切入本屏时调用（重置局部状态）"""
        pass

    def handle_event(self, event):
        """返回动作字符串或 None"""
        return None

    def update(self, dt):
        """每帧逻辑（dt 单位秒）"""
        pass

    def draw(self, surface):
        pass
