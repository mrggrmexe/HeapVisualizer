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
        while running:
            try:
                # Обработка событий
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        running = False
                    ui.handle_event(event)

                # Отрисовка
                screen.fill(BG_COLOR)
                ui.draw()

                pygame.display.flip()
                clock.tick(FPS)

            except Exception as loop_error:
                # Отлавливаем любые ошибки внутри цикла
                print(f"\n Ошибка в основном цикле: {loop_error}")
                traceback.print_exc()
                # Можно выбрать: продолжить цикл или аварийно завершить
                running = False

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
