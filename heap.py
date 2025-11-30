from typing import List, Optional, Any, Callable, Iterable, TypeVar, Generic, Dict
from contextlib import contextmanager
import math

T = TypeVar("T")

from contextlib import contextmanager
from typing import Optional

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
            Любое исключение из key()/observer/_heapify_up пробрасывается дальше,
            при этом состояние кучи откатывается к исходному.
        """
        # --- 1. Предварительная валидация значения ---
        try:
            raw_key = self.key(value) if self.key else value
            _ = self._normalize_key(raw_key)
        except Exception as e:
            # На этом этапе к куче мы ещё не прикасались, так что состояние не меняем
            raise ValueError(f"Invalid value for heap: {value!r} ({e})") from e

        # --- 2. Безопасная мутация структуры ---
        with self._mutation("push"):
            n_before = len(self.data)
            self._notify("insert_start", value=value, index=n_before)

            # Сохраняем снапшот для отката в случае любой ошибки
            old_data = self.data.copy()

            # Фактическая вставка
            self.data.append(value)
            self._notify("insert", index=n_before, value=value)

            # Пустая куча — самый простой случай: никакого подъёма не нужно
            if n_before == 0:
                self._notify("push_done", size=len(self.data))
                return

            try:
                # Восстанавливаем инвариант
                self._heapify_up(n_before)
            except Exception as e:
                # Любая ошибка во время подъёма/observer:
                # аккуратно откатываем список к исходному состоянию.
                self.data = old_data
                self._notify("insert_error", value=value, error=str(e))
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
            Любые исключения, возникшие в процессе восстановления инварианта
            (включая ошибки key()/nan_policy/observer), пробрасываются наверх.
            При этом при любой ошибке состояние кучи откатывается к исходному.
        """
        with self._mutation("pop"):
            if not self.data:
                # Куча пуста — ничего не меняем, просто логируем и возвращаем default
                self._notify("pop_empty", size=0)
                return default

            # Снапшот состояния кучи для отката
            old_data = self.data.copy()

            self._notify("pop_start", size=len(self.data))
            try:
                root = self.data[0]
                self._notify("pop_root", value=root, size=len(self.data))

                # Удаляем последний элемент
                last = self.data.pop()

                if self.data:
                    # Переносим последний на корень и восстанавливаем инвариант
                    self.data[0] = last
                    self._notify("move", src=len(self.data), dst=0, value=last)
                    self._heapify_down(0)

                self._notify("pop_done", value=root, size=len(self.data))
                return root

            except Exception as e:
                # Откат состояния кучи
                self.data = old_data
                # Пытаемся уведомить observer об ошибке, но не даём ему сломать исходный стек
                try:
                    self._notify("pop_error", error=str(e), size=len(self.data))
                except Exception:
                    pass
                # Пробрасываем исходное исключение
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
        # Даже если куча уже пуста — отправим событие (cleared=0),
        # чтобы визуализатор/логика не ломались на нажатии "Clear".
        if not self.data:
            self._notify("clear", cleared=0)
            return

        with self._mutation("clear"):
            # Снапшот для отката в случае любой ошибки
            old_data = self.data.copy()
            old_size = len(old_data)

            try:
                # Основная операция
                self.data.clear()
                self._notify("clear", cleared=old_size)

            except Exception as e:
                # При любой ошибке пытаемся откатить состояние
                self.data = old_data
                # Не даём ошибке observer ещё раз сломать стек
                try:
                    self._notify("clear_error", cleared=0, error=str(e))
                except Exception:
                    pass
                # Пробрасываем исходное исключение выше
                raise

    def extend(self, items: Iterable[T]) -> None:
        """
        Неизменяемо добавляет множество элементов в кучу.
        Защищено от некорректных входных данных и ошибок heapify().
        """

        # --- Проверка входа ---
        if items is None:
            return  # тихое игнорирование None как "ничего не добавлять"

        try:
            items = list(items)
        except TypeError:
            raise TypeError("extend() ожидает итерируемый объект")

        if not items:
            return

        # --- Быстрый путь для одного элемента ---
        if len(items) == 1:
            try:
                self.push(items[0])
                self._notify("extend", added=1)
            except Exception as exc:
                raise RuntimeError(f"push() failed in extend(): {exc}") from exc
            return

        # --- Массовая вставка ---
        if not isinstance(self.data, list):
            raise TypeError("Internal heap storage self.data повреждён — ожидается list")

        start_size = len(self.data)

        # Локальная копия для отката, если heapify() упадёт
        backup = self.data.copy()

        try:
            self.data.extend(items)
            self.heapify()
        except Exception as exc:
            # откат данных, чтобы не оставить структуру сломанной
            self.data = backup
            raise RuntimeError(f"heapify() failed in extend(): {exc}") from exc

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
        """
        # --- Базовые проверки внутреннего состояния ---
        if not hasattr(self, "data"):
            raise AttributeError("Heap has no internal 'data' storage (self.data)")

        if not isinstance(self.data, list):
            raise TypeError("Internal heap storage self.data повреждён — ожидается list")

        removed = 0
        i = 0
        remove_all = bool(all)

        while i < len(self.data):
            # Защитимся от странных реализаций __eq__
            try:
                is_equal = (self.data[i] == value)
            except Exception as exc:
                raise RuntimeError(f"Comparison failed in remove(): {exc}") from exc

            if is_equal:
                try:
                    before = len(self.data)
                    self._remove_at(i)
                    after = len(self.data)
                except Exception as exc:
                    raise RuntimeError(f"_remove_at({i}) failed in remove(): {exc}") from exc

                # Базовая sanity-проверка, чтобы не зависнуть в бесконечном цикле
                if after >= before:
                    raise RuntimeError(
                        "_remove_at() не уменьшил размер кучи; "
                        "возможен бесконечный цикл или нарушение инварианта."
                    )

                removed += 1

                if not remove_all:
                    break
                # i не увеличиваем: на эту позицию попал новый элемент,
                # нужно проверить его ещё раз на равенство value.
            else:
                i += 1

        if removed:
            try:
                self._notify("remove_value", value=value, count=removed)
            except Exception as exc:
                # Поведение по выбору: либо проглатывать, либо поднимать ошибку.
                # Здесь поднимаем, чтобы такие баги было видно сразу.
                raise RuntimeError(f"_notify() failed in remove(): {exc}") from exc

        return removed

    def _remove_at(self, index: int) -> None:
        """
        Удаляет элемент по индексу с восстановлением инварианта кучи.

        Args:
            index: Индекс удаляемого элемента.

        Примечания:
            - Если индекс вне диапазона, метод ничего не делает.
        """
        with self._mutation("remove_at"):
            # --- Проверка внутреннего состояния ---
            if not hasattr(self, "data"):
                raise AttributeError("Heap has no internal 'data' storage (self.data)")

            if not isinstance(self.data, list):
                raise TypeError("Internal heap storage self.data повреждён — ожидается list")

            n = len(self.data)
            if not (0 <= index < n):
                # Вне диапазона — действительно «ничего не делаем»
                return

            # --- Удаляем последний элемент ---
            try:
                last = self.data.pop()
            except Exception as exc:
                raise RuntimeError(f"pop() failed in _remove_at(): {exc}") from exc

            # Если удаляем последний элемент — куча по-прежнему валидна
            if index == n - 1:
                size = len(self.data)  # должно быть n - 1
                try:
                    self._notify("remove_at", index=index, size=size)
                except Exception as exc:
                    raise RuntimeError(f"_notify() failed in _remove_at(): {exc}") from exc
                return

            # --- Переносим последний элемент на место удалённого ---
            self.data[index] = last

            # --- Выбираем направление просеивания ---
            try:
                if index > 0:
                    parent = (index - 1) // 2
                    try:
                        needs_up = self.data[index] < self.data[parent]
                    except Exception as exc:
                        raise RuntimeError(
                            f"Comparison failed in _remove_at() at index {index}: {exc}"
                        ) from exc
                else:
                    # Корень — поднимать некуда, только вниз
                    needs_up = False

                if needs_up:
                    self._heapify_up(index)
                else:
                    self._heapify_down(index)
            except Exception as exc:
                raise RuntimeError(
                    f"Heapify failed in _remove_at() at index {index}: {exc}"
                ) from exc

            # --- Sanity-check размера ---
            size = len(self.data)
            if size != n - 1:
                raise RuntimeError(
                    f"_remove_at() corrupted heap size: expected {n - 1}, got {size}"
                )

            # --- Нотификация об успешном удалении ---
            try:
                self._notify("remove_at", index=index, size=size)
            except Exception as exc:
                # На этом этапе куча уже валидна; падаем только по причине логгера
                raise RuntimeError(f"_notify() failed in _remove_at(): {exc}") from exc

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
        # Гарантируем наличие служебных полей
        if not hasattr(self, "_mutating"):
            self._mutating: bool = False
        if not hasattr(self, "_ops"):
            self._ops: int = 0

        if self._mutating:
            raise RuntimeError(f"Re-entrant heap mutation in '{opname}'")

        self._mutating = True
        exc: Optional[BaseException] = None

        try:
            yield
        except BaseException as e:
            # Запоминаем исходное исключение, чтобы не потерять
            exc = e
            raise
        finally:
            # Всегда снимаем флаг, даже если внутри всё упало
            self._mutating = False

            # Аккуратно увеличиваем счётчик операций
            try:
                self._ops = int(self._ops) + 1
            except Exception:
                # В случае порчи счётчика — жёсткий ресет
                self._ops = 1

            # Верификация структуры: не должна ломать основной поток исключений
            verifier = getattr(self, "_maybe_verify", None)
            if callable(verifier):
                try:
                    verifier()
                except Exception as verify_exc:
                    # Если уже есть основное исключение — не перебиваем его
                    if exc is None:
                        # здесь по желанию:
                        # - либо поднять RuntimeError
                        # - либо только залогировать
                        raise RuntimeError(
                            f"Heap verification failed after '{opname}': {verify_exc}"
                        ) from verify_exc
                    # если exc не None — просто проглатываем verify-ошибку

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

    # ---------- ENHANCED FUNCTIONALITY ----------

    def nlargest(self, n: int) -> List[T]:
        """
        Возвращает n наибольших элементов (если это min-heap) или
        n наименьших (если это max-heap) **без** изменения структуры.

        Args:
            n: Количество элементов для возврата.

        Returns:
            Список из n элементов. Порядок — от большего к меньшему для min-heap
            и от меньшего к большему для max-heap.
        """
        if n <= 0:
            return []

        # Используем сортировку с учётом key() и nan_policy
        # Для min-heap берём самые большие (reverse=True), для max-heap — самые маленькие.
        try:
            sorted_data = sorted(self.data, key=self._k, reverse=self.min_heap)
        except Exception as e:
            # В случае проблем с key()/nan_policy пробрасываем ValueError наружу
            raise ValueError(f"Failed to compute keys for nlargest(): {e}") from e

        return sorted_data[: min(n, len(sorted_data))]

    def pushpop(self, value: T) -> T:
        """
        Эквивалент последовательности push -> pop, но более эффективный.

        Args:
            value: Значение для добавления.

        Returns:
            Корневой элемент после вставки (может быть value или старый корень).
        """
        with self._mutation("pushpop"):
            if not self.data or self._prefer(value, self.data[0]):
                # Если куча пуста или новый элемент хуже корня
                return value

            # Сохраняем текущий корень
            root = self.data[0]

            # Заменяем корень новым значением и восстанавливаем инвариант
            self.data[0] = value
            self._notify("replace_root", old_value=root, new_value=value)
            self._heapify_down(0)

            return root

    def replace(self, value: T) -> T:
        """
        Эквивалент pop -> push, но более эффективный.

        Args:
            value: Значение для добавления.

        Returns:
            Извлечённый корневой элемент (старый корень).

        Raises:
            IndexError: Если куча пуста. Для пустой кучи используйте push().
        """
        if not self.data:
            raise IndexError("replace() on an empty heap; use push() instead")

        with self._mutation("replace"):
            root = self.data[0]
            self.data[0] = value
            self._notify("replace_root", old_value=root, new_value=value)
            self._heapify_down(0)

            return root

    def merge(self, other: 'Heap[T]') -> None:
        """
        Эффективно объединяет две кучи с одинаковыми параметрами.

        Args:
            other: Другая куча для объединения.

        Raises:
            ValueError: Если кучи имеют разные параметры сравнения.
        """
        if (self.min_heap != other.min_heap or
                self.key != other.key or
                self._nan_policy != other._nan_policy):
            raise ValueError("Cannot merge heaps with different comparison parameters")

        if not other.data:
            return

        with self._mutation("merge"):
            old_size = len(self.data)
            self.data.extend(other.data)
            self.heapify()
            self._notify("merge", added=len(other.data), old_size=old_size)

    def items(self) -> List[T]:
        """
        Возвращает все элементы кучи в виде списка.
        Альтернатива to_list() с более интуитивным именем.
        """
        return self.to_list()

    def __iter__(self):
        """
        Поддержка итерации по элементам кучи (без гарантии порядка!).
        Для получения элементов в отсортированном порядке используйте destructive_iter().
        """
        return iter(self.data)

    def destructive_iter(self):
        """
        Итератор, который возвращает элементы в отсортированном порядке,
        извлекая их из кучи (разрушающая операция).
        """
        while self.data:
            yield self.pop()

    def __contains__(self, value: T) -> bool:
        """
        Поддержка оператора 'in' для проверки наличия элемента.

        Внимание: Линейный поиск! Для частых проверок рассмотрите
        использование дополнительной структуры данных.
        """
        return value in self.data

    def count(self, value: T) -> int:
        """
        Подсчитывает количество вхождений значения в кучу.

        Внимание: Линейный поиск по всем элементам!
        """
        return self.data.count(value)

    # ---------- STATISTICS AND METRICS ----------

    def depth(self) -> int:
        """
        Возвращает глубину (высоту) бинарной кучи.

        Returns:
            Количество уровней в дереве.
        """
        if not self.data:
            return 0
        return int(math.log2(len(self.data))) + 1

    def is_perfect(self) -> bool:
        """
        Проверяет, является ли куча идеально сбалансированным деревом.

        Returns:
            True если количество элементов равно 2^h - 1 для некоторого h.
        """
        n = len(self.data)
        return (n & (n + 1)) == 0

    def get_stats(self) -> Dict[str, Any]:
        """
        Возвращает статистику кучи для отладки и мониторинга.
        """
        return {
            "size": len(self.data),
            "mode": "min" if self.min_heap else "max",
            "depth": self.depth(),
            "is_perfect": self.is_perfect(),
            "is_valid": self.is_valid_heap(),
            "operations_count": self._ops,
            "has_observer": self._observer is not None,
            "verify_rate": self._verify_sr,
            "nan_policy": self._nan_policy
        }

    # ---------- VISUALIZATION HELPER ----------

    def to_tree_repr(self, max_depth: int = 4) -> List[str]:
        """
        Генерирует текстовое представление дерева для визуализации.

        Args:
            max_depth: Максимальная глубина для отображения.

        Returns:
            Список строк, представляющих уровни дерева.
        """
        if not self.data:
            return ["[Empty heap]"]

        result = []
        n = len(self.data)
        depth = min(self.depth(), max_depth)

        for level in range(depth):
            start = 2 ** level - 1
            end = min(2 ** (level + 1) - 1, n)
            level_items = []

            for i in range(start, end):
                if i < n:
                    item_str = str(self.data[i])
                    if len(item_str) > 10:
                        item_str = item_str[:10] + "..."
                    level_items.append(item_str)

            indent = " " * (2 ** (depth - level) - 2)
            separator = " " * (2 ** (depth - level + 1) - 2)
            result.append(f"{indent}{separator.join(level_items)}")

        if len(self.data) > 2 ** max_depth - 1:
            result.append(f"... and {len(self.data) - (2 ** max_depth - 1)} more items")

        return result

    def print_tree(self, max_depth: int = 4) -> None:
        """
        Печатает дерево в удобочитаемом формате.
        """
        for line in self.to_tree_repr(max_depth):
            print(line)
