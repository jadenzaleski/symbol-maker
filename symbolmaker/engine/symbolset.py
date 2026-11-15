"""What an Xcode asset catalog needs around a symbol: a name that is safe to use as a file name, and Contents.json.

A custom symbol is a folder `<name>.symbolset/` holding `<name>.svg` (the template) and `Contents.json`.
"""
import json
import re

INFO = {'author': 'xcode', 'version': 1}
_VALID = re.compile(r'^[A-Za-z0-9._-]+$')


def validate_name(name):
    """Error message, or None when the name is a usable symbol name."""
    if not name or not name.strip():
        return 'Give the symbol a name.'
    if len(name) > 100:
        return 'The name is too long (100 characters at most).'
    if not _VALID.fullmatch(name):
        return 'Use only letters, digits, dots, hyphens and underscores (no spaces or slashes).'
    if name.startswith('.') or name.endswith('.') or '..' in name:
        return 'The name cannot start or end with a dot or contain "..".'
    return None


def contents_json(name):
    """The Contents.json text for `<name>.symbolset/`. Raises ValueError for an unusable name."""
    err = validate_name(name)
    if err:
        raise ValueError(err)
    return json.dumps({'info': INFO, 'symbols': [{'filename': f'{name}.svg', 'idiom': 'universal'}]}, indent=2)
