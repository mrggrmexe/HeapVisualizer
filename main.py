"""
main.py — точка входа визуализатора бинарной кучи (Heap Visualizer).

Модуль инициализирует Pygame-окно, настраивает параметры HiDPI-рендеринга
(для macOS / Retina-дисплеев), создаёт экземпляры Heap и UI, и запускает
основной цикл отрисовки и обработки событий.
"""

import os
import sys
import traceback
import pygame
from settings import *
from ui import UI
from heap import Heap


def main():
    """
    Точка входа приложения Heap Visualizer.

    Основные задачи:
        1. Настроить SDL для корректной работы в HiDPI-режиме.
        2. Инициализировать Pygame и окно визуализации.
        3. Создать экземпляры Heap (модель данных) и UI (интерфейс).
        4. Запустить главный цикл приложения:
            - обработка событий (клавиатура, мышь);
            - обновление отображения;
            - поддержание стабильного FPS.

    Исключения:
        Любые непойманные исключения логируются в консоль с трассировкой.
    """
    try:
        # --- Retina / HiDPI Fix (macOS + SDL2) ---
        # Разрешаем SDL использовать реальное пиксельное разрешение дисплея.
        os.environ["SDL_VIDEO_ALLOW_HIGHDPI"] = "1"
        os.environ.pop("SDL_VIDEO_HIGHDPI_DISABLED", None)

        # --- Инициализация Pygame ---
        pygame.init()
        print(" Pygame успешно инициализирован.")

        # --- Создание окна ---
        try:
            screen = pygame.display.set_mode(
                (WIDTH, HEIGHT),
                pygame.HWSURFACE | pygame.DOUBLEBUF | pygame.RESIZABLE
            )
            pygame.display.set_caption("Heap Visualizer (HiDPI)")
        except pygame.error as e:
            print(f" Ошибка при создании окна: {e}")
            sys.exit(1)

        # --- Информация о дисплее ---
        try:
            info = pygame.display.Info()
            print(f"Display size: {info.current_w}x{info.current_h}")
            print(f"Logical size: {WIDTH}x{HEIGHT}")
        except Exception as e:
            print(f" Не удалось получить информацию о дисплее: {e}")

        # --- Подготовка таймера и объектов приложения ---
        clock = pygame.time.Clock()
        heap = Heap(min_heap=True)
        ui = UI(screen, heap)

        # --- Основной цикл ---
        running = True
        consecutive_errors = 0
        MAX_CONSECUTIVE_ERRORS = 5  # после 5 подряд ошибок — аварийный выход

        try:
            while running:
                try:
                    # --- Обработка событий ---
                    for event in pygame.event.get():
                        if event.type == pygame.QUIT:
                            running = False
                        else:
                            # Ошибка в обработке ОДНОГО события не убивает весь цикл
                            try:
                                ui.handle_event(event)
                            except Exception as event_error:
                                print(f"\n[WARN] Ошибка при обработке события: {event_error}")
                                traceback.print_exc()
                                # Продолжаем, просто пропуская проблемное событие

                    # --- Отрисовка ---
                    try:
                        screen.fill(BG_COLOR)
                        ui.draw()
                        pygame.display.flip()
                    except pygame.error as pg_err:
                        # Обычно это уже серьёзно (потеря контекста, проблемное окно)
                        print(f"\n[ERROR] Ошибка Pygame при отрисовке: {pg_err}")
                        traceback.print_exc()
                        running = False
                        continue
                    except Exception as draw_err:
                        print(f"\n[ERROR] Ошибка в отрисовке кадра: {draw_err}")
                        traceback.print_exc()
                        consecutive_errors += 1
                        if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                            print(f"[FATAL] Слишком много подряд ошибок отрисовки ({consecutive_errors}), выходим.")
                            running = False
                        # Если ошибка не фатальна — просто пропускаем кадр
                        continue
                    else:
                        # Успешный кадр — сбрасываем счётчик ошибок
                        consecutive_errors = 0

                    # --- Ограничение FPS ---
                    try:
                        clock.tick(FPS)
                    except Exception as tick_err:
                        print(f"\n[WARN] Ошибка в clock.tick(): {tick_err}")
                        traceback.print_exc()
                        # Это не критично, просто не ограничим FPS в этом кадре

                except KeyboardInterrupt:
                    print("\n[INFO] Остановка по Ctrl+C")
                    running = False

                except SystemExit:
                    # Если кто-то вызвал sys.exit() внутри — уважаем это
                    raise

                except Exception as loop_error:
                    # Любая НЕОЖИДАННАЯ ошибка верхнего уровня цикла
                    print(f"\n[FATAL] Необработанная ошибка в основном цикле: {loop_error}")
                    traceback.print_exc()
                    running = False

        finally:
            # Гарантированное завершение Pygame
            try:
                pygame.quit()
            except Exception as quit_err:
                print(f"\n[WARN] Ошибка при pygame.quit(): {quit_err}")
                traceback.print_exc()
            # По желанию:
            # sys.exit(0)

    except KeyboardInterrupt:
        # Позволяем корректно выйти через Ctrl+C
        print("\n Завершение по Ctrl+C")

    except Exception as e:
        # Любая инициализационная ошибка
        print(f"\n Критическая ошибка при запуске: {e}")
        traceback.print_exc()

    finally:
        # Гарантированное завершение Pygame
        pygame.quit()
        print(" Приложение завершено.")


if __name__ == "__main__":
    main()
