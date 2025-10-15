class Heap:
    def __init__(self, min_heap=True):
        self.data = []
        self.min_heap = min_heap

    def push(self, value):
        """Добавляет элемент и восстанавливает свойство кучи"""
        self.data.append(value)
        self._heapify_up(len(self.data) - 1)

    def pop(self):
        """Удаляет корень кучи"""
        if not self.data:
            return None
        root = self.data[0]
        last = self.data.pop()
        if self.data:
            self.data[0] = last
            self._heapify_down(0)
        return root

    def _compare(self, a, b):
        return a < b if self.min_heap else a > b

    def _heapify_up(self, index):
        # TODO: реализовать просеивание вверх
        pass

    def _heapify_down(self, index):
        # TODO: реализовать просеивание вниз
        pass

    def clear(self):
        self.data.clear()
