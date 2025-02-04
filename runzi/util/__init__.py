import zipfile
from pathlib import Path, PurePath


def archive(source_path, output_zip):
    '''
    zip contents of source path and return the full archive path.
    handles both single file and a folder
    '''
    with zipfile.ZipFile(output_zip, 'w', compression=zipfile.ZIP_DEFLATED) as zip:
        if Path(source_path).is_file():
            zip.write(source_path, PurePath(source_path).name)
        else:
            for filename in Path(source_path).rglob('*'):
                zip.write(filename, arcname=str(Path(filename).relative_to(source_path)))
    return output_zip
