"""
Centralized class management system for EvilEye.
Manages all class-related information across the system.
"""

from typing import Dict, List, Optional, Union, Any
import logging

logger = logging.getLogger(__name__)


class ClassManager:
    """
    Centralized manager for all class-related information in the system.
    
    Responsibilities:
    1. Collect class mappings from all sources (detectors, attribute classifiers)
    2. Resolve conflicts between different sources
    3. Provide unified class information to all components
    4. Support both class names and IDs in configurations
    """
    
    def __init__(self):
        self.class_mapping: Dict[str, int] = {}  # {class_name: class_id}
        self.reverse_mapping: Dict[int, str] = {}  # {class_id: class_name}
        self.sources: List[Dict[str, Any]] = []  # Track sources of class information
        self.conflicts: List[str] = []
        
    def add_class_mapping(self, mapping: Dict[str, int], source: str) -> bool:
        """
        Add class mapping from a source (detector, classifier, etc.)
        
        Args:
            mapping: Dictionary {class_name: class_id}
            source: Source identifier (e.g., "ObjectDetectorYolo", "AttributeClassifier")
            
        Returns:
            True if no conflicts, False if conflicts detected
        """
        if not mapping:
            return True
            
        logger.info(f"Adding class mapping from {source}: {mapping}")
        
        # Check for conflicts
        has_conflicts = False
        for class_name, class_id in mapping.items():
            # Check name conflicts
            if class_name in self.class_mapping:
                if self.class_mapping[class_name] != class_id:
                    conflict_msg = f"Class '{class_name}' has different IDs: {self.class_mapping[class_name]} vs {class_id} (sources: {self._get_source_for_class(class_name)} vs {source})"
                    self.conflicts.append(conflict_msg)
                    logger.warning(conflict_msg)
                    has_conflicts = True
                else:
                    # Same mapping, no conflict
                    continue
            
            # Check ID conflicts
            if class_id in self.reverse_mapping:
                if self.reverse_mapping[class_id] != class_name:
                    conflict_msg = f"Class ID {class_id} has different names: '{self.reverse_mapping[class_id]}' vs '{class_name}' (sources: {self._get_source_for_id(class_id)} vs {source})"
                    self.conflicts.append(conflict_msg)
                    logger.warning(conflict_msg)
                    has_conflicts = True
                else:
                    # Same mapping, no conflict
                    continue
            
            # No conflicts, add to mappings
            self.class_mapping[class_name] = class_id
            self.reverse_mapping[class_id] = class_name
            
        # Track source
        self.sources.append({
            'source': source,
            'mapping': mapping.copy(),
            'timestamp': self._get_timestamp()
        })
        
        return not has_conflicts
    
    def get_class_id(self, class_name: str) -> Optional[int]:
        """Get class ID from class name"""
        return self.class_mapping.get(class_name)
    
    def get_class_name(self, class_id: int) -> Optional[str]:
        """Get class name from class ID"""
        return self.reverse_mapping.get(class_id)
    
    def convert_classes_to_ids(self, classes: List[Union[str, int]]) -> List[int]:
        """
        Convert classes parameter to list of IDs.
        Supports both class names and IDs.
        
        Args:
            classes: List of class names or IDs
            
        Returns:
            List of class IDs
        """
        if not classes:
            return []
            
        result_ids = []
        invalid_classes = []
        
        for cls in classes:
            if isinstance(cls, str):
                # Class name - convert to ID
                class_id = self.get_class_id(cls)
                if class_id is not None:
                    result_ids.append(class_id)
                else:
                    invalid_classes.append(cls)
            elif isinstance(cls, int):
                # Class ID - use as is
                result_ids.append(cls)
            else:
                # Invalid type
                invalid_classes.append(str(cls))
        
        if invalid_classes:
            logger.warning(f"Invalid or unknown classes: {invalid_classes}")
            logger.info(f"Available classes: {list(self.class_mapping.keys())}")
        
        return result_ids
    
    def convert_classes_to_names(self, classes: List[Union[str, int]]) -> List[str]:
        """
        Convert classes parameter to list of names.
        
        Args:
            classes: List of class names or IDs
            
        Returns:
            List of class names
        """
        if not classes:
            return []
            
        result_names = []
        invalid_classes = []
        
        for cls in classes:
            if isinstance(cls, str):
                # Class name - use as is
                if cls in self.class_mapping:
                    result_names.append(cls)
                else:
                    invalid_classes.append(cls)
            elif isinstance(cls, int):
                # Class ID - convert to name
                class_name = self.get_class_name(cls)
                if class_name is not None:
                    result_names.append(class_name)
                else:
                    invalid_classes.append(str(cls))
            else:
                # Invalid type
                invalid_classes.append(str(cls))
        
        if invalid_classes:
            logger.warning(f"Invalid or unknown classes: {invalid_classes}")
            logger.info(f"Available classes: {list(self.class_mapping.keys())}")
        
        return result_names
    
    def get_primary_classes_by_name(self, primary_by_name: List[str]) -> List[int]:
        """Convert primary class names to IDs"""
        return self.convert_classes_to_ids(primary_by_name)
    
    def get_primary_classes_by_id(self, primary_by_id: List[int]) -> List[int]:
        """Return primary class IDs as is"""
        return primary_by_id
    
    def get_all_class_names(self) -> List[str]:
        """Get all available class names"""
        return list(self.class_mapping.keys())
    
    def get_all_class_ids(self) -> List[int]:
        """Get all available class IDs"""
        return list(self.reverse_mapping.keys())
    
    def get_class_mapping(self) -> Dict[str, int]:
        """Get the complete class mapping"""
        return self.class_mapping.copy()
    
    def get_reverse_mapping(self) -> Dict[int, str]:
        """Get the reverse class mapping"""
        return self.reverse_mapping.copy()
    
    def has_conflicts(self) -> bool:
        """Check if there are any conflicts"""
        return len(self.conflicts) > 0
    
    def get_conflicts(self) -> List[str]:
        """Get list of all conflicts"""
        return self.conflicts.copy()
    
    def clear_conflicts(self):
        """Clear all conflicts"""
        self.conflicts.clear()
    
    def get_sources(self) -> List[Dict[str, Any]]:
        """Get information about all sources"""
        return self.sources.copy()
    
    def _get_source_for_class(self, class_name: str) -> str:
        """Get source name for a class name"""
        for source_info in self.sources:
            if class_name in source_info['mapping']:
                return source_info['source']
        return "unknown"
    
    def _get_source_for_id(self, class_id: int) -> str:
        """Get source name for a class ID"""
        for source_info in self.sources:
            if class_id in source_info['mapping'].values():
                return source_info['source']
        return "unknown"
    
    def _get_timestamp(self) -> str:
        """Get current timestamp"""
        import datetime
        return datetime.datetime.now().isoformat()
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of class manager state"""
        return {
            'total_classes': len(self.class_mapping),
            'class_mapping': self.class_mapping,
            'conflicts': self.conflicts,
            'sources': [s['source'] for s in self.sources],
            'has_conflicts': self.has_conflicts()
        }
