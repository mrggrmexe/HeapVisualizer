import os
import pygame
from settings import *
from ui import UI
from heap import Heap


def main():
    # --- Retina / HiDPI Fix (macOS + SDL2) ---
    # Разрешаем SDL использовать реальное пиксельное разрешение
    os.environ["SDL_VIDEO_ALLOW_HIGHDPI"] = "1"
    os.environ.pop("SDL_VIDEO_HIGHDPI_DISABLED", None)

    pygame.init()

    # Создаём окно без SDL_SCALED (чтобы избежать блюра)
    screen = pygame.display.set_mode(
        (WIDTH, HEIGHT),
        pygame.HWSURFACE | pygame.DOUBLEBUF | pygame.RESIZABLE
    )
    pygame.display.set_caption("Heap Visualizer (HiDPI)")

    # Проверим физическое разрешение (для справки в консоли)
    info = pygame.display.Info()
    print(f"Display size: {info.current_w}x{info.current_h}")
    print(f"Logical size: {WIDTH}x{HEIGHT}")

    clock = pygame.time.Clock()

    heap = Heap(min_heap=True)
    ui = UI(screen, heap)

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            ui.handle_event(event)

        screen.fill(BG_COLOR)
        ui.draw()

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()


if __name__ == "__main__":
    main()
