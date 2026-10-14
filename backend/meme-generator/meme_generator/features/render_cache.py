"""Short-lived private in-memory cache, bounded by bytes and entries."""
from collections import OrderedDict
import time


class RenderCache:
    def __init__(self, max_bytes=8*1024*1024, max_entries=16, ttl=120):
        self.max_bytes=max_bytes;self.max_entries=max_entries;self.ttl=ttl
        self.items=OrderedDict();self.bytes=0

    def get(self, key):
        self.prune()
        item=self.items.get(key)
        if not item:return None
        self.items.move_to_end(key)
        return item[1]

    def put(self, key, content):
        self.prune()
        if len(content)>self.max_bytes:return
        if key in self.items:self.bytes-=len(self.items.pop(key)[1])
        self.items[key]=(time.monotonic(),content);self.bytes+=len(content)
        while self.bytes>self.max_bytes or len(self.items)>self.max_entries:
            self.bytes-=len(self.items.popitem(last=False)[1][1])

    def prune(self):
        now=time.monotonic()
        for key in list(self.items):
            if now-self.items[key][0]>self.ttl:self.bytes-=len(self.items.pop(key)[1])
