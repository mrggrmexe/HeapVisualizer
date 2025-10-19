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

        # Кнопки
        self.buttons = []
        self._build_buttons()

        # Поле ввода
        self.input_rect = pygame.Rect(20, 44, 160, 28)
        self.input_active = False
        self.input_text = ""

        # Hover
        self._hover_btn = None
        self.insert_btn_rect = None

        # ----- АНИМАЦИИ -----
        self.anim_queue = []
        self.current_anim = None
        self.highlight_pair = None
        self.highlight_end = 0

        self.overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)

        if hasattr(self.heap, "set_observer"):
            self.heap.set_observer(self._on_heap_event)

    # ---------- построение кнопок ----------
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
            if self.insert_btn_rect and self.insert_btn_rect.collidepoint(event.pos):
                if self.input_text:
                    self._insert_from_input()
                return

            if self.input_rect.collidepoint(event.pos):
                self.input_active = True
            else:
                self.input_active = False

            for btn in self.buttons:
                if btn["rect"].collidepoint(event.pos) and self._is_enabled(btn):
                    self._run_action(btn["action"])
                    break

        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_i:
                self._run_action("insert_rand")
            elif event.key == pygame.K_p:
                self._run_action("pop")
            elif event.key == pygame.K_m:
                self._run_action("toggle_mode")
            elif event.key == pygame.K_r:
                self._run_action("reset")

            if self.input_active:
                if event.key == pygame.K_RETURN:
                    self._insert_from_input()
                elif event.key == pygame.K_BACKSPACE:
                    self.input_text = self.input_text[:-1]
                else:
                    ch = event.unicode
                    if ch.isdigit() and len(self.input_text) < 6:
                        self.input_text += ch

    def _run_action(self, action: str):
        if action == "insert_rand":
            value = random.randint(1, 99)
            self.heap.push(value)
        elif action == "toggle_mode":
            if hasattr(self.heap, "toggle_mode"):
                self.heap.toggle_mode()
            else:
                self.heap.min_heap = not self.heap.min_heap
                if hasattr(self.heap, "heapify"):
                    self.heap.heapify()
        elif action == "pop":
            if len(self.heap) > 0:
                self.heap.pop()
        elif action == "reset":
            self.heap.clear()

        self._build_buttons()

    def _insert_from_input(self):
        if self.input_text:
            try:
                val = int(self.input_text)
                val = max(-10_000, min(10_000, val))
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

    # ---------- OBSERVER ----------
    def _on_heap_event(self, event: str, payload: dict):
        if event == "compare":
            i = payload.get("i")
            j = payload.get("j")
            self.anim_queue.append({
                "type": "compare",
                "dur": ANIM_COMPARE_MS / 1000.0,
                "payload": {"i": i, "j": j}
            })
        elif event == "swap":
            i = payload.get("i")
            j = payload.get("j")
            ai = payload.get("ai")
            aj = payload.get("aj")
            self.anim_queue.append({
                "type": "swap",
                "dur": ANIM_SWAP_MS / 1000.0,
                "payload": {"i": i, "j": j, "ai": ai, "aj": aj}
            })
        elif event == "move":
            src = payload.get("src")
            dst = payload.get("dst")
            value = payload.get("value")
            self.anim_queue.append({
                "type": "move",
                "dur": ANIM_MOVE_MS / 1000.0,
                "payload": {"src": src, "dst": dst, "value": value}
            })
        elif event == "insert":
            idx = payload.get("index")
            val = payload.get("value")
            if idx is None:
                idx = len(getattr(self.heap, "data", [])) - 1
            self.anim_queue.append({
                "type": "appear",
                "dur": ANIM_APPEAR_MS / 1000.0,
                "payload": {"index": idx, "value": val}
            })

    # ---------- отрисовка ----------
    def draw(self):
        self._draw_toolbar()
        self._update_and_draw_array_view()
        self._draw_info_text()

    def _draw_toolbar(self):
        pygame.draw.rect(self.screen, PANEL_BG, (0, 0, WIDTH, PANEL_H))

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

        self.insert_btn_rect = pygame.Rect(self.input_rect.right + 8, self.input_rect.y, 90, 28)
        btn_bg = BTN_BG if self.input_text else BTN_BG_DISABLED
        pygame.draw.rect(self.screen, btn_bg, self.insert_btn_rect, border_radius=6)
        label = self.font.render("Insert", True, TEXT_COLOR)
        self.screen.blit(label, (self.insert_btn_rect.x + 16, self.insert_btn_rect.y + 4))

    # ---------- Прозрачность баров ----------
    def _alpha_for_value(self, val, vmin, vmax) -> int:
        if vmax == vmin:
            return 255
        t = (val - vmin) / (vmax - vmin)
        return 128 + int(t * (255 - 128))  # 50%..100%

    # ---------- отрисовка баров и анимаций ----------
    def _update_and_draw_array_view(self):
        values = getattr(self.heap, "data", [])
        if not values:
            msg = self.font.render("Heap is empty. Use Insert or type a number ↑", True, (180, 180, 200))
            self.screen.blit(msg, (WIDTH // 2 - msg.get_width() // 2, HEIGHT // 2 - msg.get_height() // 2))
            return

        top = PANEL_H + 10
        available_h = HEIGHT - top - 50
        vmax = max(abs(v) for v in values) or 1
        scale = max(1, available_h // (vmax * 3))
        bar_width = max(16, WIDTH // max(10, len(values)))
        base_y = top + int(available_h * 0.9)

        self.overlay.fill((0, 0, 0, 0))
        self._advance_animation()

        exclude = set()
        if self.current_anim:
            t = self.current_anim
            if t["type"] == "swap":
                exclude.update([t["payload"]["i"], t["payload"]["j"]])
            elif t["type"] == "move":
                exclude.update([t["payload"]["dst"]])
            elif t["type"] == "appear":
                exclude.update([t["payload"]["index"]])

        prev_clip = self.screen.get_clip()
        clip_rect = pygame.Rect(0, top, WIDTH, available_h)
        self.screen.set_clip(clip_rect)

        bars_layer = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        vmin = min(values)
        vmax_val = max(values)

        for i, val in enumerate(values):
            if i in exclude:
                continue
            x = i * bar_width + 10
            height = abs(val) * scale * 3
            y = base_y - height if val >= 0 else base_y
            alpha = self._alpha_for_value(val, vmin, vmax_val)
            base_color = COMPARE_COLOR if (self.highlight_pair and i in self.highlight_pair) else BAR_COLOR
            color_with_alpha = (*base_color, alpha)
            pygame.draw.rect(bars_layer, color_with_alpha, pygame.Rect(x, y, bar_width - 4, height))

        self.screen.blit(bars_layer, (0, 0))

        for i, val in enumerate(values):
            if i in exclude:
                continue
            x = i * bar_width + 10
            label = self.small.render(str(val), True, TEXT_COLOR)
            self.screen.blit(label, (x + (bar_width - label.get_width()) // 2, base_y + 6))

        pygame.draw.line(self.screen, (90, 90, 110), (10, base_y), (WIDTH - 10, base_y), 1)

        if self.current_anim:
            self._draw_active_overlay(values, bar_width, scale, base_y)

        self.screen.set_clip(prev_clip)

    # ---------- Анимации ----------
    def _draw_active_overlay(self, values, bar_width, scale, base_y):
        t = self.current_anim
        kind = t["type"]
        p = t["payload"]
        progress = self._anim_progress(t)

        def draw_bar(x, val, color, alpha=GHOST_ALPHA):
            height = abs(val) * scale * 3
            y = base_y - height if val >= 0 else base_y
            rect = pygame.Rect(int(x), int(y), bar_width - 4, height)
            c = (*color, alpha)
            pygame.draw.rect(self.overlay, c, rect)
            label = self.small.render(str(val), True, TEXT_COLOR)
            self.overlay.blit(label, (rect.x + (bar_width - label.get_width()) // 2, base_y + 6))

        if kind == "swap":
            i, j = p["i"], p["j"]
            ai, aj = p["ai"], p["aj"]
            xi = i * bar_width + 10
            xj = j * bar_width + 10
            xi2 = xi + (xj - xi) * progress
            xj2 = xj + (xi - xj) * progress
            draw_bar(xi2, ai, SWAP_COLOR)
            draw_bar(xj2, aj, SWAP_COLOR)

        elif kind == "move":
            src, dst, val = p["src"], p["dst"], p["value"]
            xs = src * bar_width + 10
            xd = dst * bar_width + 10
            x2 = xs + (xd - xs) * progress
            draw_bar(x2, val, MOVE_COLOR)

        elif kind == "appear":
            idx, val = p["index"], p["value"]
            x = idx * bar_width + 10
            alpha = int(GHOST_ALPHA * progress)
            draw_bar(x, val, APPEAR_COLOR, alpha=alpha)

        self.screen.blit(self.overlay, (0, 0))

    # ---------- Тайминг ----------
    def _advance_animation(self):
        now = time.perf_counter()
        if self.highlight_pair and now >= self.highlight_end:
            self.highlight_pair = None

        if not self.current_anim and self.anim_queue:
            item = self.anim_queue.pop(0)
            item["t0"] = now
            self.current_anim = item
            if item["type"] == "compare":
                i, j = item["payload"]["i"], item["payload"]["j"]
                self.highlight_pair = {i, j}
                self.highlight_end = now + item["dur"]
                self.current_anim = None
            return

        if self.current_anim:
            if self._anim_progress(self.current_anim) >= 1.0:
                self.current_anim = None

    @staticmethod
    def _anim_progress(anim):
        if not anim:
            return 0.0
        span = anim["dur"]
        if span <= 0:
            return 1.0
        now = time.perf_counter()
        return max(0.0, min(1.0, (now - anim["t0"]) / span))

    # ---------- Инфо-текст ----------
    def _draw_info_text(self):
        mode = "Min-Heap" if self.heap.min_heap else "Max-Heap"
        info = self.font.render(f"[I] InsertRand  [P] Pop  [M] Toggle  [R] Reset   ({mode})", True, TEXT_COLOR)
        self.screen.blit(info, (20, HEIGHT - 36))

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
