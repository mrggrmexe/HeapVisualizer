from typing import List, Optional, Any, Callable, Iterable, TypeVar, Generic, Dict
from contextlib import contextmanager
import math

T = TypeVar("T")


class Heap(Generic[T]):
    """
    Расширенная реализация бинарной кучи.

    Возможности:
        - Поддержка min/max режима (min_heap=True по умолчанию).
        - Observer-колбэк для визуализации событий и отладки.
        - Поддержка key-функции для сравнения элементов.
        - Политика обработки NaN (raise/min/max).
        - Защита от реэнтрантных изменений структуры (mutations).

    Примечания:
        - Структура и сигнатуры методов сохранены для совместимости
          с остальными частями проекта.
        - В observer передаются компактные payload'ы (значения > 200 символов
          сокращаются).
    """

    def __init__(
        self,
        min_heap: bool = True,
        key: Optional[Callable[[T], Any]] = None,
        observer: Optional[Callable[[str, dict], None]] = None,
        verify_sample_rate: int = 0,
        nan_policy: str = "raise",
    ):
        """
        Инициализирует кучу.

        Args:
            min_heap: Режим сравнения. True — min-куча, False — max-куча.
            key: Необязательная функция проекции ключа для сравнения.
            observer: Колбэк наблюдателя: (event: str, payload: dict) -> None.
            verify_sample_rate: Частота проверок инварианта (0 — без проверок).
            nan_policy: Политика обработки NaN в ключах: 'raise' | 'min' | 'max'.

        Примечания:
            - Если verify_sample_rate > 0, после каждого изменения с частотой
              1 / verify_sample_rate будет выполняться проверка инварианта.
        """
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
        """
        Добавляет элемент в кучу (вставка с последующим подъёмом).

        Args:
            value: Вставляемый элемент.

        Raises:
            ValueError: При недопустимом значении (например, key(value) даёт NaN
                        при nan_policy='raise', либо key() бросает исключение).
        """
        # Предварительная нормализация значения (NaN и key) — для ранней валидации
        try:
            _ = self._normalize_key(self.key(value) if self.key else value)
        except Exception as e:
            raise ValueError(f"Invalid value for heap: {value!r} ({e})") from e

        with self._mutation("push"):
            n_before = len(self.data)
            self._notify("insert_start", value=value, index=n_before)

            # Фактическая вставка
            self.data.append(value)
            self._notify("insert", index=n_before, value=value)

            try:
                # Восстанавливаем инвариант
                self._heapify_up(n_before)
            except Exception as e:
                # Если сравнение/heapify сломались — удаляем элемент обратно
                popped = self.data.pop()
                self._notify("insert_error", value=popped, error=str(e))
                raise

            self._notify("push_done", size=len(self.data))

    def pop(self, default: Optional[T] = None) -> Optional[T]:
        """
        Извлекает и возвращает корневой элемент кучи.

        Args:
            default: Значение по умолчанию, возвращаемое при пустой куче.

        Returns:
            Извлечённый элемент или default, если куча пуста.

        Raises:
            Любые исключения, возникшие в процессе восстановления инварианта,
            пробрасываются наверх (после уведомления observer).
        """
        with self._mutation("pop"):
            if not self.data:
                self._notify("pop_empty", size=0)
                return default

            self._notify("pop_start", size=len(self.data))
            try:
                root = self.data[0]
                self._notify("pop_root", value=root, size=len(self.data))

                last = self.data.pop()
                if self.data:
                    self.data[0] = last
                    self._notify("move", src=len(self.data), dst=0, value=last)
                    self._heapify_down(0)

                self._notify("pop_done", value=root, size=len(self.data))
                return root

            except Exception as e:
                self._notify("pop_error", error=str(e), size=len(self.data))
                raise

    def peek(self) -> Optional[T]:
        """
        Возвращает корневой элемент, не удаляя его.

        Returns:
            Корневой элемент или None, если куча пуста.
        """
        return self.data[0] if self.data else None

    def clear(self) -> None:
        """
        Полностью очищает кучу.

        Примечания:
            - Отправляет событие 'clear' с количеством очищенных элементов.
        """
        if not self.data:
            return
        with self._mutation("clear"):
            old_size = len(self.data)
            self.data.clear()
            self._notify("clear", cleared=old_size)

    def extend(self, items: Iterable[T]) -> None:
        """
        Массово добавляет элементы и перестраивает кучу оптимальным образом.

        Args:
            items: Итерабельная коллекция добавляемых элементов.

        Примечания:
            - Для одного элемента быстрее вызвать push().
            - Для нескольких элементов эффективнее выполнить extend + heapify().
        """
        items = list(items)
        if not items:
            return

        n_added = len(items)
        if n_added == 1:
            # Для одного элемента быстрее сделать push
            self.push(items[0])  # фикс опечатки: раньше было self.heappush(...)
            self._notify("extend", added=1)
            return

        start_size = len(self.data)
        self.data.extend(items)
        self.heapify()
        self._notify("extend", added=len(self.data) - start_size)

    def toggle_mode(self) -> None:
        """
        Переключает режим сравнения (min <-> max) с безопасной перестройкой кучи.

        Примечания:
            - Вызывает heapify() после переключения режима.
        """
        self.min_heap = not self.min_heap
        self._notify("toggle_mode", min_heap=self.min_heap)
        self.heapify()

    def set_mode(self, min_heap: bool) -> None:
        """
        Устанавливает конкретный режим сравнения с перестройкой кучи.

        Args:
            min_heap: True — min-режим, False — max-режим.

        Примечания:
            - Перестройка выполняется только при фактическом изменении режима.
        """
        if self.min_heap != min_heap:
            self.min_heap = min_heap
            self._notify("set_mode", min_heap=self.min_heap)
            self.heapify()

    def heapify(self) -> None:
        """
        Перестраивает кучу "на месте" из текущего массива данных.

        Примечания:
            - Используется стратегия "сверху вниз": спуск по внутренним узлам.
        """
        with self._mutation("heapify"):
            n = len(self.data)
            for i in range((n - 2) // 2, -1, -1):
                self._heapify_down(i)
            self._notify("heapify_done", size=n)

    def remove(self, value: T, all: bool = False) -> int:
        """
        Удаляет первый или все элементы, равные заданному значению.

        Args:
            value: Значение для удаления.
            all: Если True, удаляются все вхождения. Иначе только первое.

        Returns:
            Количество удалённых элементов.

        Примечания:
            - Сохраняет инвариант кучи после каждого удаления.
        """
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
        """
        Удаляет элемент по индексу с восстановлением инварианта.

        Args:
            index: Индекс удаляемого элемента.

        Примечания:
            - Если индекс вне диапазона, метод ничего не делает.
            - После удаления выполняются _heapify_down и _heapify_up, чтобы
              корректно восстановить структуру.
        """
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
        """
        Возвращает копию внутреннего массива кучи.

        Returns:
            Новый список со всеми элементами кучи.
        """
        return list(self.data)

    def is_empty(self) -> bool:
        """
        Проверяет, пуста ли куча.

        Returns:
            True, если нет элементов, иначе False.
        """
        return not self.data

    def __len__(self) -> int:
        """
        Возвращает количество элементов в куче.

        Returns:
            Число элементов.
        """
        return len(self.data)

    def __repr__(self) -> str:
        """
        Возвращает человекочитаемое представление кучи.

        Returns:
            Строка вида "<MinHeap [..]>" или "<MaxHeap [..]>".
        """
        kind = "MinHeap" if self.min_heap else "MaxHeap"
        return f"<{kind} {self.data}>"

    # ---------- INTERNALS ----------

    @contextmanager
    def _mutation(self, opname: str):
        """
        Контекстный менеджер для безопасных мутаций структуры.

        Args:
            opname: Имя операции (для логирования/observer).

        Raises:
            RuntimeError: При попытке реэнтрантного изменения кучи.
        """
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
        """
        По необходимости проверяет инвариант кучи по счётчику операций.

        Примечания:
            - Активируется, если verify_sample_rate > 0 и номер операции кратен
              заданной частоте. В противном случае ничего не делает.
            - При нарушении инварианта возбуждается AssertionError.
        """
        if self._verify_sr and (self._ops % self._verify_sr == 0):
            assert self.is_valid_heap(), "Heap invariant broken"

    # ---------- NOTIFICATIONS ----------

    def set_observer(self, fn: Optional[Callable[[str, Dict[str, Any]], None]]) -> None:
        """
        Устанавливает или снимает observer-колбэк.

        Args:
            fn: Функция-обработчик событий или None, чтобы отключить.
        """
        self._observer = fn

    def _notify(self, event: str, **payload: Any) -> None:
        """
        Безопасно вызывает observer, передавая событие и компактный payload.

        Args:
            event: Имя события (строка).
            **payload: Дополнительные данные события.

        Примечания:
            - Значения длиной > 200 символов сокращаются в строковом виде.
            - Исключения в observer подавляются и логируются на уровне debug.
        """
        observer = getattr(self, "_observer", None)
        if not observer:
            return

        def _compact(v: Any) -> Any:
            s = repr(v)
            return s[:200] + "…" if len(s) > 200 else v

        compact_payload = {k: _compact(v) for k, v in payload.items()}

        try:
            observer(event, compact_payload)
        except Exception as e:
            import logging
            logging.debug(
                f"Observer callback failed for event '{event}': {e}",
                exc_info=True,
            )

    # ---------- COMPARISON HELPERS ----------

    def _k(self, a: T) -> Any:
        """
        Вычисляет нормализованный ключ элемента с учётом key() и nan_policy.

        Args:
            a: Элемент.

        Returns:
            Ключ для сравнения.

        Raises:
            ValueError: Если key() бросил исключение или ключ недопустим.
        """
        try:
            v = self.key(a) if self.key else a
        except Exception as e:
            raise ValueError(f"key() failed for {a!r}: {e}") from e
        return self._normalize_key(v)

    def _normalize_key(self, v: Any) -> Any:
        """
        Нормализует ключ, учитывая NaN-политику.

        Args:
            v: Ключ для нормализации.

        Returns:
            Нормализованное значение ключа (возможно +/-inf для NaN).

        Raises:
            ValueError: Если nan_policy='raise' и ключ — NaN.
        """
        if isinstance(v, float) and math.isnan(v):
            if self._nan_policy == "raise":
                raise ValueError("NaN key is not allowed (nan_policy='raise')")
            elif self._nan_policy == "min":
                return float("-inf")
            elif self._nan_policy == "max":
                return float("inf")
            else:
                # Неподдерживаемое значение политики — по умолчанию как 'max'
                return float("inf")
        return v

    def _prefer(self, a: T, b: T) -> bool:
        """
        Определяет, предпочтительнее ли a по сравнению с b согласно режиму.

        Args:
            a: Первый элемент.
            b: Второй элемент.

        Returns:
            True, если a должен быть выше b (min: ключ меньше; max: больше).
        """
        ka, kb = self._k(a), self._k(b)
        return ka < kb if self.min_heap else ka > kb

    # ---------- HEAP OPERATIONS ----------

    def _heapify_up(self, index: int) -> None:
        """
        Поднимает элемент вверх до восстановления инварианта.

        Args:
            index: Индекс поднимаемого элемента.
        """
        while index > 0:
            parent = (index - 1) // 2
            if self._prefer(self.data[index], self.data[parent]):
                self._swap(index, parent)
                index = parent
            else:
                break

    def _heapify_down(self, index: int) -> None:
        """
        Опускает элемент вниз до восстановления инварианта.

        Args:
            index: Индекс опускаемого элемента.
        """
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
        """
        Меняет местами элементы с индексами i и j и уведомляет observer.

        Args:
            i: Индекс первого элемента.
            j: Индекс второго элемента.
        """
        self.data[i], self.data[j] = self.data[j], self.data[i]
        self._notify("swap", i=i, j=j, ai=self.data[i], aj=self.data[j])

    # ---------- VERIFICATION ----------

    def is_valid_heap(self) -> bool:
        """
        Проверяет соблюдение инварианта бинарной кучи.

        Returns:
            True, если каждый родитель предпочтительнее своих детей,
            иначе False.
        """
        n = len(self.data)
        for i in range((n - 2) // 2 + 1):
            left, right = 2 * i + 1, 2 * i + 2
            if left < n and self._prefer(self.data[left], self.data[i]):
                return False
            if right < n and self._prefer(self.data[right], self.data[i]):
                return False
        return True
