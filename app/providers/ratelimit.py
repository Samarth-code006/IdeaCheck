"""Small process-local token bucket for bounded free-tier request rates."""
import threading
import time


class TokenBucket:
    def __init__(self, requests_per_minute: int):
        self.capacity=max(1,requests_per_minute)
        self.tokens=float(self.capacity)
        self.refill_per_second=self.capacity/60
        self.updated=time.monotonic()
        self.lock=threading.Lock()

    def acquire(self) -> None:
        while True:
            with self.lock:
                now=time.monotonic()
                self.tokens=min(self.capacity,self.tokens+(now-self.updated)*self.refill_per_second)
                self.updated=now
                if self.tokens>=1:
                    self.tokens-=1
                    return
                wait=(1-self.tokens)/self.refill_per_second
            time.sleep(wait)
