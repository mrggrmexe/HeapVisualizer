import pygame
from settings import *
from ui import UI
from heap import Heap


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Heap Visualizer")
    clock = pygame.time.Clock()

    heap = Heap(min_heap=True)
    ui = UI(screen, heap)

    running = True
    while running:
        screen.fill(BG_COLOR)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            ui.handle_event(event)

        ui.draw()
        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()


if __name__ == "__main__":
    main()
