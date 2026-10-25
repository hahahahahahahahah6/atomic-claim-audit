import os
import tempfile


def save(path, text):
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp:
        temp.write(text)
    os.replace(temp.name, path)
