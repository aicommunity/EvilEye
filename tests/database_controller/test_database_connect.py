import os
import sys

#sys.path.append(str(Path(__file__).parent.parent.parent))
from database_controller import DatabaseControllerPg


if __name__ == '__main__':
    db = DatabaseControllerPg()

    db.init()
    db.default()

    db.connect()