from pathlib import Path
import shutil


def save(path, source):
    Path(path).write_text('data')
    with open(path, 'w') as stream:
        stream.write('data')
    shutil.copy2(source, path)
