from __future__ import annotations
from typing import (
    List, Optional, Any, Callable, Iterable, TypeVar, Generic, Protocol, Tuple
)

# -------- дженерики и протокол сравнения --------
class _Comparable(Protocol):
    def __lt__(self, other: Any) -> bool: ...
    def __gt__(self, other: Any) -> bool: ...

T = TypeVar("T", bound=_Comparable)

Observer = Callable[[str, dict], None]  # (event, payload) -> None

class Heap(Generic[T]):
    """
    Бинарная куча (array-backed) с поддержкой:
      - min/max режима
      - key-функции для сравнения
      - observer-callback для трассировки шагов (анимация)
      - пакетного построения/расширения
      - удаления по значению
    """

    def __init__(
        self,
        min_heap: bool = True,
        key: Optional[Callable[[T], Any]] = None,
        items: Optional[Iterable[T]] = None,
        observer: Optional[Observer] = None,
    ):
        self.data: List[T] = []
        self.min_heap = min_heap
        self.key = key
        self._observer = observer
        if items is not None:
            self.data = list(items)
            self.heapify()

    # ---------- публичные методы ----------
    def set_observer(self, observer: Optional[Observer]) -> None:
        self._observer = observer

    def push(self, value: T) -> None:
        self.data.append(value)
        self._notify("insert", index=len(self.data) - 1, value=value)
        self._heapify_up(len(self.data) - 1)
        self._notify("push_done", size=len(self.data))

    def pop(self, default: Optional[T] = None) -> Optional[T]:
        if not self.data:
            self._notify("pop_empty", size=0)
            return default
        root = self.data[0]
        last = self.data.pop()
        self._notify("pop_root", value=root, size=len(self.data) + 1)
        if self.data:
            self.data[0] = last
            self._notify("move", src=len(self.data), dst=0, value=last)
            self._heapify_down(0)
        self._notify("pop_done", value=root, size=len(self.data))
        return root

    def peek(self, default: Optional[T] = None) -> Optional[T]:
        return self.data[0] if self.data else default

    def clear(self) -> None:
        self.data.clear()
        self._notify("clear")

    def extend(self, items: Iterable[T]) -> None:
        # добавляем и перестраиваем линейно
        start_size = len(self.data)
        self.data.extend(items)
        self._notify("extend", added=len(self.data) - start_size)
        self.heapify()

    @classmethod
    def from_iterable(
        cls,
        items: Iterable[T],
        *,
        min_heap: bool = True,
        key: Optional[Callable[[T], Any]] = None,
        observer: Optional[Observer] = None,
    ) -> "Heap[T]":
        return cls(min_heap=min_heap, key=key, items=list(items), observer=observer)

    def heapify(self) -> None:
        n = len(self.data)
        for i in range((n - 2) // 2, -1, -1):
            self._heapify_down(i)
        self._notify("heapify_done", size=n)

    def toggle_mode(self) -> None:
        self.min_heap = not self.min_heap
        self._notify("toggle_mode", min_heap=self.min_heap)
        self.heapify()

    def set_mode(self, min_heap: bool) -> None:
        if self.min_heap != min_heap:
            self.min_heap = min_heap
            self._notify("set_mode", min_heap=self.min_heap)
            self.heapify()

    def is_valid_heap(self) -> bool:
        n = len(self.data)
        last_parent = (n - 2) // 2
        for i in range(0, last_parent + 1):
            left = 2 * i + 1
            right = 2 * i + 2
            if left < n and self._prefer(self.data[left], self.data[i]):
                return False
            if right < n and self._prefer(self.data[right], self.data[i]):
                return False
        return True

    def remove(self, value: T, *, all: bool = False) -> int:
        """
        Удаляет первое (или все) вхождение value. Возвращает число удалённых.
        Амортизационно O(k log n) при k удалениях.
        """
        removed = 0
        i = 0
        while i < len(self.data):
            if self.data[i] == value:
                self._remove_at(i)
                removed += 1
                if not all:
                    break
                # не увеличиваем i — на позицию i приехал новый элемент
            else:
                i += 1
        if removed:
            self._notify("remove_value", value=value, count=removed)
        return removed

    def copy(self) -> "Heap[T]":
        h = Heap(min_heap=self.min_heap, key=self.key)
        h.data = list(self.data)
        return h

    def __len__(self) -> int:
        return len(self.data)

    def __bool__(self) -> bool:
        return bool(self.data)

    def to_list(self) -> List[T]:
        return list(self.data)

    def __repr__(self) -> str:
        t = "MinHeap" if self.min_heap else "MaxHeap"
        return f"<{t} {self.data}>"

    # ---------- внутренние вспомогательные ----------
    def _k(self, a: T) -> Any:
        return self.key(a) if self.key else a

    def _prefer(self, a: T, b: T) -> bool:
        # True, если a «лучше» b для текущего режима
        ka, kb = self._k(a), self._k(b)
        return ka < kb if self.min_heap else ka > kb

    def _heapify_up(self, index: int) -> None:
        while index > 0:
            parent = (index - 1) // 2
            self._notify("compare", i=index, j=parent,
                         ai=self.data[index], aj=self.data[parent])
            if self._prefer(self.data[index], self.data[parent]):
                self._notify("swap", i=index, j=parent,
                             ai=self.data[index], aj=self.data[parent])
                self.data[index], self.data[parent] = self.data[parent], self.data[index]
                index = parent
            else:
                break

    def _heapify_down(self, index: int) -> None:
        n = len(self.data)
        while True:
            left = 2 * index + 1
            right = 2 * index + 2
            candidate = index

            if left < n:
                self._notify("compare", i=left, j=candidate,
                             ai=self.data[left], aj=self.data[candidate])
                if self._prefer(self.data[left], self.data[candidate]):
                    candidate = left
            if right < n:
                self._notify("compare", i=right, j=candidate,
                             ai=self.data[right], aj=self.data[candidate])
                if self._prefer(self.data[right], self.data[candidate]):
                    candidate = right

            if candidate == index:
                break
            self._notify("swap", i=index, j=candidate,
                         ai=self.data[index], aj=self.data[candidate])
            self.data[index], self.data[candidate] = self.data[candidate], self.data[index]
            index = candidate

    def _remove_at(self, i: int) -> T:
        """
        Удаляет элемент по индексу i и восстанавливает кучу.
        Возвращает удалённое значение.
        """
        n = len(self.data)
        val = self.data[i]
        last = self.data.pop()
        self._notify("remove_at", index=i, value=val)
        if i < n - 1:
            self.data[i] = last
            self._notify("move", src=n - 1, dst=i, value=last)
            # Восстанавливаем: пробуем и вверх, и вниз (в худшем — одно из них сработает за O(log n))
            if i > 0 and self._prefer(self.data[i], self.data[(i - 1) // 2]):
                self._heapify_up(i)
            else:
                self._heapify_down(i)
        return val

    def _notify(self, event: str, **payload: Any) -> None:
        if self._observer:
            try:
                self._observer(event, payload)
            except Exception:
                # Никогда не роняем структуру из-за UI/observer
                pass
