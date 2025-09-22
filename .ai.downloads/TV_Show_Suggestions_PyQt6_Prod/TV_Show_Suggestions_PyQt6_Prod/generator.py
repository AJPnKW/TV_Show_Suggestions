import os
from typing import List, Dict
from jinja2 import Environment, FileSystemLoader, select_autoescape

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
TEMPLATES_DIR = os.path.join(PROJECT_ROOT, "templates")
OUTPUTS_DIR = os.path.join(PROJECT_ROOT, "outputs")
os.makedirs(OUTPUTS_DIR, exist_ok=True)

def generate_html(shows: List[Dict], outfile: str, theme: Dict=None) -> str:
    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(["html","xml"])
    )
    tpl = env.get_template("page.html.j2")
    html = tpl.render(shows=shows, theme=theme or {})
    with open(outfile, "w", encoding="utf-8") as f:
        f.write(html)
    return outfile
