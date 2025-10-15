# heap.py
from typing import List, Optional, Any

class Heap:
    """
    Простая реализация бинарной кучи (array-backed).
    Поддерживает min- и max-режим (min_heap=True по умолчанию).
    """

    def __init__(self, min_heap: bool = True):
        self.data: List[Any] = []
        self.min_heap = min_heap

    # ---------- публичные методы ----------
    def push(self, value: Any) -> None:
        """Добавляет элемент и восстанавливает свойство кучи (просеивание вверх)."""
        self.data.append(value)
        self._heapify_up(len(self.data) - 1)

    def pop(self) -> Optional[Any]:
        """Удаляет и возвращает корень кучи. Если куча пуста — возвращает None."""
        if not self.data:
            return None
        root = self.data[0]
        last = self.data.pop()
        if self.data:
            # Переместить последний элемент в корень и просеять вниз
            self.data[0] = last
            self._heapify_down(0)
        return root

    def peek(self) -> Optional[Any]:
        """Возвращает корень без удаления, или None если куча пуста."""
        return self.data[0] if self.data else None

    def clear(self) -> None:
        """Очищает кучу."""
        self.data.clear()

    def __len__(self) -> int:
        return len(self.data)

    def is_empty(self) -> bool:
        return len(self.data) == 0

    def to_list(self) -> List[Any]:
        """Возвращает копию внутреннего массива (для отладки/визуализации)."""
        return list(self.data)

    def __repr__(self) -> str:
        t = "MinHeap" if self.min_heap else "MaxHeap"
        return f"<{t} {self.data}>"

    # ---------- внутренние вспомогательные ----------
    def _compare(self, a: Any, b: Any) -> bool:
        """
        Возвращает True если a «лучше» b в текущем режиме кучи:
         - для min-heap: a < b
         - для max-heap: a > b
        """
        return a < b if self.min_heap else a > b

    def _heapify_up(self, index: int) -> None:
        """
        Просеивание вверх: если элемент лучше родителя (в min-heap — меньше),
        то меняем их местами, пока не достигнем корня или порядок не восстановится.
        Итеративная реализация.
        """
        while index > 0:
            parent = (index - 1) // 2
            if self._compare(self.data[index], self.data[parent]):
                # обмен
                self.data[index], self.data[parent] = self.data[parent], self.data[index]
                index = parent
            else:
                break

    def _heapify_down(self, index: int) -> None:
        """
        Просеивание вниз: сравниваем с детьми, выбираем "лучшего" ребёнка
        (меньшего для min-heap, большего для max-heap) и обмениваем, если нужно.
        Итеративная реализация.
        """
        n = len(self.data)
        while True:
            left = 2 * index + 1
            right = 2 * index + 2
            candidate = index  # индекс элемента, который потенциально должен быть на этой позиции

            # выбрать между left и current
            if left < n and self._compare(self.data[left], self.data[candidate]):
                candidate = left

            # выбрать между right и current/candidate
            if right < n and self._compare(self.data[right], self.data[candidate]):
                candidate = right

            if candidate == index:
                break  # порядок восстановлен
            # обмен и продолжить просеивание вниз с новой позицией
            self.data[index], self.data[candidate] = self.data[candidate], self.data[index]
            index = candidate
