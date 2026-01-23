from models import db


class BaseService:
    def __init__(self, repository):
        self.repository = repository

    def get_all(self):
        return self.repository.get_all()

    def get_by_id(self, id):
        return self.repository.get_by_id(id)

    def create(self, **kwargs):
        return self.repository.create(**kwargs)

    def update(self, id, **kwargs):
        return self.repository.update(id, **kwargs)

    def delete(self, id):
        return self.repository.delete(id)