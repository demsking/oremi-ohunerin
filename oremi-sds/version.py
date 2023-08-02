import toml

with open('pyproject.toml') as f:
  __version__ = toml.load(f)['tool']['poetry']['version']


__all__ = [
  '__version__',
]

del toml
