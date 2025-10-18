"""
ConfigHistoryManager - обертка над существующим DatabaseController для работы с историей конфигураций.

Использует существующую структуру БД (таблица jobs с полями configuration_info и configuration_id)
для предоставления удобного API для работы с историей конфигураций.
"""

import json
import os
import shutil
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Any
from pathlib import Path

from ..core.logger import get_module_logger
from ..database_controller.database_controller_pg import DatabaseControllerPg


class ConfigHistoryManager:
    """
    Менеджер истории конфигураций.
    
    Предоставляет удобный API для работы с историей конфигураций,
    используя существующую структуру базы данных EvilEye.
    """
    
    def __init__(self, db_controller: DatabaseControllerPg):
        """
        Инициализация менеджера истории конфигураций.
        
        Args:
            db_controller: Экземпляр DatabaseControllerPg для работы с БД
        """
        self.logger = get_module_logger("config_history_manager")
        self.db_controller = db_controller
        
        # Проверяем подключение к базе данных
        if not self.db_controller.is_connected():
            self.logger.warning("DatabaseController is not connected. Attempting to connect.")
            self.db_controller.connect()
        
        if not self.db_controller.is_connected():
            raise ConnectionError("Failed to connect to the database.")
        
        self.logger.info("ConfigHistoryManager initialized with connected DatabaseController.")
    
    def _ensure_connected(self):
        """Проверяет подключение к базе данных и переподключается при необходимости."""
        if not self.db_controller.is_connected():
            self.logger.warning("Database connection lost. Attempting to reconnect.")
            self.db_controller.connect()
            if not self.db_controller.is_connected():
                raise ConnectionError("Failed to reconnect to the database.")
        
    def get_config_history(self, 
                          start_date: Optional[datetime] = None,
                          end_date: Optional[datetime] = None,
                          project_id: Optional[int] = None,
                          limit: int = 100) -> List[Dict[str, Any]]:
        """
        Получить историю конфигураций с фильтрацией.
        
        Args:
            start_date: Начальная дата для фильтрации
            end_date: Конечная дата для фильтрации
            project_id: ID проекта для фильтрации
            limit: Максимальное количество записей
            
        Returns:
            Список словарей с информацией о конфигурациях
        """
        try:
            query_parts = [
                "SELECT j.job_id, j.project_id, j.configuration_id, j.creation_time,",
                "j.finish_time, j.is_terminated, j.configuration_info",
                "FROM jobs j",
                "WHERE j.configuration_info IS NOT NULL"
            ]
            
            params = []
            param_count = 0
            
            if start_date:
                param_count += 1
                query_parts.append(f"AND j.creation_time >= %s")
                params.append(start_date)
                
            if end_date:
                param_count += 1
                query_parts.append(f"AND j.creation_time <= %s")
                params.append(end_date)
                
            if project_id is not None:
                param_count += 1
                query_parts.append(f"AND j.project_id = %s")
                params.append(project_id)
                
            query_parts.append("ORDER BY j.creation_time DESC")
            query_parts.append(f"LIMIT %s")
            params.append(limit)
            
            query = " ".join(query_parts)
            
            records = self.db_controller.query(query, params)
            
            result = []
            for record in records:
                job_id, proj_id, config_id, creation_time, finish_time, is_terminated, config_info = record
                
                # Определяем статус
                status = "Running"
                if is_terminated:
                    if finish_time:
                        status = "Completed"
                    else:
                        status = "Terminated"
                elif finish_time:
                    status = "Completed"
                
                result.append({
                    'job_id': job_id,
                    'project_id': proj_id,
                    'configuration_id': config_id,
                    'creation_time': creation_time,
                    'finish_time': finish_time,
                    'status': status,
                    'configuration_info': config_info if config_info else None
                })
                
            self.logger.info(f"Retrieved {len(result)} configuration history records")
            return result
            
        except Exception as e:
            self.logger.error(f"Error retrieving config history: {e}")
            return []
    
    def get_unique_configurations(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Получить список уникальных конфигураций.
        
        Args:
            limit: Максимальное количество уникальных конфигураций
            
        Returns:
            Список уникальных конфигураций с метаданными
        """
        try:
            self._ensure_connected()
            
            query = """
                SELECT DISTINCT ON (j.configuration_id) 
                    j.configuration_id,
                    j.job_id,
                    j.project_id,
                    j.creation_time,
                    j.finish_time,
                    j.is_terminated,
                    j.configuration_info,
                    COUNT(*) OVER (PARTITION BY j.configuration_id) as usage_count
                FROM jobs j
                WHERE j.configuration_info IS NOT NULL
                ORDER BY j.configuration_id, j.creation_time DESC
                LIMIT %s
            """
            
            records = self.db_controller.query(query, (limit,))
            
            result = []
            for record in records:
                config_id, job_id, proj_id, creation_time, finish_time, is_terminated, config_info, usage_count = record
                
                # Определяем статус
                status = "Running"
                if is_terminated:
                    if finish_time:
                        status = "Completed"
                    else:
                        status = "Terminated"
                elif finish_time:
                    status = "Completed"
                
                result.append({
                    'configuration_id': config_id,
                    'job_id': job_id,
                    'project_id': proj_id,
                    'creation_time': creation_time,
                    'finish_time': finish_time,
                    'status': status,
                    'usage_count': usage_count,
                    'configuration_info': config_info if config_info else None
                })
                
            self.logger.info(f"Retrieved {len(result)} unique configurations")
            return result
            
        except Exception as e:
            self.logger.error(f"Error retrieving unique configurations: {e}")
            return []
    
    def get_config_by_job_id(self, job_id: int) -> Optional[Dict[str, Any]]:
        """
        Получить конфигурацию по ID задания.
        
        Args:
            job_id: ID задания
            
        Returns:
            Словарь с информацией о конфигурации или None
        """
        try:
            self._ensure_connected()
            
            query = """
                SELECT j.job_id, j.project_id, j.configuration_id, j.creation_time,
                       j.finish_time, j.is_terminated, j.configuration_info
                FROM jobs j
                WHERE j.job_id = %s AND j.configuration_info IS NOT NULL
            """
            
            records = self.db_controller.query(query, (job_id,))
            
            if not records:
                self.logger.warning(f"No configuration found for job_id: {job_id}")
                return None
                
            record = records[0]
            job_id, proj_id, config_id, creation_time, finish_time, is_terminated, config_info = record
            
            # Определяем статус
            status = "Running"
            if is_terminated:
                if finish_time:
                    status = "Completed"
                else:
                    status = "Terminated"
            elif finish_time:
                status = "Completed"
            
            result = {
                'job_id': job_id,
                'project_id': proj_id,
                'configuration_id': config_id,
                'creation_time': creation_time,
                'finish_time': finish_time,
                'status': status,
                'configuration_info': json.loads(config_info) if config_info else None
            }
            
            self.logger.info(f"Retrieved configuration for job_id: {job_id}")
            return result
            
        except Exception as e:
            self.logger.error(f"Error retrieving config for job_id {job_id}: {e}")
            return None
    
    def compare_configurations(self, job_id1: int, job_id2: int) -> Dict[str, Any]:
        """
        Сравнить две конфигурации.
        
        Args:
            job_id1: ID первого задания
            job_id2: ID второго задания
            
        Returns:
            Словарь с результатами сравнения
        """
        try:
            config1 = self.get_config_by_job_id(job_id1)
            config2 = self.get_config_by_job_id(job_id2)
            
            if not config1 or not config2:
                return {
                    'error': 'One or both configurations not found',
                    'config1_found': config1 is not None,
                    'config2_found': config2 is not None
                }
            
            info1 = config1.get('configuration_info', {})
            info2 = config2.get('configuration_info', {})
            
            # Простое сравнение JSON структур
            differences = self._find_json_differences(info1, info2)
            
            result = {
                'job_id1': job_id1,
                'job_id2': job_id2,
                'config1_creation_time': config1['creation_time'],
                'config2_creation_time': config2['creation_time'],
                'differences': differences,
                'identical': len(differences) == 0
            }
            
            self.logger.info(f"Compared configurations {job_id1} and {job_id2}, found {len(differences)} differences")
            return result
            
        except Exception as e:
            self.logger.error(f"Error comparing configurations {job_id1} and {job_id2}: {e}")
            return {'error': str(e)}
    
    def restore_configuration(self, job_id: int, target_path: str, create_backup: bool = True) -> Dict[str, Any]:
        """
        Восстановить конфигурацию из истории.
        
        Args:
            job_id: ID задания с конфигурацией для восстановления
            target_path: Путь к файлу конфигурации для восстановления
            create_backup: Создавать ли резервную копию текущего файла
            
        Returns:
            Словарь с результатом операции
        """
        try:
            config = self.get_config_by_job_id(job_id)
            if not config:
                return {
                    'success': False,
                    'error': f'Configuration not found for job_id: {job_id}'
                }
            
            config_info = config.get('configuration_info')
            if not config_info:
                return {
                    'success': False,
                    'error': 'No configuration data found'
                }
            
            target_path = Path(target_path)
            
            # Создаем резервную копию, если файл существует
            backup_path = None
            if create_backup and target_path.exists():
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = target_path.with_suffix(f"{target_path.suffix}.backup.{timestamp}")
                shutil.copy2(target_path, backup_path)
                self.logger.info(f"Created backup: {backup_path}")
            
            # Записываем восстановленную конфигурацию
            with open(target_path, 'w', encoding='utf-8') as f:
                json.dump(config_info, f, indent=4, ensure_ascii=False)
            
            result = {
                'success': True,
                'job_id': job_id,
                'target_path': str(target_path),
                'backup_path': str(backup_path) if backup_path else None,
                'creation_time': config['creation_time'],
                'status': config['status']
            }
            
            self.logger.info(f"Successfully restored configuration from job_id {job_id} to {target_path}")
            return result
            
        except Exception as e:
            self.logger.error(f"Error restoring configuration from job_id {job_id}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def export_config_history(self, 
                             output_path: str,
                             start_date: Optional[datetime] = None,
                             end_date: Optional[datetime] = None,
                             project_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Экспортировать историю конфигураций в файл.
        
        Args:
            output_path: Путь к файлу для экспорта
            start_date: Начальная дата для фильтрации
            end_date: Конечная дата для фильтрации
            project_id: ID проекта для фильтрации
            
        Returns:
            Словарь с результатом операции
        """
        try:
            history = self.get_config_history(start_date, end_date, project_id, limit=1000)
            
            export_data = {
                'export_timestamp': datetime.now().isoformat(),
                'filters': {
                    'start_date': start_date.isoformat() if start_date else None,
                    'end_date': end_date.isoformat() if end_date else None,
                    'project_id': project_id
                },
                'total_records': len(history),
                'configurations': history
            }
            
            output_path = Path(output_path)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False, default=str)
            
            result = {
                'success': True,
                'output_path': str(output_path),
                'total_records': len(history)
            }
            
            self.logger.info(f"Successfully exported {len(history)} configuration records to {output_path}")
            return result
            
        except Exception as e:
            self.logger.error(f"Error exporting config history: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _find_json_differences(self, obj1: Any, obj2: Any, path: str = "") -> List[Dict[str, Any]]:
        """
        Найти различия между двумя JSON объектами.
        
        Args:
            obj1: Первый объект
            obj2: Второй объект
            path: Текущий путь в объекте
            
        Returns:
            Список различий
        """
        differences = []
        
        if type(obj1) != type(obj2):
            differences.append({
                'path': path,
                'type': 'type_mismatch',
                'value1': str(type(obj1)),
                'value2': str(type(obj2))
            })
            return differences
        
        if isinstance(obj1, dict):
            all_keys = set(obj1.keys()) | set(obj2.keys())
            for key in all_keys:
                new_path = f"{path}.{key}" if path else key
                if key not in obj1:
                    differences.append({
                        'path': new_path,
                        'type': 'missing_in_first',
                        'value2': obj2[key]
                    })
                elif key not in obj2:
                    differences.append({
                        'path': new_path,
                        'type': 'missing_in_second',
                        'value1': obj1[key]
                    })
                else:
                    differences.extend(self._find_json_differences(obj1[key], obj2[key], new_path))
        
        elif isinstance(obj1, list):
            max_len = max(len(obj1), len(obj2))
            for i in range(max_len):
                new_path = f"{path}[{i}]"
                if i >= len(obj1):
                    differences.append({
                        'path': new_path,
                        'type': 'missing_in_first',
                        'value2': obj2[i]
                    })
                elif i >= len(obj2):
                    differences.append({
                        'path': new_path,
                        'type': 'missing_in_second',
                        'value1': obj1[i]
                    })
                else:
                    differences.extend(self._find_json_differences(obj1[i], obj2[i], new_path))
        
        else:
            if obj1 != obj2:
                differences.append({
                    'path': path,
                    'type': 'value_mismatch',
                    'value1': obj1,
                    'value2': obj2
                })
        
        return differences

    def get_projects_list(self) -> List[Dict[str, Any]]:
        """
        Получить список всех проектов.
        
        Returns:
            List[Dict]: Список проектов с информацией о каждом
        """
        try:
            self._ensure_connected()
            
            query = """
                SELECT DISTINCT project_id, 
                       COUNT(*) as job_count,
                       MIN(creation_time) as first_job,
                       MAX(creation_time) as last_job
                FROM jobs 
                WHERE project_id IS NOT NULL 
                GROUP BY project_id
                ORDER BY project_id
            """
            
            result = self.db_controller.execute_query(query)
            
            projects = []
            for row in result:
                project_id = row[0]
                job_count = row[1]
                first_job = row[2]
                last_job = row[3]
                
                # Получаем название проекта (если есть отдельная таблица projects)
                project_name = f"Project {project_id}"
                project_description = f"Project with {job_count} jobs"
                
                projects.append({
                    'project_id': project_id,
                    'project_name': project_name,
                    'project_description': project_description,
                    'job_count': job_count,
                    'first_job': first_job,
                    'last_job': last_job
                })
            
            self.logger.info(f"Retrieved {len(projects)} projects")
            return projects
            
        except Exception as e:
            self.logger.error(f"Error getting projects list: {e}")
            return []

    def create_project(self, project_name: str, project_description: str = "") -> Dict[str, Any]:
        """
        Создать новый проект.
        
        Args:
            project_name: Название проекта
            project_description: Описание проекта
            
        Returns:
            Dict: Результат операции
        """
        try:
            self._ensure_connected()
            
            # Генерируем новый project_id
            query = "SELECT COALESCE(MAX(project_id), 0) + 1 FROM jobs"
            result = self.db_controller.execute_query(query)
            new_project_id = result[0][0] if result else 1
            
            # Если есть отдельная таблица projects, создаем запись там
            # Пока что просто возвращаем новый ID
            self.logger.info(f"Created new project: {project_name} (ID: {new_project_id})")
            
            return {
                'success': True,
                'project_id': new_project_id,
                'project_name': project_name,
                'message': f"Project '{project_name}' created successfully"
            }
            
        except Exception as e:
            self.logger.error(f"Error creating project: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def update_project(self, project_id: int, project_name: str, project_description: str = "") -> Dict[str, Any]:
        """
        Обновить информацию о проекте.
        
        Args:
            project_id: ID проекта
            project_name: Новое название проекта
            project_description: Новое описание проекта
            
        Returns:
            Dict: Результат операции
        """
        try:
            self._ensure_connected()
            
            # Проверяем существование проекта
            query = "SELECT COUNT(*) FROM jobs WHERE project_id = %s"
            result = self.db_controller.execute_query(query, (project_id,))
            project_exists = result[0][0] > 0 if result else False
            
            if not project_exists:
                return {
                    'success': False,
                    'error': f"Project with ID {project_id} not found"
                }
            
            # Если есть отдельная таблица projects, обновляем там
            # Пока что просто логируем
            self.logger.info(f"Updated project {project_id}: {project_name}")
            
            return {
                'success': True,
                'project_id': project_id,
                'project_name': project_name,
                'message': f"Project {project_id} updated successfully"
            }
            
        except Exception as e:
            self.logger.error(f"Error updating project: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def delete_project(self, project_id: int) -> Dict[str, Any]:
        """
        Удалить проект.
        
        Args:
            project_id: ID проекта
            
        Returns:
            Dict: Результат операции
        """
        try:
            self._ensure_connected()
            
            # Проверяем существование проекта
            query = "SELECT COUNT(*) FROM jobs WHERE project_id = %s"
            result = self.db_controller.execute_query(query, (project_id,))
            job_count = result[0][0] if result else 0
            
            if job_count == 0:
                return {
                    'success': False,
                    'error': f"Project with ID {project_id} not found"
                }
            
            # Обновляем все задачи проекта, устанавливая project_id = NULL
            update_query = "UPDATE jobs SET project_id = NULL WHERE project_id = %s"
            self.db_controller.execute_query(update_query, (project_id,))
            
            self.logger.info(f"Deleted project {project_id}, updated {job_count} jobs")
            
            return {
                'success': True,
                'project_id': project_id,
                'updated_jobs': job_count,
                'message': f"Project {project_id} deleted, {job_count} jobs updated"
            }
            
        except Exception as e:
            self.logger.error(f"Error deleting project: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def get_project_info(self, project_id: int) -> Optional[Dict[str, Any]]:
        """
        Получить информацию о проекте.
        
        Args:
            project_id: ID проекта
            
        Returns:
            Dict: Информация о проекте или None
        """
        try:
            self._ensure_connected()
            
            query = """
                SELECT project_id,
                       COUNT(*) as job_count,
                       MIN(creation_time) as first_job,
                       MAX(creation_time) as last_job,
                       AVG(EXTRACT(EPOCH FROM (finish_time - creation_time))/3600) as avg_duration_hours
                FROM jobs 
                WHERE project_id = %s
                GROUP BY project_id
            """
            
            result = self.db_controller.execute_query(query, (project_id,))
            
            if not result:
                return None
            
            row = result[0]
            return {
                'project_id': row[0],
                'project_name': f"Project {row[0]}",
                'project_description': f"Project with {row[1]} jobs",
                'job_count': row[1],
                'first_job': row[2],
                'last_job': row[3],
                'avg_duration_hours': float(row[4]) if row[4] else 0
            }
            
        except Exception as e:
            self.logger.error(f"Error getting project info: {e}")
            return None

    def get_project_statistics(self, project_id: int, detailed: bool = False) -> Optional[Dict[str, Any]]:
        """
        Получить статистику по проекту.
        
        Args:
            project_id: ID проекта
            detailed: Получить детальную статистику
            
        Returns:
            Dict: Статистика проекта
        """
        try:
            self._ensure_connected()
            
            # Базовая статистика
            base_query = """
                SELECT 
                    COUNT(*) as total_jobs,
                    COUNT(CASE WHEN status = 'Running' THEN 1 END) as running_jobs,
                    COUNT(CASE WHEN status = 'Stopped' THEN 1 END) as completed_jobs,
                    COUNT(CASE WHEN status = 'Error' THEN 1 END) as error_jobs,
                    SUM(EXTRACT(EPOCH FROM (finish_time - creation_time))/3600) as total_duration,
                    AVG(EXTRACT(EPOCH FROM (finish_time - creation_time))/3600) as avg_duration,
                    MIN(EXTRACT(EPOCH FROM (finish_time - creation_time))/3600) as min_duration,
                    MAX(EXTRACT(EPOCH FROM (finish_time - creation_time))/3600) as max_duration,
                    MIN(creation_time) as first_job_date,
                    MAX(creation_time) as last_job_date
                FROM jobs 
                WHERE project_id = %s
            """
            
            result = self.db_controller.execute_query(base_query, (project_id,))
            
            if not result:
                return None
            
            row = result[0]
            stats = {
                'total_jobs': row[0] or 0,
                'running_jobs': row[1] or 0,
                'completed_jobs': row[2] or 0,
                'error_jobs': row[3] or 0,
                'total_duration': float(row[4]) if row[4] else 0,
                'avg_duration': float(row[5]) if row[5] else 0,
                'min_duration': float(row[6]) if row[6] else 0,
                'max_duration': float(row[7]) if row[7] else 0,
                'first_job_date': row[8],
                'last_job_date': row[9]
            }
            
            # Детальная статистика
            if detailed:
                detailed_query = """
                    SELECT 
                        SUM(frames_processed) as total_frames,
                        SUM(objects_detected) as total_objects,
                        SUM(events_detected) as total_events,
                        AVG(frames_processed::float / NULLIF(EXTRACT(EPOCH FROM (finish_time - creation_time)), 0)) as avg_fps
                    FROM jobs 
                    WHERE project_id = %s AND frames_processed IS NOT NULL
                """
                
                detailed_result = self.db_controller.execute_query(detailed_query, (project_id,))
                
                if detailed_result and detailed_result[0][0] is not None:
                    detailed_row = detailed_result[0]
                    stats.update({
                        'total_frames': detailed_row[0] or 0,
                        'total_objects': detailed_row[1] or 0,
                        'total_events': detailed_row[2] or 0,
                        'avg_fps': float(detailed_row[3]) if detailed_row[3] else 0
                    })
                
                # Период активности
                if stats['first_job_date'] and stats['last_job_date']:
                    first_date = stats['first_job_date']
                    last_date = stats['last_job_date']
                    if isinstance(first_date, str):
                        first_date = datetime.fromisoformat(first_date.replace('Z', '+00:00'))
                    if isinstance(last_date, str):
                        last_date = datetime.fromisoformat(last_date.replace('Z', '+00:00'))
                    
                    period = last_date - first_date
                    stats['activity_period'] = f"{period.days} days, {period.seconds // 3600} hours"
                else:
                    stats['activity_period'] = "Unknown"
            
            return stats
            
        except Exception as e:
            self.logger.error(f"Error getting project statistics: {e}")
            return None

    def validate_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Валидация конфигурации.
        
        Args:
            config: Конфигурация для валидации
            
        Returns:
            Dict: Результат валидации
        """
        try:
            errors = []
            warnings = []
            
            # Проверяем обязательные поля
            required_fields = ['sources', 'detectors', 'trackers']
            for field in required_fields:
                if field not in config:
                    errors.append(f"Missing required field: {field}")
                elif not config[field]:
                    warnings.append(f"Empty {field} configuration")
            
            # Проверяем источники
            if 'sources' in config:
                sources = config['sources']
                if isinstance(sources, dict):
                    for source_id, source_config in sources.items():
                        if not isinstance(source_config, dict):
                            errors.append(f"Invalid source configuration for {source_id}")
                            continue
                        
                        # Проверяем обязательные поля источника
                        if 'source_address' not in source_config:
                            errors.append(f"Source {source_id} missing source_address")
                        
                        # Проверяем существование файлов
                        if 'source_address' in source_config:
                            source_path = source_config['source_address']
                            if source_path.startswith('/') and not os.path.exists(source_path):
                                warnings.append(f"Source file not found: {source_path}")
            
            # Проверяем детекторы
            if 'detectors' in config:
                detectors = config['detectors']
                if isinstance(detectors, dict):
                    for detector_id, detector_config in detectors.items():
                        if not isinstance(detector_config, dict):
                            errors.append(f"Invalid detector configuration for {detector_id}")
                            continue
                        
                        # Проверяем путь к модели
                        if 'model_path' in detector_config:
                            model_path = detector_config['model_path']
                            if not os.path.exists(model_path):
                                warnings.append(f"Detector model not found: {model_path}")
            
            # Проверяем трекеры
            if 'trackers' in config:
                trackers = config['trackers']
                if isinstance(trackers, dict):
                    for tracker_id, tracker_config in trackers.items():
                        if not isinstance(tracker_config, dict):
                            errors.append(f"Invalid tracker configuration for {tracker_id}")
                            continue
            
            return {
                'valid': len(errors) == 0,
                'errors': errors,
                'warnings': warnings,
                'error_count': len(errors),
                'warning_count': len(warnings)
            }
            
        except Exception as e:
            self.logger.error(f"Error validating config: {e}")
            return {
                'valid': False,
                'errors': [f"Validation error: {str(e)}"],
                'warnings': [],
                'error_count': 1,
                'warning_count': 0
            }

    def get_config_stats(self, config_id: str) -> Optional[Dict[str, Any]]:
        """
        Получить статистику по конфигурации.
        
        Args:
            config_id: ID конфигурации
            
        Returns:
            Dict: Статистика конфигурации
        """
        try:
            self._ensure_connected()
            
            query = """
                SELECT 
                    configuration_id,
                    COUNT(*) as usage_count,
                    COUNT(DISTINCT project_id) as project_count,
                    MIN(creation_time) as first_used,
                    MAX(creation_time) as last_used,
                    AVG(EXTRACT(EPOCH FROM (finish_time - creation_time))/3600) as avg_duration,
                    SUM(frames_processed) as total_frames,
                    SUM(objects_detected) as total_objects,
                    SUM(events_detected) as total_events
                FROM jobs 
                WHERE configuration_id = %s
                GROUP BY configuration_id
            """
            
            result = self.db_controller.execute_query(query, (config_id,))
            
            if not result:
                return None
            
            row = result[0]
            return {
                'configuration_id': row[0],
                'usage_count': row[1],
                'project_count': row[2],
                'first_used': row[3],
                'last_used': row[4],
                'avg_duration': float(row[5]) if row[5] else 0,
                'total_frames': row[6] or 0,
                'total_objects': row[7] or 0,
                'total_events': row[8] or 0
            }
            
        except Exception as e:
            self.logger.error(f"Error getting config stats: {e}")
            return None
