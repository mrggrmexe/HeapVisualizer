import math
from dataclasses import dataclass

import pygame
import random
import time
from settings import *

@dataclass
class Button:
    rect: pygame.Rect
    label: str
    action: str

    def __getitem__(self, key):
        return getattr(self, key)

class UI:
    def __init__(self, screen, heap):
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

        self.input_rect = pygame.Rect(20, 94, 160, 28)
        self.input_active = False
        self.input_text = ""

        self.insert_btn_rect = None
        self._hover_btn = None

        # состояние анимаций
        self.anim_queue = []
        self.current_anim = None
        self.highlight_pair = None
        self.highlight_end = 0

        # новые состояния для расширенной функциональности
        self.temp_message = None
        self.message_end_time = 0
        self.destructive_iterating = False
        self.sorted_items = []

        # подписка на ивенты кучи
        if hasattr(self.heap, "set_observer"):
            self.heap.set_observer(self._on_heap_event)

    def _build_buttons(self):
        """Создаёт кнопки тулбара с защитой от ошибок в разметке."""

        # Базовый список кнопок — держим вне try, чтобы можно было
        # использовать его и в fallback-разметке
        labels = [
            ("Insert Rand", "insert_rand"),
            (self._toggle_label() if hasattr(self, "heap") and hasattr(self.heap, "min_heap") else "Toggle",
             "toggle_mode"),
            ("Pop", "pop"),
            ("PushPop", "pushpop"),
            ("Replace", "replace"),
            ("5 Largest", "nlargest"),
            ("Sort All", "sort_all"),
            ("Stats", "show_stats"),
            ("Reset", "reset"),
        ]

        # На всякий случай убеждаемся, что список кнопок существует
        if not hasattr(self, "buttons") or not isinstance(self.buttons, list):
            self.buttons = []
        else:
            self.buttons.clear()

        # Значения по умолчанию — пригодятся и в основном коде, и в fallback
        START_X = 20
        START_Y = 12
        PADDING_X = 12
        PADDING_Y = 6
        SPACING = 10

        # Безопасно определяем максимальную ширину строки
        max_width = None
        try:
            if hasattr(self, "toolbar_surface") and self.toolbar_surface is not None:
                max_width = max(100, int(self.toolbar_surface.get_width()) - 40)
            elif hasattr(self, "screen") and self.screen is not None:
                max_width = max(100, int(self.screen.get_width()) - 40)
        except Exception:
            pass

        # Фолбэк, если ничего не получилось
        if max_width is None:
            try:
                from settings import WIDTH  # может не существовать
                max_width = max(100, int(WIDTH) - 40)
            except Exception:
                max_width = 600  # последний вариант по умолчанию

        try:
            # Шрифт может быть неинициализирован
            font = getattr(self, "font", None)
            if font is None:
                # если по какой-то причине шрифт не создан
                font = pygame.font.SysFont("consolas", 20)
                self.font = font

            # определяем высоту строки
            sample_text_w, sample_text_h = font.size("Sample")
            button_height = sample_text_h + PADDING_Y * 2
            row_height = button_height + 5  # отступ между строками

            x = START_X
            y = START_Y
            current_width = 0

            for label, action in labels:
                # Страхуемся от странных значений
                label_str = str(label)
                action_str = str(action)

                try:
                    text_w, text_h = font.size(label_str)
                except Exception:
                    # если font.size упал – используем дефолтные размеры
                    text_w, text_h = 80, sample_text_h

                width = max(40, text_w + PADDING_X * 2)
                height = max(button_height, text_h + PADDING_Y * 2)

                # если кнопка слишком широкая – ограничим её
                if width > max_width:
                    width = max_width

                # перенос строки
                if current_width + width > max_width and current_width > 0:
                    y += row_height
                    x = START_X
                    current_width = 0

                rect = pygame.Rect(int(x), int(y), int(width), int(height))

                try:
                    self.buttons.append(Button(rect, label_str, action_str))
                except Exception:
                    # если конструктор Button упал – тихо пропустим эту кнопку
                    continue

                x += width + SPACING
                current_width += width + SPACING

            # Если вдруг не создалась ни одна кнопка — делаем простой вертикальный столбец
            if not self.buttons:
                y = START_Y
                default_w, default_h = 120, button_height
                for i, (label, action) in enumerate(labels):
                    rect = pygame.Rect(START_X, y + i * (default_h + 4), default_w, default_h)
                    self.buttons.append(Button(rect, str(label), str(action)))

                y = START_Y + len(labels) * (default_h + 4)
                row_height = default_h + 4

            # Поле ввода располагаем под последней строкой кнопок
            input_y = y + row_height + 10
            self.input_rect = pygame.Rect(START_X, int(input_y), 160, 28)

        except Exception as e:
            # Грубый fallback, чтобы приложение не упало вообще
            self.buttons = []
            y = START_Y
            default_w, default_h = 120, 32
            for i, (label, action) in enumerate(labels):
                rect = pygame.Rect(START_X, y + i * (default_h + 4), default_w, default_h)
                self.buttons.append(Button(rect, str(label), str(action)))

            self.input_rect = pygame.Rect(START_X, y + len(labels) * (default_h + 8), 160, 28)

            if hasattr(self, "_show_temp_message"):
                self._show_temp_message(f"Button layout error: {e}")

        # В любом случае просим перерисовать тулбар
        self.toolbar_needs_redraw = True

    def _toggle_label(self):
        return "To Max-Heap" if self.heap.min_heap else "To Min-Heap"

    def handle_event(self, event):
        # Безопасно достаём список кнопок и текущую кнопку под курсором
        buttons = getattr(self, "buttons", []) or []
        hover_btn = getattr(self, "_hover_btn", None)

        # Вспомогательные функции для работы с кнопками разных типов (dict / объект)
        def _get_btn_rect(btn):
            if isinstance(btn, dict):
                return btn.get("rect")
            return getattr(btn, "rect", None)

        def _get_btn_action(btn):
            if isinstance(btn, dict):
                return btn.get("action")
            return getattr(btn, "action", None)

        def _btn_enabled(btn):
            is_enabled = getattr(self, "_is_enabled", None)
            if callable(is_enabled):
                try:
                    return bool(is_enabled(btn))
                except Exception:
                    return False
            # если проверки нет — считаем кнопку включённой
            return True

        # Флаг перерисовки тулбара
        def _request_redraw():
            try:
                self.toolbar_needs_redraw = True
            except Exception:
                # если вдруг у self нет такого атрибута
                setattr(self, "toolbar_needs_redraw", True)

        if event.type == pygame.MOUSEMOTION:
            new_hover = None
            for btn in buttons:
                rect = _get_btn_rect(btn)
                if rect is None or not hasattr(rect, "collidepoint"):
                    continue
                try:
                    if rect.collidepoint(event.pos) and _btn_enabled(btn):
                        new_hover = btn
                        break
                except Exception:
                    # если вдруг event.pos не тот или collidepoint сломался — пропускаем
                    continue

            if new_hover is not hover_btn:
                self._hover_btn = new_hover
                _request_redraw()

        elif event.type == pygame.MOUSEBUTTONDOWN and getattr(event, "button", None) == 1:
            # Кнопка Insert
            insert_rect = getattr(self, "insert_btn_rect", None)
            if insert_rect is not None and hasattr(insert_rect, "collidepoint"):
                try:
                    if insert_rect.collidepoint(event.pos):
                        if getattr(self, "input_text", ""):
                            if hasattr(self, "_insert_from_input"):
                                try:
                                    self._insert_from_input()
                                except Exception:
                                    pass
                            _request_redraw()
                        return
                except Exception:
                    # Не даём обработчику упасть из-за странных координат
                    pass

            # Поле ввода
            input_rect = getattr(self, "input_rect", None)
            was_active = getattr(self, "input_active", False)

            input_clicked = False
            if input_rect is not None and hasattr(input_rect, "collidepoint"):
                try:
                    input_clicked = input_rect.collidepoint(event.pos)
                except Exception:
                    input_clicked = False

            self.input_active = bool(input_clicked)
            if self.input_active != was_active:
                _request_redraw()

            # Кнопки тулбара
            for btn in buttons:
                rect = _get_btn_rect(btn)
                if rect is None or not hasattr(rect, "collidepoint"):
                    continue

                try:
                    if rect.collidepoint(event.pos) and _btn_enabled(btn):
                        action = _get_btn_action(btn)
                        if action is None:
                            return
                        # _run_action может быть как методом, так и чем-то ещё
                        run_action = getattr(self, "_run_action", None)
                        if callable(run_action):
                            try:
                                run_action(action)
                            except Exception:
                                # Не валим всё приложение из-за падения внутри обработчика
                                pass
                        return
                except Exception:
                    # Пропускаем кнопку, если что-то пошло не так
                    continue

        elif event.type == pygame.KEYDOWN:
            if getattr(self, "input_active", False):
                # Обработка текста в поле ввода
                handler = getattr(self, "_handle_text_input", None)
                if callable(handler):
                    try:
                        handler(event)
                    except Exception:
                        pass
            else:
                # Горячие клавиши
                handler = getattr(self, "_handle_shortcuts", None)
                if callable(handler):
                    try:
                        handler(event)
                    except Exception:
                        pass

    def _handle_shortcuts(self, event):
        """Добавлены горячие клавиши для новых функций"""
        keymap = {
            pygame.K_i: "insert_rand",
            pygame.K_p: "pop",
            pygame.K_t: "pushpop",
            pygame.K_e: "replace",
            pygame.K_l: "nlargest",
            pygame.K_s: "sort_all",
            pygame.K_d: "show_stats",
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
        """Безопасно выполняет действие тулбара по строковому идентификатору."""

        # Нормализуем действие
        action = str(action) if action is not None else ""
        if not action:
            return

        heap = getattr(self, "heap", None)
        show_msg = getattr(self, "_show_temp_message", None)

        def warn(msg: str):
            if callable(show_msg):
                try:
                    show_msg(msg)
                except Exception:
                    pass

        if heap is None:
            warn(f"Heap is not initialized (action: {action})")
            return

        # Удобный способ безопасно проверить длину
        def safe_len(obj, default=0):
            try:
                return len(obj)
            except Exception:
                return default

        try:
            if action == "insert_rand":
                # heap.push может отсутствовать или быть некорректным
                push = getattr(heap, "push", None)
                if callable(push):
                    try:
                        import random
                        push(random.randint(1, 99))
                    except Exception as e:
                        warn(f"insert_rand failed: {e}")
                else:
                    warn("insert_rand: heap has no 'push' method")

            elif action == "toggle_mode":
                toggle = getattr(heap, "toggle_mode", None)
                if callable(toggle):
                    try:
                        toggle()
                    except Exception as e:
                        warn(f"toggle_mode failed: {e}")
                else:
                    # Фолбэк — ручное переключение флага min_heap
                    if hasattr(heap, "min_heap"):
                        try:
                            heap.min_heap = not bool(heap.min_heap)
                        except Exception as e:
                            warn(f"toggle_mode: cannot flip min_heap: {e}")

                        heapify = getattr(heap, "heapify", None)
                        if callable(heapify):
                            try:
                                heapify()
                            except Exception as e:
                                warn(f"toggle_mode: heapify failed: {e}")
                    else:
                        warn("toggle_mode: heap has no 'toggle_mode' and no 'min_heap'")

            elif action == "pop":
                if safe_len(heap) > 0:
                    pop_method = getattr(heap, "pop", None)
                    if callable(pop_method):
                        try:
                            pop_method()
                        except Exception as e:
                            warn(f"pop failed: {e}")
                    else:
                        warn("pop: heap has no 'pop' method")
                else:
                    # Тихо игнорируем, можно и сообщить:
                    # warn("Heap is empty")
                    pass

            elif action == "pushpop":
                if getattr(self, "input_text", ""):
                    handler = getattr(self, "_run_pushpop", None)
                    if callable(handler):
                        try:
                            handler()
                        except Exception as e:
                            warn(f"pushpop failed: {e}")
                    else:
                        warn("_run_pushpop handler is missing")
                else:
                    warn("pushpop: input is empty")

            elif action == "replace":
                if getattr(self, "input_text", ""):
                    handler = getattr(self, "_run_replace", None)
                    if callable(handler):
                        try:
                            handler()
                        except Exception as e:
                            warn(f"replace failed: {e}")
                    else:
                        warn("_run_replace handler is missing")
                else:
                    warn("replace: input is empty")

            elif action == "nlargest":
                handler = getattr(self, "_run_nlargest", None)
                if callable(handler):
                    try:
                        handler()
                    except Exception as e:
                        warn(f"nlargest failed: {e}")
                else:
                    warn("_run_nlargest handler is missing")

            elif action == "sort_all":
                handler = getattr(self, "_run_sort_all", None)
                if callable(handler):
                    try:
                        handler()
                    except Exception as e:
                        warn(f"sort_all failed: {e}")
                else:
                    warn("_run_sort_all handler is missing")

            elif action == "show_stats":
                handler = getattr(self, "_show_stats", None)
                if callable(handler):
                    try:
                        handler()
                    except Exception as e:
                        warn(f"show_stats failed: {e}")
                else:
                    warn("_show_stats handler is missing")

            elif action == "reset":
                # Очищаем кучу
                cleared = False
                clear_method = getattr(heap, "clear", None)
                if callable(clear_method):
                    try:
                        clear_method()
                        cleared = True
                    except Exception as e:
                        warn(f"reset: clear() failed: {e}")

                # Фолбэк, если clear() нет
                if not cleared and hasattr(heap, "data") and isinstance(heap.data, list):
                    try:
                        heap.data.clear()
                        cleared = True
                    except Exception as e:
                        warn(f"reset: data.clear() failed: {e}")

                if not cleared:
                    warn("reset: cannot clear heap")

                # Сброс остальных полей, если они есть
                try:
                    if hasattr(self, "destructive_iterating"):
                        self.destructive_iterating = False
                except Exception:
                    pass

                try:
                    if hasattr(self, "sorted_items"):
                        # если это список – очищаем, иначе просто перезаписываем
                        if isinstance(self.sorted_items, list):
                            self.sorted_items.clear()
                        else:
                            self.sorted_items = []
                except Exception:
                    pass

            else:
                # неизвестное действие
                warn(f"Unknown action: {action}")

        except Exception as e:
            # Грубый «страховочный» catch, чтобы вообще не упасть из-за логики выше
            warn(f"Action '{action}' failed with unexpected error: {e}")

        # В конце пробуем перестроить кнопки, но тоже безопасно
        rebuild = getattr(self, "_build_buttons", None)
        if callable(rebuild):
            try:
                rebuild()
            except Exception as e:
                warn(f"_build_buttons failed after action '{action}': {e}")
                # В крайнем случае просто просим перерисовку тулбара
                try:
                    self.toolbar_needs_redraw = True
                except Exception:
                    setattr(self, "toolbar_needs_redraw", True)
        else:
            # Если _build_buttons нет — хотя бы флаг перерисовки
            try:
                self.toolbar_needs_redraw = True
            except Exception:
                setattr(self, "toolbar_needs_redraw", True)

    def _run_pushpop(self):
        """Выполняет pushpop с введенным значением"""
        try:
            v = int(self.input_text)
            v = max(-10_000, min(10_000, v))
            if hasattr(self.heap, 'pushpop'):
                result = self.heap.pushpop(v)
                self._show_temp_message(f"PushPop: {v} → returned {result}")
            else:
                # Эмуляция pushpop если метод отсутствует
                result = self.heap.pop() if len(self.heap) > 0 else None
                self.heap.push(v)
                self._show_temp_message(f"PushPop emulated: {v} → returned {result}")
        except ValueError:
            pass
        self.input_text = ""
        self.input_active = False

    def _run_replace(self):
        """Выполняет replace с введенным значением"""
        try:
            v = int(self.input_text)
            v = max(-10_000, min(10_000, v))
            if hasattr(self.heap, 'replace'):
                result = self.heap.replace(v)
                self._show_temp_message(f"Replace: {v} → returned {result}")
            else:
                # Эмуляция replace если метод отсутствует
                if len(self.heap) > 0:
                    result = self.heap.pop()
                    self.heap.push(v)
                    self._show_temp_message(f"Replace emulated: {v} → returned {result}")
                else:
                    self.heap.push(v)
                    self._show_temp_message(f"Heap was empty, pushed: {v}")
        except ValueError:
            pass
        self.input_text = ""
        self.input_active = False

    def _run_nlargest(self):
        """Показывает 5 наибольших/наименьших элементов"""
        try:
            if hasattr(self.heap, 'nlargest'):
                items = self.heap.nlargest(5)
                heap_type = "Min" if self.heap.min_heap else "Max"
                self._show_temp_message(f"5 largest in {heap_type}-Heap: {items}")
            else:
                # Эмуляция nlargest
                temp = list(self.heap.data)
                temp.sort(reverse=not self.heap.min_heap)
                items = temp[:5]
                heap_type = "Min" if self.heap.min_heap else "Max"
                self._show_temp_message(f"5 largest in {heap_type}-Heap: {items}")
        except Exception as e:
            self._show_temp_message(f"Error: {str(e)}")

    def _run_sort_all(self):
        """Запускает/останавливает разрушающую сортировку"""
        if self.destructive_iterating:
            self.destructive_iterating = False
            self._show_temp_message("Sorting stopped")
        else:
            if hasattr(self.heap, 'destructive_iter'):
                self.destructive_iterating = True
                self.sorted_items = []
                self._show_temp_message("Sorting started - click again to stop")
            else:
                # Эмуляция destructive_iter
                temp = list(self.heap.data)
                temp.sort(reverse=not self.heap.min_heap)
                self._show_temp_message(f"Sorted: {temp}")

    def _show_stats(self):
        """Показывает статистику кучи"""
        try:
            if hasattr(self.heap, 'get_stats'):
                stats = self.heap.get_stats()
                messages = [
                    f"Size: {stats['size']}",
                    f"Depth: {stats['depth']}",
                    f"Mode: {stats['mode']}",
                    f"Valid: {stats['is_valid']}",
                    f"Perfect: {stats['is_perfect']}",
                    f"Operations: {stats['operations_count']}"
                ]
                self._show_temp_message("\n".join(messages))
            else:
                # Базовая статистика
                depth = int(math.log2(len(self.heap.data))) + 1 if self.heap.data else 0
                is_perfect = (len(self.heap.data) & (len(self.heap.data) + 1)) == 0
                messages = [
                    f"Size: {len(self.heap.data)}",
                    f"Depth: {depth}",
                    f"Mode: {'min' if self.heap.min_heap else 'max'}",
                    f"Perfect: {is_perfect}"
                ]
                self._show_temp_message("\n".join(messages))
        except Exception as e:
            self._show_temp_message(f"Stats error: {str(e)}")

    def _show_temp_message(self, message: str, duration: float = 3.0):
        """Показывает временное сообщение"""
        self.temp_message = message
        self.message_end_time = time.perf_counter() + duration

    def _insert_from_input(self):
        try:
            v = int(self.input_text)
            v = max(-10_000, min(10_000, v))
            self.heap.push(v)
        except ValueError:
            pass
        self.input_text = ""
        self.input_active = False

    def _is_enabled(self, btn) -> bool:
        """Добавлены проверки для новых кнопок"""
        if btn["action"] == "pop" and len(self.heap) == 0:
            return False
        if btn["action"] in ["pushpop", "replace"] and not self.input_text:
            return False
        if btn["action"] == "nlargest" and len(self.heap) == 0:
            return False
        if btn["action"] == "sort_all" and len(self.heap) == 0:
            return False
        return True

    def _on_heap_event(self, event: str, payload: dict):
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
        """Рендер кадра + безопасная поддержка разрушающей сортировки и временных сообщений."""

        # --- Безопасная обработка разрушающей сортировки ---
        try:
            if getattr(self, "destructive_iterating", False) \
                    and not getattr(self, "anim_queue", None) \
                    and not getattr(self, "current_anim", None):

                heap = getattr(self, "heap", None)

                if heap is not None and hasattr(heap, "destructive_iter") and len(heap) > 0:
                    try:
                        it = getattr(self, "_destructive_iter", None)
                        if it is None:
                            # создаём итератор только один раз
                            it = heap.destructive_iter()
                            self._destructive_iter = it

                        item = next(it)

                        if not hasattr(self, "sorted_items"):
                            self.sorted_items = []
                        self.sorted_items.append(item)

                    except StopIteration:
                        # сортировка завершена
                        self.destructive_iterating = False
                        if hasattr(self, "_destructive_iter"):
                            del self._destructive_iter

                        msg = f"Sorting complete! Sorted: {getattr(self, 'sorted_items', [])}"
                        if hasattr(self, "_show_temp_message"):
                            self._show_temp_message(msg)

                    except Exception as sort_err:
                        # любая другая ошибка при сортировке — останавливаем режим
                        self.destructive_iterating = False
                        if hasattr(self, "_destructive_iter"):
                            del self._destructive_iter
                        if hasattr(self, "_show_temp_message"):
                            self._show_temp_message(f"Error during sorting: {sort_err}")
        except Exception as outer_sort_err:
            # защита от совсем неожиданных вещей вокруг сортировки
            if hasattr(self, "_show_temp_message"):
                self._show_temp_message(f"Unexpected sorting error: {outer_sort_err}")

        # --- Перерисовка тулбара ---
        if getattr(self, "toolbar_needs_redraw", False):
            if hasattr(self, "_redraw_toolbar"):
                try:
                    self._redraw_toolbar()
                except Exception as tb_err:
                    # чтобы не лагало бесконечно, сбросим флаг
                    self.toolbar_needs_redraw = False
                    if hasattr(self, "_show_temp_message"):
                        self._show_temp_message(f"Toolbar redraw error: {tb_err}")

        # --- Перерисовка баров ---
        if hasattr(self, "_redraw_bars_if_needed"):
            try:
                self._redraw_bars_if_needed()
            except Exception as bars_err:
                if hasattr(self, "_show_temp_message"):
                    self._show_temp_message(f"Bars redraw error: {bars_err}")

        # --- Рисуем поверхности ---
        screen = getattr(self, "screen", None)
        if screen is not None:
            try:
                bars_surface = getattr(self, "bars_surface", None)
                toolbar_surface = getattr(self, "toolbar_surface", None)

                if bars_surface is not None:
                    screen.blit(bars_surface, (0, 0))
                if toolbar_surface is not None:
                    screen.blit(toolbar_surface, (0, 0))
            except Exception as blit_err:
                if hasattr(self, "_show_temp_message"):
                    self._show_temp_message(f"Blit error: {blit_err}")

        # --- Текст/оверлеи ---
        for method_name in ("_draw_info_text", "_draw_temp_message", "_draw_sort_progress"):
            fn = getattr(self, method_name, None)
            if callable(fn):
                try:
                    fn()
                except Exception as draw_err:
                    # не даём одному тексту/оверлею уронить весь кадр
                    if hasattr(self, "_show_temp_message") and method_name != "_draw_temp_message":
                        self._show_temp_message(f"{method_name} error: {draw_err}")

    def _draw_temp_message(self):
        """Рисует временное сообщение"""
        if self.temp_message and time.perf_counter() < self.message_end_time:
            lines = self.temp_message.split('\n')
            y = HEIGHT - 150

            # Фон для сообщения
            max_width = max(self.font.size(line)[0] for line in lines)
            bg_rect = pygame.Rect(20, y - 5, max_width + 20, len(lines) * 25 + 10)
            pygame.draw.rect(self.screen, (40, 40, 60), bg_rect, border_radius=5)
            pygame.draw.rect(self.screen, (100, 100, 150), bg_rect, 2, border_radius=5)

            for line in lines:
                text = self.font.render(line, True, (220, 220, 100))
                self.screen.blit(text, (30, y))
                y += 25

    def _draw_sort_progress(self):
        """Показывает прогресс сортировки"""
        if self.destructive_iterating:
            progress = len(self.sorted_items) / (len(self.sorted_items) + len(self.heap.data)) if (len(self.sorted_items) +
                                                                                                   len(self.heap.data)) > 0 else 0
            text = self.font.render(f"Sorting... {len(self.sorted_items)} items extracted", True, (255, 200, 100))
            self.screen.blit(text, (WIDTH - 300, HEIGHT - 100))

            # Прогресс-бар
            bar_rect = pygame.Rect(WIDTH - 300, HEIGHT - 70, 280, 20)
            pygame.draw.rect(self.screen, (60, 60, 80), bar_rect, border_radius=3)
            fill_width = int(280 * progress)
            if fill_width > 0:
                fill_rect = pygame.Rect(bar_rect.x, bar_rect.y, fill_width, 20)
                pygame.draw.rect(self.screen, (100, 200, 100), fill_rect, border_radius=3)

    def _redraw_toolbar(self):
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
            # Центрируем текст в кнопке
            text_x = rect.x + (rect.width - label_surf.get_width()) // 2
            text_y = rect.y + (rect.height - label_surf.get_height()) // 2
            surf.blit(label_surf, (text_x, text_y))

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
        # Центрируем текст в поле ввода
        text_x = self.input_rect.x + 8
        text_y = self.input_rect.y + (self.input_rect.height - txt.get_height()) // 2
        surf.blit(txt, (text_x, text_y))

        # кнопка Insert рядом с инпутом - на той же высоте
        self.insert_btn_rect = pygame.Rect(
            self.input_rect.right + 8,
            self.input_rect.y,  # та же Y-координата что и у поля ввода
            90,
            self.input_rect.height  # та же высота что и у поля ввода
        )
        btn_bg = BTN_BG if self.input_text else BTN_BG_DISABLED
        pygame.draw.rect(surf, btn_bg, self.insert_btn_rect, border_radius=6)
        label = self.font.render("Insert", True, TEXT_COLOR)
        # Центрируем текст в кнопке Insert
        label_x = self.insert_btn_rect.x + (self.insert_btn_rect.width - label.get_width()) // 2
        label_y = self.insert_btn_rect.y + (self.insert_btn_rect.height - label.get_height()) // 2
        surf.blit(label, (label_x, label_y))

        self.toolbar_needs_redraw = False

    def _redraw_bars_if_needed(self):
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
        if vmax == vmin:
            return 255
        t = (val - vmin) / (vmax - vmin)
        return 128 + int(t * 127)

    def _draw_active_overlay_onto_overlay(self, values, bar_width, scale, base_y):
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
                self.current_anim = None
            else:
                self.current_anim = item
            return

        if self.current_anim:
            if self._anim_progress(self.current_anim) >= 1.0:
                self.current_anim = None

    @staticmethod
    def _anim_progress(anim):
        span = anim["dur"]
        if span <= 0:
            return 1.0
        return min(1.0, (time.perf_counter() - anim["t0"]) / span)

    def _draw_info_text(self):
        mode = "Min-Heap" if self.heap.min_heap else "Max-Heap"
        info_lines = [
            "[I] InsertRand  [P] Pop  [T] PushPop  [E] Replace",
            "[L] 5 Largest  [S] Sort  [D] Stats  [M] Toggle  [R] Reset"
        ]

        y_pos = HEIGHT - 70
        for line in info_lines:
            info = self.font.render(line, True, TEXT_COLOR)
            self.screen.blit(info, (20, y_pos))
            y_pos += 25

        mode_text = self.font.render(f"({mode})", True, TEXT_COLOR)
        self.screen.blit(mode_text, (WIDTH - 120, HEIGHT - 45))

        status_ok = True
        if hasattr(self.heap, "is_valid_heap"):
            try:
                status_ok = self.heap.is_valid_heap()
            except Exception:
                status_ok = False

        status_text = "HEAP OK" if status_ok else "HEAP BROKEN"
        status_color = ACCENT_OK if status_ok else ACCENT_BAD
        status = self.font.render(status_text, True, status_color)
        self.screen.blit(status, (WIDTH - 120, HEIGHT - 70))