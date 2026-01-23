from models.core import User
from .base_repository import BaseRepository


class UserRepository(BaseRepository):
    def __init__(self):
        super().__init__(User)

    def get_by_username(self, username):
        return self.model_class.query.filter_by(username=username).first()

    def get_active_users(self):
        return self.model_class.query.filter_by(active=True).all()