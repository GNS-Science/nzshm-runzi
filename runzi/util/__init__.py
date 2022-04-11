
import os
import zipfile
from pathlib import PurePath

def archive(source_path, output_zip):
    '''
    zip contents of source path and return the full archive path.
    handles both single file and a folder
    '''
    zip = zipfile.ZipFile(output_zip, 'w', compression=zipfile.ZIP_DEFLATED)
    if os.path.isfile(source_path):
        zip.write(source_path, PurePath(source_path).name )
    else:
        for root, dirs, files in os.walk(source_path):
            for file in files:
                filename = str(PurePath(root, file))
                arcname = filename.replace(str(source_path), '')
                zip.write(filename, arcname )
    return output_zip

