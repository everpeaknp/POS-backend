def display(*args, **kwargs):
    def decorator(func):
        return func
    if callable(args[0] if args else None):
        return decorator(args[0])
    return decorator
