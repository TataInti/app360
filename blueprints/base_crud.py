from flask import Blueprint, redirect, render_template, request, url_for
from models import db


class BaseCRUD:
    def __init__(self, blueprint_name, model_class, service_class, template_prefix):
        self.bp = Blueprint(blueprint_name, __name__)
        self.model_class = model_class
        self.service = service_class()
        self.template_prefix = template_prefix
        self._register_routes()

    def _register_routes(self):
        self.bp.add_url_rule('/', view_func=self.list_items, methods=['GET'])
        self.bp.add_url_rule('/new', view_func=self.new_item, methods=['GET', 'POST'])
        self.bp.add_url_rule('/edit/<int:item_id>', view_func=self.edit_item, methods=['GET', 'POST'])

    def list_items(self):
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        items = self.service.repository.get_all(page=page, per_page=per_page)
        if hasattr(items, 'items'):  # Paginated result
            return render_template(f"{self.template_prefix}_list.html", items=items.items, pagination=items)
        return render_template(f"{self.template_prefix}_list.html", items=items)

    def new_item(self):
        if request.method == "POST":
            # Generic form handling - subclasses can override
            kwargs = {key: value for key, value in request.form.items()}
            self.service.create(**kwargs)
            return redirect(url_for(f"{self.bp.name}.list_items"))
        return render_template(f"{self.template_prefix}_form.html")

    def edit_item(self, item_id):
        item = self.service.get_by_id(item_id)
        if not item:
            return "Item not found", 404

        if request.method == "POST":
            kwargs = {key: value for key, value in request.form.items()}
            self.service.update(item_id, **kwargs)
            return redirect(url_for(f"{self.bp.name}.list_items"))

        return render_template(f"{self.template_prefix}_form.html", item=item)