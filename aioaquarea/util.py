from collections import OrderedDict


class LimitedSizeDict(OrderedDict):
    def __init__(self, max_keys: int, *args, **kwds):
        self.size_limit = max_keys
        OrderedDict.__init__(self, *args, **kwds)
        self._check_size_limit()

    def __setitem__(self, key, value):
        OrderedDict.__setitem__(self, key, value)
        self._check_size_limit()

    def _check_size_limit(self):
        if self.size_limit is not None:
            while len(self) > self.size_limit:
                self.popitem(last=False)
