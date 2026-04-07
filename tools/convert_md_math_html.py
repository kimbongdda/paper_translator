import pathlib, markdown
p = pathlib.Path('Throughput Analysis and User Barring Design for Up 328b505ddbeb805295adf7d677d3552b.md')
text = p.read_text(encoding='utf-8')
html = markdown.markdown(
    text,
    extensions=['fenced_code', 'tables', 'pymdownx.arithmatex'],
    extension_configs={
        'pymdownx.arithmatex': {
            'generic': True,
            'preview': True,
        }
    }
)
out = pathlib.Path('Throughput Analysis and User Barring Design for Up 328b505ddbeb805295adf7d677d3552b.html')
out.write_text('<!doctype html>\n<html><head><meta charset="utf-8"><title>Throughput Analysis</title>\n<script type="text/javascript" id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>\n</head><body>\n' + html + '\n</body></html>', encoding='utf-8')
print('HTML 생성 완료:', out.resolve())
