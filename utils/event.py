events = dict()


def subscribe(event, subscriber_func):
    if event not in events:
        events[event] = []
    events[event].append(subscriber_func)


def notify(event, *args, **kwargs):
    if event not in events:
        return
    for func in events[event]:
        func(*args, **kwargs)
