import pygame
import random
import time
from settings import *


class UI:
    def __init__(self, screen, heap):
        """
        Инициализация UI.

        - Создаёт кешируемые поверхности:
          - toolbar_surface: верхняя панель с кнопками и инпутом; перерисовывается только при изменениях.
          - bars_surface: слой с барами и подписями значений кучи.
          - overlay: временный слой поверх bars_surface для анимаций (swap/move/appear).
        - Хранит snapshot кучи, чтобы понять, нужно ли перерисовывать bars_surface.
        - Настраивает состояние UI: кнопки, поле ввода, hover и т.д.
        - Настраивает очередь анимаций (anim_queue), текущую анимацию (current_anim),
          и подсветку compare (highlight_pair / highlight_end).
        - Подписывается на события кучи через set_observer, если он есть.
        """
        self.screen = screen
        self.heap = heap
        self.font = pygame.font.SysFont("consolas", 20)
        self.small = pygame.font.SysFont("consolas", 16)

        # кешируемые слои
        self.toolbar_surface = pygame.Surface((WIDTH, PANEL_H), pygame.SRCALPHA)
        self.toolbar_needs_redraw = True
        self.bars_surface = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        self.overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)

        # snapshot значений кучи (tuple), чтобы отслеживать изменения
        self._last_values_snapshot = tuple()

        # состояние UI
        self.buttons = []
        self._build_buttons()

        self.input_rect = pygame.Rect(20, 44, 160, 28)
        self.input_active = False
        self.input_text = ""

        self.insert_btn_rect = None
        self._hover_btn = None

        # состояние анимаций
        self.anim_queue = []
        self.current_anim = None
        self.highlight_pair = None
        self.highlight_end = 0

        # подписка на ивенты кучи
        if hasattr(self.heap, "set_observer"):
            self.heap.set_observer(self._on_heap_event)

    def _build_buttons(self):
        """
        Перестраивает массив кнопок на тулбаре:
        - "Insert Rand": вставка случайного значения.
        - "To Max-Heap"/"To Min-Heap": переключение режима.
        - "Pop": удалить корень.
        - "Reset": очистить кучу.

        Каждой кнопке задаётся прямоугольник (rect) для клика.

        Вызывается также после смены режима (toggle), чтобы обновить подписи.
        Помечает тулбар как "нуждающийся в перерисовке".
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
            w, _ = self.font.size(label)
            rect = pygame.Rect(x, y, w + 24, 28)
            self.buttons.append({"rect": rect, "label": label, "action": action})
            x += rect.width + 10

        self.toolbar_needs_redraw = True

    def _toggle_label(self):
        """
        Возвращает подпись для кнопки переключения режима кучи.
        Если сейчас min_heap=True → предлагаем перейти в Max-Heap.
        И наоборот.
        """
        return "To Max-Heap" if self.heap.min_heap else "To Min-Heap"

    def handle_event(self, event):
        """
        Обрабатывает события Pygame уровня UI:
        - MOUSEMOTION:
            подсвечивает кнопку под курсором (hover), только если она активна;
            если hover поменялся → тулбар помечается на перерисовку.
        - MOUSEBUTTONDOWN (ЛКМ):
            1) клик по кнопке Insert рядом с полем ввода вставляет введённое число.
            2) клик по полю ввода активирует/деактивирует фокус (input_active).
            3) клик по обычным кнопкам ("Pop", "Reset", и т.п.) вызывает _run_action.
        - KEYDOWN:
            если у инпута есть фокус → символы уходят в _handle_text_input;
            иначе используются хоткеи (_handle_shortcuts).
        """
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
            # клик по маленькой кнопке Insert рядом с полем ввода
            if self.insert_btn_rect and self.insert_btn_rect.collidepoint(event.pos):
                if self.input_text:
                    self._insert_from_input()
                    self.toolbar_needs_redraw = True
                return

            # переключение фокуса ввода
            was_active = self.input_active
            self.input_active = self.input_rect.collidepoint(event.pos)
            if self.input_active != was_active:
                self.toolbar_needs_redraw = True

            # клики по остальным кнопкам тулбара
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
        """
        Горячие клавиши:
        I → insert_rand
        P → pop
        M → toggle_mode
        R → reset

        После выполнения некоторых действий (например, toggle_mode)
        тулбар может нуждаться в перерисовке, поэтому помечаем его.
        """
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
        """
        Обработка ввода текста в поле инпута:

        - ENTER: попытаться вставить число из инпута в кучу (push).
        - BACKSPACE: удалить последний символ.
        - ESC: снять фокус с инпута.
        - Любой другой ввод:
            принимаются цифры и один ведущий минус.
            длина ограничена (6 символов).
        После любого изменения текста тулбар надо перерисовать.
        """
        if event.key == pygame.K_RETURN:
            self._insert_from_input()
        elif event.key == pygame.K_BACKSPACE:
            self.input_text = self.input_text[:-1]
        elif event.key == pygame.K_ESCAPE:
            self.input_active = False
        else:
            ch = event.unicode
            # разрешаем "-" только в начале
            if (ch.isdigit() or (ch == "-" and not self.input_text)) and len(self.input_text) < 6:
                self.input_text += ch

        self.toolbar_needs_redraw = True

    def _run_action(self, action: str):
        """
        Выполняет семантику кнопок/хоткеев:

        - insert_rand:
            push случайного int [1..99] в кучу.
        - toggle_mode:
            если у кучи есть метод toggle_mode() → вызываем его;
            иначе инвертируем флаг min_heap вручную и вызываем heapify(), если есть.
        - pop:
            pop() из кучи (если она не пустая).
        - reset:
            clear() кучи.

        В конце пересобирает кнопки (_build_buttons),
        т.к. подпись toggle может поменяться, и тулбар нужно перерисовать.
        """
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
        """
        Пробует преобразовать текст из self.input_text в число и добавить в кучу:
        - Парсит int.
        - Кладёт его в диапазон [-10000, 10000].
        - Вызывает heap.push(v).
        После успешной (или неуспешной) попытки:
        - очищает поле,
        - снимает фокус.
        """
        try:
            v = int(self.input_text)
            v = max(-10_000, min(10_000, v))
            self.heap.push(v)
        except ValueError:
            pass
        self.input_text = ""
        self.input_active = False

    def _is_enabled(self, btn) -> bool:
        """
        Возвращает False для кнопки Pop, если куча пустая.
        Остальные кнопки всегда активны.
        """
        return not (btn["action"] == "pop" and len(self.heap) == 0)

    def _on_heap_event(self, event: str, payload: dict):
        """
        Колбэк-наблюдатель, вызывается кучей (heap.set_observer -> self._on_heap_event).

        Куча репортит события:
        - "compare": подсветка сравниваемых индексов.
        - "swap":    анимация обмена значений двух индексов.
        - "move":    анимация перемещения значения src→dst.
        - "insert":  анимация появления нового значения.

        Мы транслируем это в очередь анимаций self.anim_queue:
        кладём dict с:
            "type"  (compare/swap/move/appear),
            "dur"   (продолжительность в секундах),
            "payload" (данные, например индексы и значения).

        Для insert, если не указан index, считаем что это последний элемент.
        """
        mapping = {
            "compare": (ANIM_COMPARE_MS, "compare"),
            "swap": (ANIM_SWAP_MS, "swap"),
            "move": (ANIM_MOVE_MS, "move"),
            "insert": (ANIM_APPEAR_MS, "appear"),
        }
        if event not in mapping:
            return

        ms, visual_type = mapping[event]
        dur = ms / 1000.0

        p = payload.copy()
        if event == "insert" and p.get("index") is None:
            p["index"] = len(getattr(self.heap, "data", [])) - 1

        self.anim_queue.append({
            "type": visual_type,
            "dur": dur,
            "payload": p,
        })

    def draw(self):
        """
        Главный публичный рендер-метод. Вызывается каждый кадр.

        Логика перерисовки оптимизирована так:
        - Верхняя панель (toolbar_surface) перерисовывается только если был флаг toolbar_needs_redraw.
        - bars_surface (бары) перерисовывается И только тогда, когда изменилась куча,
          или запустилась/изменилась анимация, или активна подсветка compare.

        Порядок финального бленда на экран:
        1. bars_surface
        2. toolbar_surface
        3. текст статуса/хоткеев снизу (рисуется сразу в self.screen)
        """
        if self.toolbar_needs_redraw:
            self._redraw_toolbar()

        self._redraw_bars_if_needed()

        self.screen.blit(self.bars_surface, (0, 0))
        self.screen.blit(self.toolbar_surface, (0, 0))
        self._draw_info_text()

    def _redraw_toolbar(self):
        """
        Полная перерисовка поверхности тулбара (toolbar_surface):
        - фон панели,
        - кнопки (состояния normal/hover/disabled),
        - поле ввода числа,
        - кнопка Insert справа от поля ввода.

        Также обновляет self.insert_btn_rect.
        В конце снимает флаг toolbar_needs_redraw.
        """
        surf = self.toolbar_surface
        surf.fill(PANEL_BG)

        # кнопки
        for btn in self.buttons:
            rect = btn["rect"]
            if not self._is_enabled(btn):
                bg = BTN_BG_DISABLED
            elif self._hover_btn is btn:
                bg = BTN_BG_HOVER
            else:
                bg = BTN_BG

            pygame.draw.rect(surf, bg, rect, border_radius=6)
            label_surf = self.font.render(btn["label"], True, TEXT_COLOR)
            surf.blit(label_surf, (rect.x + 12, rect.y + 4))

        # поле ввода
        pygame.draw.rect(
            surf,
            (160, 160, 160) if self.input_active else INPUT_BG,
            self.input_rect,
            border_radius=6,
        )

        placeholder = self.input_text or "Type number…"
        ph_color = (200, 200, 200) if self.input_text else (130, 130, 150)
        txt = self.small.render(placeholder, True, ph_color)
        surf.blit(txt, (self.input_rect.x + 8, self.input_rect.y + 6))

        # кнопка Insert рядом с инпутом
        self.insert_btn_rect = pygame.Rect(self.input_rect.right + 8, self.input_rect.y, 90, 28)
        btn_bg = BTN_BG if self.input_text else BTN_BG_DISABLED
        pygame.draw.rect(surf, btn_bg, self.insert_btn_rect, border_radius=6)
        label = self.font.render("Insert", True, TEXT_COLOR)
        surf.blit(label, (self.insert_btn_rect.x + 16, self.insert_btn_rect.y + 4))

        self.toolbar_needs_redraw = False

    def _redraw_bars_if_needed(self):
        """
        Обновляет bars_surface при необходимости.

        bars_surface перерисовывается, если:
        - Данные кучи изменились с прошлого кадра.
        - Идёт анимация (или только что началась/закончилась).
        - Есть активная подсветка compare (highlight_pair) или она только что пропала.
        - Куча стала пустой (иначе могли остаться старые бары).

        Шаги:
        1. Берём snapshot массива heap.data.
        2. Продвигаем анимацию (_advance_animation), это может повлиять на подсветку/overlay.
        3. Проверяем, надо ли перерисовывать и, если надо, вызываем _draw_bars_surface(values).
        4. Обновляем snapshot.
        """
        values = getattr(self.heap, "data", [])
        values_snapshot = tuple(values)

        before_anim_state = (self.current_anim, bool(self.highlight_pair))
        self._advance_animation()
        after_anim_state = (self.current_anim, bool(self.highlight_pair))

        anim_active = bool(self.current_anim or self.anim_queue or self.highlight_pair)

        heap_changed = (values_snapshot != self._last_values_snapshot)
        anim_state_changed = (before_anim_state != after_anim_state)

        if not values or heap_changed or anim_active or anim_state_changed:
            self._draw_bars_surface(values)

        self._last_values_snapshot = values_snapshot

    def _draw_bars_surface(self, values):
        """
        Перерисовывает bars_surface с нуля и, при наличии активной анимации,
        рисует движущиеся бары на overlay и наслаивает overlay.

        Поведение:
        - Если куча пустая → пишем подсказку по центру.
        - Иначе для каждого значения рисуется вертикальная колонка:
            * высота зависит от |val|
            * цвет и прозрачность зависят от значения
            * индексы, участвующие в активной анимации (swap/move/appear),
              на основном слое не рисуются — они пойдут на overlay.
        - Рисуем базовую линию оси X.
        """
        surf = self.bars_surface
        surf.fill((0, 0, 0, 0))

        if not values:
            msg = self.font.render(
                "Heap is empty. Use Insert or type a number ↑",
                True,
                (180, 180, 200),
            )
            surf.blit(
                msg,
                (WIDTH // 2 - msg.get_width() // 2,
                 HEIGHT // 2 - msg.get_height() // 2),
            )
            return

        top = PANEL_H + 10
        available_h = HEIGHT - top - 50

        vmax_abs = max(abs(v) for v in values) or 1
        scale = max(1, available_h // (vmax_abs * 3))

        bar_width = max(16, WIDTH // max(10, len(values)))

        base_y = top + int(available_h * 0.9)

        self.overlay.fill((0, 0, 0, 0))

        exclude = set()
        if self.current_anim:
            p = self.current_anim["payload"]
            exclude = {
                p.get("i"),
                p.get("j"),
                p.get("dst"),
                p.get("index"),
            } - {None}

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
            bar_rect = pygame.Rect(x, y, bar_width - 4, height)
            pygame.draw.rect(surf, (*base_color, alpha), bar_rect)

            label = self.small.render(str(val), True, TEXT_COLOR)
            surf.blit(
                label,
                (x + (bar_width - label.get_width()) // 2, base_y + 6),
            )

        pygame.draw.line(
            surf,
            (90, 90, 110),
            (10, base_y),
            (WIDTH - 10, base_y),
            1,
        )

        if self.current_anim:
            self._draw_active_overlay_onto_overlay(values, bar_width, scale, base_y)
            surf.blit(self.overlay, (0, 0))

    def _alpha_for_value(self, val, vmin, vmax) -> int:
        """
        Возвращает альфа-канал (прозрачность) бара для значения val.
        Диапазон 128..255, линейно относительно минимума/максимума кучи.
        Если весь массив одинаковый → 255.
        """
        if vmax == vmin:
            return 255
        t = (val - vmin) / (vmax - vmin)
        return 128 + int(t * 127)

    def _draw_active_overlay_onto_overlay(self, values, bar_width, scale, base_y):
        """
        Рисует "летящие" бары текущей анимации (swap/move/appear)
        на self.overlay.

        Логика:
        - swap: два индекса i и j обмениваются позициями.
        - move: один бар переезжает с src на dst.
        - appear: новый бар появляется с нарастающей прозрачностью.

        После отрисовки overlay потом накладывается на bars_surface.
        """
        t = self.current_anim
        kind = t["type"]
        p = t["payload"]
        progress = self._anim_progress(t)

        def draw_bar(x, val, color, alpha=GHOST_ALPHA):
            height = abs(val) * scale * 3
            y = base_y - height if val >= 0 else base_y
            rect = pygame.Rect(int(x), int(y), bar_width - 4, height)

            pygame.draw.rect(self.overlay, (*color, alpha), rect)
            label = self.small.render(str(val), True, TEXT_COLOR)
            self.overlay.blit(
                label,
                (rect.x + (bar_width - label.get_width()) // 2, base_y + 6),
            )

        if kind == "swap":
            i, j = p["i"], p["j"]
            ai, aj = p["ai"], p["aj"]
            xi = i * bar_width + 10
            xj = j * bar_width + 10
            draw_bar(xi + (xj - xi) * progress, ai, SWAP_COLOR)
            draw_bar(xj + (xi - xj) * progress, aj, SWAP_COLOR)

        elif kind == "move":
            src, dst, val = p["src"], p["dst"], p["value"]
            xs = src * bar_width + 10
            xd = dst * bar_width + 10
            draw_bar(xs + (xd - xs) * progress, val, MOVE_COLOR)

        elif kind == "appear":
            idx, val = p["index"], p["value"]
            x = idx * bar_width + 10
            alpha = int(GHOST_ALPHA * progress)
            draw_bar(x, val, APPEAR_COLOR, alpha=alpha)

    def _advance_animation(self):
        """
        Продвигает очередь анимаций и управляет состоянием подсветки сравнения.

        Поведение:
        - highlight_pair (подсветка compare) живёт до highlight_end.
        - Если сейчас нет активной анимации current_anim, но есть anim_queue:
            * Если это compare → просто ставим highlight_pair и таймер, а current_anim не запускаем.
            * Иначе запускаем анимацию и сохраняем её как current_anim (с t0=now).
        - Если current_anim есть и прогресс >= 1.0 → завершаем (current_anim = None).
        """
        now = time.perf_counter()

        # убрать compare-подсветку по таймеру
        if self.highlight_pair and now >= self.highlight_end:
            self.highlight_pair = None

        # если анимации нет — пробуем взять следующую
        if not self.current_anim and self.anim_queue:
            item = self.anim_queue.pop(0)
            item["t0"] = now
            if item["type"] == "compare":
                i, j = item["payload"]["i"], item["payload"]["j"]
                self.highlight_pair = {i, j}
                self.highlight_end = now + item["dur"]
                self.current_anim = None
            else:
                self.current_anim = item
            return

        # если анимация есть — проверяем, не закончилась ли
        if self.current_anim:
            if self._anim_progress(self.current_anim) >= 1.0:
                self.current_anim = None

    @staticmethod
    def _anim_progress(anim):
        """
        Возвращает прогресс анимации [0..1] на основе perf_counter().
        Если длительность <= 0 — сразу считаем анимацию завершённой.
        """
        span = anim["dur"]
        if span <= 0:
            return 1.0
        return min(1.0, (time.perf_counter() - anim["t0"]) / span)

    def _draw_info_text(self):
        """
        Рисует внизу экрана (на self.screen, не на кешированных слоях):
        - хоткеи [I/P/M/R] и текущий режим (Min-Heap / Max-Heap),
        - статус "HEAP OK" или "HEAP BROKEN" с цветовой индикацией,
          причём корректность проверяется через heap.is_valid_heap(), если метод есть.
        """
        mode = "Min-Heap" if self.heap.min_heap else "Max-Heap"
        info = self.font.render(
            f"[I] InsertRand  [P] Pop  [M] Toggle  [R] Reset   ({mode})",
            True,
            TEXT_COLOR,
        )

        status_ok = True
        if hasattr(self.heap, "is_valid_heap"):
            try:
                status_ok = self.heap.is_valid_heap()
            except Exception:
                status_ok = False

        status_text = "HEAP OK" if status_ok else "HEAP BROKEN"
        status_color = ACCENT_OK if status_ok else ACCENT_BAD
        status = self.font.render(status_text, True, status_color)

        self.screen.blit(status, (20, HEIGHT - 62))
        self.screen.blit(info, (20, HEIGHT - 36))
