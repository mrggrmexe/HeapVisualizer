import pygame
import random
from settings import *

class UI:
    def __init__(self, screen, heap):
        self.screen = screen
        self.heap = heap
        self.font = pygame.font.SysFont("consolas", 20)

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_i:
                value = random.randint(1, 99)
                self.heap.push(value)
            elif event.key == pygame.K_p:
                self.heap.pop()
            elif event.key == pygame.K_m:
                self.heap.toggle_mode()
            elif event.key == pygame.K_r:
                self.heap.clear()

    def draw(self):
        self._draw_array_view()
        self._draw_info_text()

    def _draw_array_view(self):
        if not self.heap.data:
            return
        bar_width = WIDTH // max(10, len(self.heap.data))
        for i, val in enumerate(self.heap.data):
            x = i * bar_width + 10
            y = HEIGHT // 2
            pygame.draw.rect(self.screen, BAR_COLOR, (x, y - val * 3, bar_width - 4, val * 3))
            label = self.font.render(str(val), True, TEXT_COLOR)
            self.screen.blit(label, (x + bar_width // 4, y + 10))

    def _draw_info_text(self):
        mode = "Min-Heap" if self.heap.min_heap else "Max-Heap"
        info = self.font.render(f"[I] Insert  [P] Pop  [M] Toggle ({mode})  [R] Reset", True, TEXT_COLOR)
        self.screen.blit(info, (20, 20))

        # Индикатор корректности кучи
        ok = self.heap.is_valid_heap()
        status_text = "HEAP OK" if ok else "HEAP BROKEN"
        status_color = (120, 255, 120) if ok else (255, 120, 120)
        status = self.font.render(status_text, True, status_color)
        self.screen.blit(status, (20, 50))
