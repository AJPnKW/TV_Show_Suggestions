# scripts/generator.py
import os
from jinja2 import Environment, FileSystemLoader, select_autoescape

SCRIPT_DIR   = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, os.pardir))
TEMPLATES_DIR= os.path.join(PROJECT_ROOT, "templates")
OUTPUTS_DIR  = os.path.join(PROJECT_ROOT, "outputs")
os.makedirs(OUTPUTS_DIR, exist_ok=True)

_env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(["html", "xml"])
)

def generate_html(shows, outfile, theme):
    tpl = _env.get_template("page.html.j2")
    html = tpl.render(shows=shows, theme=theme)
    os.makedirs(os.path.dirname(outfile), exist_ok=True)
    with open(outfile, "w", encoding="utf-8") as f:
        f.write(html)

