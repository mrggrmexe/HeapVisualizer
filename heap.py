from typing import List, Optional, Any, Callable, Iterable, TypeVar, Generic
from contextlib import contextmanager
import math

T = TypeVar("T")


class Heap(Generic[T]):
    """
    Расширенная реализация бинарной кучи с поддержкой:
    - min/max режима (min_heap=True по умолчанию)
    - observer для визуализации
    - key-функции
    - политики обработки NaN
    - защиты от реэнтрантных операций
    """

    def __init__(
        self,
        min_heap: bool = True,
        key: Optional[Callable[[T], Any]] = None,
        observer: Optional[Callable[[str, dict], None]] = None,
        verify_sample_rate: int = 0,
        nan_policy: str = "raise",
    ):
        self.data: List[T] = []
        self.min_heap = min_heap
        self.key = key
        self._observer = observer
        self._mutating = False
        self._ops = 0
        self._verify_sr = max(0, verify_sample_rate)
        self._nan_policy = nan_policy

    # ---------- PUBLIC API ----------

    def push(self, value: T) -> None:
        # предварительная нормализация значения (NaN и key)
        try:
            _ = self._normalize_key(self.key(value) if self.key else value)
        except Exception as e:
            raise ValueError(f"Invalid value for heap: {value!r} ({e})") from e
        with self._mutation("push"):
            n_before = len(self.data)
            self._notify("insert_start", value=value, index=n_before)
            # фактическая вставка
            self.data.append(value)
            self._notify("insert", index=n_before, value=value)
            try:
                # восстанавливаем инвариант
                self._heapify_up(n_before)
            except Exception as e:
                # если вдруг сравнение или heapify сломались — удаляем элемент обратно
                popped = self.data.pop()
                self._notify("insert_error", value=popped, error=str(e))
                raise

            self._notify("push_done", size=len(self.data))

    def pop(self, default: Optional[T] = None) -> Optional[T]:
        with self._mutation("pop"):
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

    def peek(self) -> Optional[T]:
        return self.data[0] if self.data else None

    def clear(self) -> None:
        with self._mutation("clear"):
            self.data.clear()
            self._notify("clear")

    def extend(self, items: Iterable[T]) -> None:
        """Пакетное добавление элементов с последующей перестройкой кучи."""
        start_size = len(self.data)
        self.data.extend(items)
        self._notify("extend", added=len(self.data) - start_size)
        self.heapify()  # heapify уже сам управляет _mutation

    def toggle_mode(self) -> None:
        """Переключение min/max режима с перестройкой без двойной блокировки."""
        self.min_heap = not self.min_heap
        self._notify("toggle_mode", min_heap=self.min_heap)
        self.heapify()

    def set_mode(self, min_heap: bool) -> None:
        """Установить конкретный режим (min_heap=True/False) безопасно."""
        if self.min_heap != min_heap:
            self.min_heap = min_heap
            self._notify("set_mode", min_heap=self.min_heap)
            self.heapify()

    def heapify(self) -> None:
        """Построение кучи из текущих данных."""
        with self._mutation("heapify"):
            n = len(self.data)
            for i in range((n - 2) // 2, -1, -1):
                self._heapify_down(i)
            self._notify("heapify_done", size=n)

    def remove(self, value: T, all: bool = False) -> int:
        """Удаляет первый (или все) элементы, равные value."""
        removed = 0
        i = 0
        while i < len(self.data):
            if self.data[i] == value:
                self._remove_at(i)
                removed += 1
                if not all:
                    break
            else:
                i += 1
        if removed:
            self._notify("remove_value", value=value, count=removed)
        return removed

    def _remove_at(self, index: int) -> None:
        with self._mutation("remove_at"):
            n = len(self.data)
            if not (0 <= index < n):
                return
            last = self.data.pop()
            if index < n - 1:
                self.data[index] = last
                self._heapify_down(index)
                self._heapify_up(index)
            self._notify("remove_at", index=index, size=len(self.data))

    def to_list(self) -> List[T]:
        return list(self.data)

    def is_empty(self) -> bool:
        return not self.data

    def __len__(self) -> int:
        return len(self.data)

    def __repr__(self) -> str:
        kind = "MinHeap" if self.min_heap else "MaxHeap"
        return f"<{kind} {self.data}>"

    # ---------- INTERNALS ----------

    @contextmanager
    def _mutation(self, opname: str):
        """Контекст защиты от реэнтрантности."""
        if self._mutating:
            raise RuntimeError(f"Re-entrant heap mutation in '{opname}'")
        self._mutating = True
        try:
            yield
        finally:
            self._mutating = False
            self._ops += 1
            self._maybe_verify()

    def _maybe_verify(self):
        if self._verify_sr and (self._ops % self._verify_sr == 0):
            assert self.is_valid_heap(), "Heap invariant broken"

    # ---------- NOTIFICATIONS ----------

    def set_observer(self, fn: Optional[Callable[[str, dict], None]]) -> None:
        self._observer = fn

    def _notify(self, event: str, **payload: Any) -> None:
        if not self._observer:
            return
        compact = {}
        for k, v in payload.items():
            s = repr(v)
            compact[k] = (s[:200] + "…") if len(s) > 200 else v
        try:
            self._observer(event, compact)
        except Exception:
            pass

    # ---------- COMPARISON HELPERS ----------

    def _k(self, a: T) -> Any:
        try:
            v = self.key(a) if self.key else a
        except Exception as e:
            raise ValueError(f"key() failed for {a!r}: {e}") from e
        return self._normalize_key(v)

    def _normalize_key(self, v: Any) -> Any:
        if isinstance(v, float) and math.isnan(v):
            if self._nan_policy == "raise":
                raise ValueError("NaN key is not allowed (nan_policy='raise')")
            elif self._nan_policy == "min":
                return float("-inf")
            elif self._nan_policy == "max":
                return float("inf")
            else:
                return float("inf")
        return v

    def _prefer(self, a: T, b: T) -> bool:
        ka, kb = self._k(a), self._k(b)
        return ka < kb if self.min_heap else ka > kb

    # ---------- HEAP OPERATIONS ----------

    def _heapify_up(self, index: int) -> None:
        while index > 0:
            parent = (index - 1) // 2
            if self._prefer(self.data[index], self.data[parent]):
                self._swap(index, parent)
                index = parent
            else:
                break

    def _heapify_down(self, index: int) -> None:
        n = len(self.data)
        while True:
            left = 2 * index + 1
            right = 2 * index + 2
            best = index
            if left < n and self._prefer(self.data[left], self.data[best]):
                best = left
            if right < n and self._prefer(self.data[right], self.data[best]):
                best = right
            if best == index:
                break
            self._swap(index, best)
            index = best

    def _swap(self, i: int, j: int) -> None:
        self.data[i], self.data[j] = self.data[j], self.data[i]
        self._notify("swap", i=i, j=j, ai=self.data[i], aj=self.data[j])

    # ---------- VERIFICATION ----------

    def is_valid_heap(self) -> bool:
        n = len(self.data)
        for i in range((n - 2) // 2 + 1):
            left, right = 2 * i + 1, 2 * i + 2
            if left < n and self._prefer(self.data[left], self.data[i]):
                return False
            if right < n and self._prefer(self.data[right], self.data[i]):
                return False
        return True
