from pathlib import Path

import pytest
from flask import Flask, render_template_string
from markupsafe import Markup


ROOT = Path(__file__).resolve().parents[1]
MACRO_IMPORT = "{% from '_components.html' import form_field, form_grid, status, page_head %}"


@pytest.fixture
def render_component():
    app = Flask(__name__, template_folder=str(ROOT / "templates"))

    def render(source, **context):
        with app.app_context():
            return render_template_string(f"{MACRO_IMPORT}\n{source}", **context)

    return render


def test_form_field_escapes_label_help_and_error_and_shows_unit(render_component):
    injection = '<script>alert("x")</script>'
    html = render_component(
        "{{ form_field(label, 'importe', unidad='ARS', ayuda=help, error=error) }}",
        label=injection,
        help=injection,
        error=injection,
    )

    assert 'class="app-field"' in html
    assert 'class="app-input-unit"' in html
    assert 'class="app-input-unit__text">ARS</span>' in html
    assert 'name="importe"' in html and 'id="importe"' in html
    assert html.count("&lt;script&gt;") == 3
    assert "<script>" not in html
    assert 'class="app-field__help"' in html
    assert 'class="app-field__error" role="alert"' in html


def test_form_field_renders_trusted_control_markup(render_component):
    control = Markup('<input class="app-input" id="correo" name="correo" type="email">')
    html = render_component("{{ form_field('Correo', control) }}", control=control)

    assert control in html
    assert 'for="correo"' not in html
    assert 'class="app-field__label">Correo</label>' in html


def test_form_grid_renders_caller_and_column_variant(render_component):
    html = render_component(
        "{% call form_grid(3) %}<div class=\"app-field\">Campo</div>{% endcall %}"
    )

    assert 'class="app-form-grid app-form-grid--3"' in html
    assert 'data-columns="3"' in html
    assert '<div class="app-field">Campo</div>' in html


def test_status_macro_maps_known_and_unknown_states_and_escapes_text(render_component):
    states = {
        "Cumplido": "ok",
        "Por debajo del ritmo esperado": "warn",
        "Sin meta": "neutral",
        "Activo": "ok",
        "Inactivo": "neutral",
        "Pendiente": "warn",
        "Anulado": "neutral",
        "Pend. anulación": "warn",
        "Aprobado": "ok",
        "Pagado": "ok",
        "Liquidado": "neutral",
        "Falta": "error",
        "Justificado": "neutral",
    }
    for state, tone in states.items():
        html = render_component("{{ status(state) }}", state=state)
        assert f'class="app-status app-status--{tone}"' in html
        assert 'class="app-status__dot" aria-hidden="true"' in html
        assert f'class="app-status__text">{state}</span>' in html

    hostile = '<script>alert("x")</script>'
    html = render_component("{{ status(state) }}", state=hostile)
    assert 'class="app-status app-status--neutral"' in html
    assert "&lt;script&gt;" in html
    assert "<script>" not in html


def test_page_head_renders_actions_and_escapes_title_and_subtitle(render_component):
    injection = '<script>alert("x")</script>'
    html = render_component(
        "{% call page_head(title, subtitle) %}<button class=\"app-action\">Guardar</button>{% endcall %}",
        title=injection,
        subtitle=injection,
    )

    assert 'class="app-page-head"' in html
    assert 'class="app-page-head__title">&lt;script&gt;' in html
    assert 'class="app-page-head__subtitle">&lt;script&gt;' in html
    assert 'class="app-page-head__actions"><button class="app-action">Guardar</button>' in html
    assert "<script>" not in html
