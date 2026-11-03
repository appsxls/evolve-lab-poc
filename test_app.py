"""Lightweight smoke checks; run with python3 test_app.py."""
from pathlib import Path
p=Path(__file__).parent
html=(p/'index.html').read_text()
js=(p/'app.js').read_text()
css=(p/'styles.css').read_text()
assert '<script src="app.js"></script>' in html
assert 'href="styles.css"' in html
assert 'id="tasks"' in html
assert "'/tasks'" in js
assert 'task-row' in css
print('PASS: basic application smoke tests')
