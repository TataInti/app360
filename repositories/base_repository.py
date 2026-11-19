from sqlalchemy import inspect as sa_inspect

from models import db

# Campos que nunca se asignan desde datos externos, aunque una lista blanca los nombre.
CAMPOS_NUNCA_ASIGNABLES = frozenset({"id", "created_at", "updated_at"})


class BaseRepository:
    # Lista blanca de campos que create() y update() aceptan de datos externos
    # (formularios o payloads). Cada repositorio que los recibe debe declararla.
    ALLOWED_FIELDS = None

    def __init__(self, model_class):
        self.model_class = model_class

    def filtrar_campos(self, datos):
        """Devuelve solo los campos asignables. Los desconocidos se descartan sin error.

        Nunca devuelve id, created_at, updated_at ni relaciones del modelo.
        """
        if self.ALLOWED_FIELDS is None:
            raise NotImplementedError(f"{type(self).__name__} debe declarar ALLOWED_FIELDS")
        relaciones = set(sa_inspect(self.model_class).relationships.keys())
        permitidos = set(self.ALLOWED_FIELDS) - CAMPOS_NUNCA_ASIGNABLES - relaciones
        return {clave: valor for clave, valor in datos.items() if clave in permitidos}

    def get_all(self, page=None, per_page=None):
        query = self.model_class.query
        if page and per_page:
            return query.paginate(page=page, per_page=per_page, error_out=False)
        return query.all()

    def get_by_id(self, id):
        return self.model_class.query.get(id)

    def create(self, **kwargs):
        instance = self.model_class(**self.filtrar_campos(kwargs))
        db.session.add(instance)
        db.session.commit()
        return instance

    def update(self, registro_id, /, **kwargs):
        # Parámetro posicional-only: un campo 'id' de un formulario no debe chocar con él.
        campos = self.filtrar_campos(kwargs)
        instance = self.get_by_id(registro_id)
        if instance:
            for key, value in campos.items():
                setattr(instance, key, value)
            db.session.commit()
        return instance

    def delete(self, id):
        instance = self.get_by_id(id)
        if instance:
            db.session.delete(instance)
            db.session.commit()
        return instance
