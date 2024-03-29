import sys
import toml

with open('pyproject.toml', encoding='utf-8') as toml_file:
  value = toml.load(toml_file)['tool']['poetry'][sys.argv[1]]

if isinstance(value, list):
  value = ', '.join(value)

print(value)
