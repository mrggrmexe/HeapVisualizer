import pygame
import random
import time
from settings import *


class UI:
    def __init__(self, screen, heap):
        self.screen = screen
        self.heap = heap
        self.font = pygame.font.SysFont("consolas", 20)
        self.small = pygame.font.SysFont("consolas", 16)

        # ----- Буферы для отрисовки -----
        self.overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        self.bars_layer = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        self.toolbar_surface = pygame.Surface((WIDTH, PANEL_H), pygame.SRCALPHA)
        self.toolbar_needs_redraw = True

        # ----- Кнопки и ввод -----
        self.buttons = []
        self._build_buttons()
        self.input_rect = pygame.Rect(20, 44, 160, 28)
        self.input_active = False
        self.input_text = ""
        self.insert_btn_rect = None
        self._hover_btn = None

        # ----- Анимации -----
        self.anim_queue = []
        self.current_anim = None
        self.highlight_pair = None
        self.highlight_end = 0

        # ----- Dirty rectangles — только изменённые зоны -----
        self.dirty_rects = set()

        if hasattr(self.heap, "set_observer"):
            self.heap.set_observer(self._on_heap_event)

    # ----- построение кнопок -----
    def _build_buttons(self):
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
        self.toolbar_needs_redraw = True  # пометим панель как изменённую

    def _toggle_label(self):
        return "To Max-Heap" if self.heap.min_heap else "To Min-Heap"

    # ----- обработка событий -----
    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            new_hover = None
            for btn in self.buttons:
                if btn["rect"].collidepoint(event.pos) and self._is_enabled(btn):
                    new_hover = btn
                    break
            if new_hover is not self._hover_btn:
                self._hover_btn = new_hover
                self.toolbar_needs_redraw = True

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.insert_btn_rect and self.insert_btn_rect.collidepoint(event.pos):
                if self.input_text:
                    self._insert_from_input()
                    self.toolbar_needs_redraw = True
                return

            self.input_active = self.input_rect.collidepoint(event.pos)
            if self.input_active:
                self.toolbar_needs_redraw = True

            for btn in self.buttons:
                if btn["rect"].collidepoint(event.pos) and self._is_enabled(btn):
                    self._run_action(btn["action"])
                    return

        elif event.type == pygame.KEYDOWN:
            if self.input_active:
                self._handle_text_input(event)
            else:
                self._handle_shortcuts(event)

    def _handle_shortcuts(self, event):
        keymap = {
            pygame.K_i: "insert_rand",
            pygame.K_p: "pop",
            pygame.K_m: "toggle_mode",
            pygame.K_r: "reset",
        }
        action = keymap.get(event.key)
        if action:
            self._run_action(action)
            self.toolbar_needs_redraw = True

    def _handle_text_input(self, event):
        if event.key == pygame.K_RETURN:
            self._insert_from_input()
        elif event.key == pygame.K_BACKSPACE:
            self.input_text = self.input_text[:-1]
        elif event.key == pygame.K_ESCAPE:
            self.input_active = False
        else:
            ch = event.unicode
            if (ch.isdigit() or (ch == "-" and not self.input_text)) and len(self.input_text) < 6:
                self.input_text += ch
        self.toolbar_needs_redraw = True

    def _run_action(self, action: str):
        if action == "insert_rand":
            self.heap.push(random.randint(1, 99))
        elif action == "toggle_mode":
            if hasattr(self.heap, "toggle_mode"):
                self.heap.toggle_mode()
            else:
                self.heap.min_heap = not self.heap.min_heap
                if hasattr(self.heap, "heapify"):
                    self.heap.heapify()
        elif action == "pop" and len(self.heap) > 0:
            self.heap.pop()
        elif action == "reset":
            self.heap.clear()
        self._build_buttons()

    def _insert_from_input(self):
        try:
            val = int(self.input_text)
            val = max(-10_000, min(10_000, val))
            self.heap.push(val)
        except ValueError:
            pass
        self.input_text = ""
        self.input_active = False

    def _is_enabled(self, btn) -> bool:
        return not (btn["action"] == "pop" and len(self.heap) == 0)

    # ----- observer -----
    def _on_heap_event(self, event: str, payload: dict):
        mapping = {
            "compare": (ANIM_COMPARE_MS, "compare"),
            "swap": (ANIM_SWAP_MS, "swap"),
            "move": (ANIM_MOVE_MS, "move"),
            "insert": (ANIM_APPEAR_MS, "appear"),
        }
        if event not in mapping:
            return
        ms, tname = mapping[event]
        dur = ms / 1000.0
        if event == "insert" and payload.get("index") is None:
            payload["index"] = len(getattr(self.heap, "data", [])) - 1
        self.anim_queue.append({"type": tname, "dur": dur, "payload": payload})

    # ----- рендер -----
    def draw(self):
        dirty = []

        # 1. Панель (рендерим только если изменялась)
        if self.toolbar_needs_redraw:
            self._draw_toolbar(self.toolbar_surface)
            self.toolbar_needs_redraw = False
            dirty.append(self.toolbar_surface.get_rect())

        # 2. Основная область
        array_dirty = self._update_and_draw_array_view()
        if array_dirty:
            dirty.append(array_dirty)

        # 3. Инфо-текст
        info_rect = self._draw_info_text()
        dirty.append(info_rect)

        # Финальный blit — только dirty области
        for rect in dirty:
            self.screen.blit(self.toolbar_surface, rect, rect)

    def _draw_toolbar(self, surface):
        surface.fill(PANEL_BG)
        for btn in self.buttons:
            rect = btn["rect"]
            enabled = self._is_enabled(btn)
            if not enabled:
                bg = BTN_BG_DISABLED
            elif self._hover_btn is btn:
                bg = BTN_BG_HOVER
            else:
                bg = BTN_BG
            pygame.draw.rect(surface, bg, rect, border_radius=6)
            label_surf = self.font.render(btn["label"], True, TEXT_COLOR)
            surface.blit(label_surf, (rect.x + 12, rect.y + 4))

        # ----- Поле ввода -----
        pygame.draw.rect(
            surface,
            (160, 160, 160) if self.input_active else INPUT_BG,
            self.input_rect,
            border_radius=6,
        )
        placeholder = self.input_text or "Type number…"
        ph_color = (200, 200, 200) if self.input_text else (130, 130, 150)
        txt = self.small.render(placeholder, True, ph_color)
        surface.blit(txt, (self.input_rect.x + 8, self.input_rect.y + 6))

        # ----- Кнопка Insert -----
        self.insert_btn_rect = pygame.Rect(self.input_rect.right + 8, self.input_rect.y, 90, 28)
        btn_bg = BTN_BG if self.input_text else BTN_BG_DISABLED
        pygame.draw.rect(surface, btn_bg, self.insert_btn_rect, border_radius=6)
        label = self.font.render("Insert", True, TEXT_COLOR)
        surface.blit(label, (self.insert_btn_rect.x + 16, self.insert_btn_rect.y + 4))

    def _update_and_draw_array_view(self):
        """Рисуем бары только если heap изменился или идёт анимация."""
        values = getattr(self.heap, "data", [])
        if not values:
            self.bars_layer.fill((0, 0, 0, 0))
            msg = self.font.render("Heap is empty. Use Insert or type a number ↑", True, (180, 180, 200))
            self.screen.blit(msg, (WIDTH // 2 - msg.get_width() // 2, HEIGHT // 2 - msg.get_height() // 2))
            return msg.get_rect()

        top = PANEL_H + 10
        available_h = HEIGHT - top - 50
        vmax = max(abs(v) for v in values) or 1
        scale = max(1, available_h // (vmax * 3))
        bar_width = max(16, WIDTH // max(10, len(values)))
        base_y = top + int(available_h * 0.9)

        # Продвинем анимацию
        prev_anim = bool(self.current_anim)
        self._advance_animation()

        if prev_anim or self.current_anim or self.anim_queue:
            self.bars_layer.fill((0, 0, 0, 0))  # перерисовка при движении
        else:
            # если heap не изменялся — не перерисовываем
            return self.bars_layer.get_rect()

        vmin, vmax_val = min(values), max(values)
        exclude = set()
        if self.current_anim:
            p = self.current_anim["payload"]
            exclude = {p.get("i"), p.get("j"), p.get("dst"), p.get("index")} - {None}

        for i, val in enumerate(values):
            if i in exclude:
                continue
            x = i * bar_width + 10
            height = abs(val) * scale * 3
            y = base_y - height if val >= 0 else base_y
            alpha = self._alpha_for_value(val, vmin, vmax_val)
            color = COMPARE_COLOR if (self.highlight_pair and i in self.highlight_pair) else BAR_COLOR
            pygame.draw.rect(self.bars_layer, (*color, alpha), pygame.Rect(x, y, bar_width - 4, height))
            label = self.small.render(str(val), True, TEXT_COLOR)
            self.bars_layer.blit(label, (x + (bar_width - label.get_width()) // 2, base_y + 6))

        self.screen.blit(self.bars_layer, (0, 0))

        if self.current_anim:
            self._draw_active_overlay(values, bar_width, scale, base_y)

        return self.bars_layer.get_rect()

    def _alpha_for_value(self, val, vmin, vmax) -> int:
        if vmax == vmin:
            return 255
        t = (val - vmin) / (vmax - vmin)
        return 128 + int(t * 127)

    # ----- Анимации -----
    def _draw_active_overlay(self, values, bar_width, scale, base_y):
        t = self.current_anim
        kind = t["type"]
        p = t["payload"]
        progress = self._anim_progress(t)

        self.overlay.fill((0, 0, 0, 0))

        def draw_bar(x, val, color, alpha=GHOST_ALPHA):
            height = abs(val) * scale * 3
            y = base_y - height if val >= 0 else base_y
            rect = pygame.Rect(int(x), int(y), bar_width - 4, height)
            pygame.draw.rect(self.overlay, (*color, alpha), rect)
            label = self.small.render(str(val), True, TEXT_COLOR)
            self.overlay.blit(label, (rect.x + (bar_width - label.get_width()) // 2, base_y + 6))

        if kind == "swap":
            i, j = p["i"], p["j"]
            ai, aj = p["ai"], p["aj"]
            xi, xj = i * bar_width + 10, j * bar_width + 10
            draw_bar(xi + (xj - xi) * progress, ai, SWAP_COLOR)
            draw_bar(xj + (xi - xj) * progress, aj, SWAP_COLOR)
        elif kind == "move":
            src, dst, val = p["src"], p["dst"], p["value"]
            xs, xd = src * bar_width + 10, dst * bar_width + 10
            draw_bar(xs + (xd - xs) * progress, val, MOVE_COLOR)
        elif kind == "appear":
            idx, val = p["index"], p["value"]
            draw_bar(idx * bar_width + 10, val, APPEAR_COLOR, int(GHOST_ALPHA * progress))

        self.screen.blit(self.overlay, (0, 0))

    def _advance_animation(self):
        now = time.perf_counter()
        if self.highlight_pair and now >= self.highlight_end:
            self.highlight_pair = None

        if not self.current_anim and self.anim_queue:
            item = self.anim_queue.pop(0)
            item["t0"] = now
            if item["type"] == "compare":
                i, j = item["payload"]["i"], item["payload"]["j"]
                self.highlight_pair = {i, j}
                self.highlight_end = now + item["dur"]
            else:
                self.current_anim = item
            return

        if self.current_anim and self._anim_progress(self.current_anim) >= 1.0:
            self.current_anim = None

    @staticmethod
    def _anim_progress(anim):
        span = anim["dur"]
        if span <= 0:
            return 1.0
        return min(1.0, (time.perf_counter() - anim["t0"]) / span)

    # ----- Инфо -----
    def _draw_info_text(self):
        mode = "Min-Heap" if self.heap.min_heap else "Max-Heap"
        info = self.font.render(f"[I] InsertRand  [P] Pop  [M] Toggle  [R] Reset   ({mode})", True, TEXT_COLOR)
        status_y = HEIGHT - 62
        info_y = HEIGHT - 36
        self.screen.blit(info, (20, info_y))

        ok = True
        if hasattr(self.heap, "is_valid_heap"):
            try:
                ok = self.heap.is_valid_heap()
            except Exception:
                ok = False
        status_text = "HEAP OK" if ok else "HEAP BROKEN"
        status_color = ACCENT_OK if ok else ACCENT_BAD
        status = self.font.render(status_text, True, status_color)
        self.screen.blit(status, (20, status_y))
        return pygame.Rect(0, status_y, WIDTH, 72)
