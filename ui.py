import pygame
import random
from settings import *

class UI:
    def __init__(self, screen, heap):
        self.screen = screen
        self.heap = heap
        self.font = pygame.font.SysFont("consolas", 20)
        self.small = pygame.font.SysFont("consolas", 16)

        # Кнопки: (метка, действие-строка)
        self.buttons = []
        self._build_buttons()

        # Поле ввода
        self.input_rect = pygame.Rect(20, 44, 160, 28)
        self.input_active = False
        self.input_text = ""  # вводимое число

        # Ховеры
        self._hover_btn = None

    # ---------- построение кнопок ----------
    def _build_buttons(self):
        """
        Формирует линейку кнопок на верхней панели. Кнопка Toggle динамически меняет текст Min/Max.
        """
        labels = [
            ("Insert Rand", "insert_rand"),
            (self._toggle_label(), "toggle_mode"),
            ("Pop", "pop"),
            ("Reset", "reset"),
        ]
        x = 20
        y = 12
        self.buttons.clear()
        for label, action in labels:
            w, h = self.font.size(label)
            rect = pygame.Rect(x, y, w + 24, 28)
            self.buttons.append({"rect": rect, "label": label, "action": action})
            x += rect.width + 10

    def _toggle_label(self):
        return "To Max-Heap" if self.heap.min_heap else "To Min-Heap"

    # ---------- обработка событий ----------
    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self._hover_btn = None
            for btn in self.buttons:
                if btn["rect"].collidepoint(event.pos) and self._is_enabled(btn):
                    self._hover_btn = btn
                    break

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # Фокус ввода
            if self.input_rect.collidepoint(event.pos):
                self.input_active = True
            else:
                self.input_active = False

            # Клик по кнопкам
            for btn in self.buttons:
                if btn["rect"].collidepoint(event.pos) and self._is_enabled(btn):
                    self._run_action(btn["action"])
                    break

        elif event.type == pygame.KEYDOWN:
            # Горячие клавиши остаются
            if event.key == pygame.K_i:
                self._run_action("insert_rand")
            elif event.key == pygame.K_p:
                self._run_action("pop")
            elif event.key == pygame.K_m:
                self._run_action("toggle_mode")
            elif event.key == pygame.K_r:
                self._run_action("reset")

            # Ввод в поле
            if self.input_active:
                if event.key == pygame.K_RETURN:
                    self._insert_from_input()
                elif event.key == pygame.K_BACKSPACE:
                    self.input_text = self.input_text[:-1]
                else:
                    ch = event.unicode
                    if ch.isdigit() and len(self.input_text) < 6:
                        self.input_text += ch

    # ---------- действия ----------
    def _run_action(self, action: str):
        if action == "insert_rand":
            value = random.randint(1, 99)
            self.heap.push(value)
        elif action == "toggle_mode":
            # корректно перестраиваем
            if hasattr(self.heap, "toggle_mode"):
                self.heap.toggle_mode()
            else:
                # обратная совместимость (если старый heap.py)
                self.heap.min_heap = not self.heap.min_heap
                if hasattr(self.heap, "heapify"):
                    self.heap.heapify()
        elif action == "pop":
            if len(self.heap) > 0:
                self.heap.pop()
        elif action == "reset":
            self.heap.clear()

        # обновить подписи (кнопка Toggle)
        self._build_buttons()

    def _insert_from_input(self):
        if self.input_text:
            try:
                val = int(self.input_text)
                # Небольшая нормализация диапазона
                if val < -10_000: val = -10_000
                if val > 10_000: val = 10_000
                self.heap.push(val)
            except ValueError:
                pass
        self.input_text = ""
        self.input_active = False

    def _is_enabled(self, btn) -> bool:
        act = btn["action"]
        if act == "pop" and len(self.heap) == 0:
            return False
        return True

    # ---------- отрисовка ----------
    def draw(self):
        self._draw_toolbar()
        self._draw_array_view()
        self._draw_info_text()

    def _draw_toolbar(self):
        # фон панели
        pygame.draw.rect(self.screen, PANEL_BG, (0, 0, WIDTH, PANEL_H))

        # кнопки
        for btn in self.buttons:
            rect = btn["rect"]
            enabled = self._is_enabled(btn)
            if not enabled:
                bg = BTN_BG_DISABLED
            elif self._hover_btn is btn:
                bg = BTN_BG_HOVER
            else:
                bg = BTN_BG
            pygame.draw.rect(self.screen, bg, rect, border_radius=6)
            label_surf = self.font.render(btn["label"], True, TEXT_COLOR)
            self.screen.blit(label_surf, (rect.x + 12, rect.y + 4))

        # поле ввода + кнопка Insert
        pygame.draw.rect(
            self.screen,
            (160, 160, 160) if self.input_active else INPUT_BG,
            self.input_rect,
            border_radius=6,
        )
        placeholder = "Type number…" if not self.input_text else self.input_text
        ph_color = (200, 200, 200) if self.input_text else (130, 130, 150)
        txt = self.small.render(placeholder, True, ph_color)
        self.screen.blit(txt, (self.input_rect.x + 8, self.input_rect.y + 6))

        # кнопка "Insert"
        insert_rect = pygame.Rect(self.input_rect.right + 8, self.input_rect.y, 90, 28)
        pygame.draw.rect(self.screen, BTN_BG if self.input_text else BTN_BG_DISABLED, insert_rect, border_radius=6)
        label = self.font.render("Insert", True, TEXT_COLOR)
        self.screen.blit(label, (insert_rect.x + 16, insert_rect.y + 4))

        # Клик по Insert
        # (в обработчике мыши нам нужно знать этот rect: сделаем простую проверку прямо здесь через состояние мыши)
        if pygame.mouse.get_pressed(num_buttons=3)[0]:
            # если нажата ЛКМ и наведено на кнопку — выполним
            if insert_rect.collidepoint(pygame.mouse.get_pos()) and self.input_text:
                self._insert_from_input()

    def _draw_array_view(self):
        if not self.heap or not getattr(self.heap, "data", None):
            # подсказка в центре, если пусто
            msg = self.font.render("Heap is empty. Use Insert or type a number ↑", True, (180, 180, 200))
            self.screen.blit(msg, (WIDTH // 2 - msg.get_width() // 2, HEIGHT // 2 - msg.get_height() // 2))
            return

        # Динамически вычисляем ширину/масштаб и стартовую точку ниже панели
        top = PANEL_H + 10
        available_h = HEIGHT - top - 50
        values = self.heap.data
        vmax = max(abs(v) for v in values) or 1
        scale = max(1, available_h // (vmax * 3))

        bar_width = max(16, WIDTH // max(10, len(values)))
        for i, val in enumerate(values):
            x = i * bar_width + 10
            # нулевая линия
            base_y = top + available_h // 2
            height = abs(val) * scale * 3
            y = base_y - height if val >= 0 else base_y
            rect = pygame.Rect(x, y, bar_width - 4, height)
            color = BAR_COLOR
            pygame.draw.rect(self.screen, color, rect)
            label = self.small.render(str(val), True, TEXT_COLOR)
            self.screen.blit(label, (x + (bar_width - label.get_width()) // 2, base_y + 6))

        # линия нуля
        pygame.draw.line(self.screen, (90, 90, 110), (10, top + available_h // 2), (WIDTH - 10, top + available_h // 2), 1)

    def _draw_info_text(self):
        # режим
        mode = "Min-Heap" if self.heap.min_heap else "Max-Heap"
        info = self.font.render(f"[I] InsertRand  [P] Pop  [M] Toggle  [R] Reset   ({mode})", True, TEXT_COLOR)
        self.screen.blit(info, (20, HEIGHT - 36))

        # статус кучи
        ok = True
        if hasattr(self.heap, "is_valid_heap"):
            try:
                ok = self.heap.is_valid_heap()
            except Exception:
                ok = False
        status_text = "HEAP OK" if ok else "HEAP BROKEN"
        status_color = ACCENT_OK if ok else ACCENT_BAD
        status = self.font.render(status_text, True, status_color)
        self.screen.blit(status, (20, HEIGHT - 62))
