from typing import Dict, Any, Optional, Type, TypeVar
from dataclasses import dataclass
import asyncio
from contextlib import asynccontextmanager

T = TypeVar('T')


@dataclass
class ServiceInfo:
    """Информация о сервисе"""
    name: str
    instance: Any
    service_type: Type
    singleton: bool = True
    dependencies: list[str] = None
    
    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = []


class ServiceContainer:
    """
    Контейнер сервисов для dependency injection.
    Управляет жизненным циклом сервисов и их зависимостями.
    """
    
    def __init__(self):
        self.services: Dict[str, ServiceInfo] = {}
        self.singletons: Dict[str, Any] = {}
        self.running = False
        self.startup_tasks = []
        self.shutdown_tasks = []
    
    def register(self, name: str, service_instance: Any, service_type: Type = None, 
                singleton: bool = True, dependencies: list[str] = None):
        """
        Регистрация сервиса
        
        Args:
            name: Имя сервиса
            service_instance: Экземпляр сервиса
            service_type: Тип сервиса
            singleton: Является ли сервис синглтоном
            dependencies: Список зависимостей сервиса
        """
        if service_type is None:
            service_type = type(service_instance)
        
        service_info = ServiceInfo(
            name=name,
            instance=service_instance,
            service_type=service_type,
            singleton=singleton,
            dependencies=dependencies or []
        )
        
        self.services[name] = service_info
        
        if singleton:
            self.singletons[name] = service_instance
        
        print(f"Registered service: {name} ({service_type.__name__})")
    
    def register_factory(self, name: str, factory_func: callable, service_type: Type = None,
                        singleton: bool = True, dependencies: list[str] = None):
        """
        Регистрация фабрики сервиса
        
        Args:
            name: Имя сервиса
            factory_func: Функция-фабрика для создания сервиса
            service_type: Тип сервиса
            singleton: Является ли сервис синглтоном
            dependencies: Список зависимостей сервиса
        """
        if service_type is None:
            # Попытка определить тип из аннотации функции
            import inspect
            sig = inspect.signature(factory_func)
            if sig.return_annotation != inspect.Signature.empty:
                service_type = sig.return_annotation
            else:
                service_type = object
        
        service_info = ServiceInfo(
            name=name,
            instance=factory_func,
            service_type=service_type,
            singleton=singleton,
            dependencies=dependencies or []
        )
        
        self.services[name] = service_info
        print(f"Registered service factory: {name} ({service_type.__name__})")
    
    def get(self, name: str) -> Any:
        """
        Получение сервиса по имени
        
        Args:
            name: Имя сервиса
            
        Returns:
            Экземпляр сервиса
            
        Raises:
            KeyError: Если сервис не найден
        """
        if name not in self.services:
            raise KeyError(f"Service '{name}' not found")
        
        service_info = self.services[name]
        
        # Если это синглтон и уже создан
        if service_info.singleton and name in self.singletons:
            return self.singletons[name]
        
        # Если это фабрика
        if callable(service_info.instance) and not hasattr(service_info.instance, '__dict__'):
            # Создаем экземпляр через фабрику
            instance = service_info.instance()
            
            if service_info.singleton:
                self.singletons[name] = instance
            
            return instance
        
        # Обычный экземпляр
        return service_info.instance
    
    def get_by_type(self, service_type: Type[T]) -> T:
        """
        Получение сервиса по типу
        
        Args:
            service_type: Тип сервиса
            
        Returns:
            Экземпляр сервиса
            
        Raises:
            KeyError: Если сервис не найден
        """
        for name, service_info in self.services.items():
            if isinstance(service_info.instance, service_type) or issubclass(service_info.service_type, service_type):
                return self.get(name)
        
        raise KeyError(f"Service of type '{service_type.__name__}' not found")
    
    def has(self, name: str) -> bool:
        """Проверка наличия сервиса"""
        return name in self.services
    
    def has_type(self, service_type: Type) -> bool:
        """Проверка наличия сервиса по типу"""
        for service_info in self.services.values():
            if isinstance(service_info.instance, service_type) or issubclass(service_info.service_type, service_type):
                return True
        return False
    
    async def start_all(self):
        """Запуск всех сервисов"""
        if self.running:
            return
        
        self.running = True
        print("Starting all services...")
        
        # Запуск сервисов в порядке зависимостей
        started_services = set()
        
        while len(started_services) < len(self.services):
            progress = False
            
            for name, service_info in self.services.items():
                if name in started_services:
                    continue
                
                # Проверяем зависимости
                dependencies_met = all(dep in started_services for dep in service_info.dependencies)
                
                if dependencies_met:
                    instance = self.get(name)
                    
                    # Запускаем сервис если у него есть метод start
                    if hasattr(instance, 'start') and callable(instance.start):
                        if asyncio.iscoroutinefunction(instance.start):
                            await instance.start()
                        else:
                            instance.start()
                    
                    started_services.add(name)
                    progress = True
                    print(f"Started service: {name}")
            
            if not progress:
                # Циклическая зависимость или недоступные зависимости
                remaining = [name for name in self.services.keys() if name not in started_services]
                print(f"Warning: Could not start services due to dependencies: {remaining}")
                break
        
        print("All services started")
    
    async def stop_all(self):
        """Остановка всех сервисов"""
        if not self.running:
            return
        
        self.running = False
        print("Stopping all services...")
        
        # Остановка сервисов в обратном порядке
        for name in reversed(list(self.services.keys())):
            try:
                instance = self.get(name)
                
                # Останавливаем сервис если у него есть метод stop
                if hasattr(instance, 'stop') and callable(instance.stop):
                    if asyncio.iscoroutinefunction(instance.stop):
                        await instance.stop()
                    else:
                        instance.stop()
                
                print(f"Stopped service: {name}")
            except Exception as e:
                print(f"Error stopping service {name}: {e}")
        
        print("All services stopped")
    
    def get_all_services(self) -> Dict[str, Any]:
        """Получение всех зарегистрированных сервисов"""
        return {name: self.get(name) for name in self.services.keys()}
    
    def get_service_info(self, name: str) -> Optional[ServiceInfo]:
        """Получение информации о сервисе"""
        return self.services.get(name)
    
    def list_services(self) -> list[str]:
        """Список всех зарегистрированных сервисов"""
        return list(self.services.keys())
    
    def clear(self):
        """Очистка всех сервисов"""
        self.services.clear()
        self.singletons.clear()
        self.running = False
        print("Service container cleared")
    
    @asynccontextmanager
    async def lifecycle(self):
        """Контекстный менеджер для управления жизненным циклом сервисов"""
        try:
            await self.start_all()
            yield self
        finally:
            await self.stop_all()
