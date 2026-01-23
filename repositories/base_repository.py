from models import db


class BaseRepository:
    def __init__(self, model_class):
        self.model_class = model_class

    def get_all(self, page=None, per_page=None):
        query = self.model_class.query
        if page and per_page:
            return query.paginate(page=page, per_page=per_page, error_out=False)
        return query.all()

    def get_by_id(self, id):
        return self.model_class.query.get(id)

    def create(self, **kwargs):
        instance = self.model_class(**kwargs)
        db.session.add(instance)
        db.session.commit()
        return instance

    def update(self, id, **kwargs):
        instance = self.get_by_id(id)
        if instance:
            for key, value in kwargs.items():
                setattr(instance, key, value)
            db.session.commit()
        return instance

    def delete(self, id):
        instance = self.get_by_id(id)
        if instance:
            db.session.delete(instance)
            db.session.commit()
        return instance