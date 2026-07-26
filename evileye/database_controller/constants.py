"""Константы для database_controller модуля."""


class QueryType:
    """Типы SQL запросов."""
    INSERT = 'insert'
    UPDATE = 'update'
    # Для обратной совместимости
    Insert = 'Insert'
    Update = 'Update'


class EventType:
    """Типы событий для уведомлений."""
    NEW_EVENT = 'new event'
    UPDATE_EVENT = 'update event'
    HANDLER_NEW_OBJECT = 'handler new object'
    HANDLER_UPDATE_OBJECT = 'handler update object'
