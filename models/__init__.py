from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# Import all models to ensure they are registered
from .core import *
from .crm import *
from .sales import *
from .purchases import *
from .hr import *
from .comercial import *
from .gastos import *
from .tesoreria import *
from .rrhh import *
from .sabiogo import *