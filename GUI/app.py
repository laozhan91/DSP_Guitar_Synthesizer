"""GUI 应用：屏幕状态机 + 主循环"""
import pygame

from GUI.app_context import AppContext
from GUI.screens.main_screen import MainScreen
from GUI.screens.song_select import SongSelectScreen
from GUI.screens.play_screen import PlayScreen

WIDTH = 960
HEIGHT = 540
FPS = 60


class App:
    def __init__(self, ctx: AppContext):
        pygame.init()
        pygame.display.set_caption('DSP 吉他合成器')
        self.ctx = ctx
        self.width = WIDTH
        self.height = HEIGHT
        self.surface = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.screens = {
            'main': MainScreen(self),
            'song_select': SongSelectScreen(self),
            'play': PlayScreen(self),
        }
        self.current = 'main'
        self.running = True

    def _switch(self, name):
        if name in self.screens:
            self.current = name
            self.screens[self.current].on_enter()

    def _apply_action(self, action):
        if action is None:
            return
        if action.startswith('switch:'):
            self._switch(action.split(':', 1)[1])
        elif action == 'quit':
            self.running = False

    def run(self):
        self.ctx.start_audio()
        try:
            while self.running:
                dt = self.clock.tick(FPS) / 1000.0
                action = None
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.running = False
                    else:
                        a = self.screens[self.current].handle_event(event)
                        if a:
                            action = a
                self._apply_action(action)
                self.screens[self.current].update(dt)
                self.screens[self.current].draw(self.surface)
                pygame.display.flip()
        finally:
            self.ctx.stop_audio()
            pygame.quit()
