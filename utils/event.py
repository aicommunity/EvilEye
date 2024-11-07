from threading import Lock

events = dict()
mutex = Lock()


def subscribe(event, subscriber_func):
    if event not in events:
        events[event] = []
    events[event].append(subscriber_func)


def notify(event, *args, **kwargs):
    if mutex.acquire(blocking=False):
        try:
            if event not in events:
                return
            for func in events[event]:
                func(*args, **kwargs)
        finally:
            mutex.release()
