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


def unsubscribe(event, subscriber_func):
    """Remove one subscriber from a process-local event channel."""
    with mutex:
        subscribers = events.get(event)
        if not subscribers:
            return False
        try:
            subscribers.remove(subscriber_func)
        except ValueError:
            return False
        if not subscribers:
            events.pop(event, None)
        return True
