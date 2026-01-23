from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# Import all models to ensure they are registered
from .core import *
from .crm import *
from .sales import *
from .purchases import *
from .hr import *