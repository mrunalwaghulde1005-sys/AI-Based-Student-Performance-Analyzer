from app import app
print([rule.endpoint for rule in app.url_map.iter_rules()])
