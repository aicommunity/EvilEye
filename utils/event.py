from threading import Lock

events = dict()
mutex = Lock()


def subscribe(event, subscriber_func):
    with mutex:
        if event not in events:
            events[event] = []
        events[event].append(subscriber_func)


def notify(event, *args, **kwargs):
    with mutex:
        if event not in events:
            return
        functions = events[event]
    for func in functions:
        func(*args, **kwargs)
