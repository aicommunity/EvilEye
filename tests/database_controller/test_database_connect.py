import os
from evileye.core.logging_config import setup_evileye_logging
from evileye.core.logger import get_module_logger
import sys

#sys.path.append(str(Path(__file__).parent.parent.parent))
from database_controller import DatabaseControllerPg


if __name__ == '__main__':
    db = DatabaseControllerPg()

    db.init()
    db.default()

    db.connect()