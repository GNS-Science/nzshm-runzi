#build_rupture_set_index

"""
Simple script to creawte valid URLs to the rupture sets built

only to be used until we have automated rupture reporting

"""

import os
# import os.path
import shutil
import fnmatch
from pathlib import PurePath, Path

import base64
import json
import collections

from nshm_toshi_client.toshi_client_base import ToshiClientBase

class ToshiFile(ToshiClientBase):

    def __init__(self, url, s3_url, auth_token, with_schema_validation=True, headers=None ):
        super(ToshiFile, self).__init__(url, auth_token, with_schema_validation, headers)
        self._s3_url = s3_url


    def get_file_meta_as_dict(self, id):
        qry = '''
        query download_file ($id:ID!) {
                node(id: $id) {
            __typename
            ... on File {
              meta{ k v }
            }
          }
        }'''

        # print(qry)
        input_variables = dict(id=id)
        executed = self.run_query(qry, input_variables)

        retval = dict()
        for kv in executed['node']['meta']:
            retval[kv['k']] = kv['v']
        return retval



API_URL  = os.getenv('NZSHM22_TOSHI_API_URL', "http://127.0.0.1:5000/graphql")
API_KEY = os.getenv('NZSHM22_TOSHI_API_KEY', "")
S3_URL = os.getenv('NZSHM22_TOSHI_S3_URL',"http://localhost:4569")


class IndexBuilder():

    _patterns = ['index.html',]# '*.zip']

    # iso_date = "2021-05-26"
    set_number = '01'
    thinning = "0.0"
    max_inversion_time = 480
    round_number = 1
    index_file = None

    def __init__(self, path, date_path ):
        self._dir_name = path
        self._date_path = date_path


    def old_get_template(self, index_file, short_name, round_number, max_inv_time, thin_factor):
        return  f'''
    <li><a href="{self._date_path}-{self.set_number}/{index_file}">
            Solution ({short_name}) {self._rupture_class}, thin({thin_factor}), {max_inv_time} mins, Round {round_number}</a>
    </li>'''


    def get_template(self, index_file):
        return  f'''<li><a href="{self._date_path}-{self.set_number}{index_file}">{str(index_file)[1:].replace('-', ' ').replace('/index.html', '')}</a></li>'''


    def build_line(self, root, filename):


        # short_name = file_meta['fault_model']
        # round_number = file_meta['round_number']
        # max_inv_time = file_meta['max_inv_time']
        # root = file_meta['root']
        # filename = file_meta['filename']

        index_file = PurePath(root.replace(self._dir_name, ''), filename)

        return self.get_template(index_file)



    def build(self):
        file_meta = dict()
        filekey = None

        # headers={"x-api-key":API_KEY}
        # file_api = ToshiFile(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)

        lines = []
        for root, dirs, files in os.walk(self._dir_name):
            for pattern in self._patterns:
                for filename in fnmatch.filter(files, pattern):

                    # # print(filename, root)

                    # # foldername = root.split('/')[-1]
                    # # filekey, round_number, max_inv_time = foldername.split('-')[1:4]

                    # # print(filekey)
                    # if not filekey in file_meta.keys():
                    #     metadata =  file_api.get_file_meta_as_dict(filekey)
                    #     metakey = f"{metadata['fault_model']}-{metadata['thinning_factor']}-{max_inv_time}-{round_number}"

                    #     #enrich the dict
                    #     metadata['filekey'] = filekey
                    #     metadata['root'] = root
                    #     metadata['filename'] = filename
                    #     metadata['round_number'] = round_number
                    #     metadata['max_inv_time'] = max_inv_time

                    #     file_meta[metakey] = metadata

                    lines. append(self.build_line(root, filename))
        return lines
        # #sort
        # od = collections.OrderedDict(sorted(file_meta.items()))

        # for key, value in od.items():
        #     self.build_line(key, value)



class DownloadBuilder():

    _patterns = ['*.zip',]
    set_number = '01'

    def __init__(self, path, date_path ):
        self._dir_name = path
        self._date_path = date_path

    def get_template(self, solution_file):
        return  f'''<li><a href="{self._date_path}-{self.set_number}/{solution_file}">Download {solution_file}</a></li>'''


    def build_line(self, root, filename):
        index_file = PurePath(root.replace(self._dir_name, ''), filename)
        return self.get_template(index_file)


    def build(self):
        lines = []
        for root, dirs, files in os.walk(self._dir_name):
            for pattern in self._patterns:
                for filename in fnmatch.filter(files, pattern):

                    lines. append(self.build_line(root, filename))
        return lines


class ReportMetaBuilder():
    """
    find the metadata.json and make this available for the HTML
    """
    _patterns = ['metadata.json',]# '*.zip']
    set_number = '01'

    def __init__(self, path, date_path ):
        self._dir_name = path
        self._date_path = date_path

    def build(self):
        file_meta = dict()
        filekey = None

        lines = []
        for root, dirs, files in os.walk(self._dir_name):
            for pattern in self._patterns:
                for filename in fnmatch.filter(files, pattern):
                    folder_path = PurePath(root)
                    if len(folder_path.parts) - len(PurePath(self._dir_name).parts) == 1:
                        #print(root, filename)
                        key = PurePath(root).parts[-1]
                        #print(key)
                        value = json.load(open(PurePath(folder_path, filename), 'r'))
                        #print(value['task_arguments'])
                        '''
                        e.g {'rupture_set_file_id': 'RmlsZTo0ODMuMFN3cTRN', 'generation_task_id': 'UnVwdHVyZUdlbmVyYXRpb25UYXNrOjE4M0FoblN5',
                        'solution_file': '/home/chrisbc/DEV/GNS/opensha-new/nshm-nz-opensha/src/python/automation/tmp/UnVwdHVyZUdlbmVyYXRpb25UYXNrOjE4M0FoblN5/InversionSolution-RmlsZTo2-rnd0-t1380_RmlsZTo0ODMuMFN3cTRN.zip',
                        'short_name': 'CFM_0_9_SANSTVZ_D90-0.1', 'rupture_class': 'Azimuth', 'max_inversion_time': '1380', 'completion_energy': '0.05', 'round_number': '0'}
                        '''

                        solution_name = PurePath( value['task_arguments']['solution_file']).name
                        #print(solution_name)
                        solution_filepath = Path(folder_path, '..', value['task_arguments']['generation_task_id'], solution_name).resolve()
                        #print(solution_filepath)
                        #rel_path = os.path.relpath(solution_filepath, start = PurePath(self._dir_name))
                        info = dict(
                            key = key,
                            meta = value['task_arguments'],
                            solution_relative_path = os.path.relpath(solution_filepath, start = PurePath(self._dir_name)),
                            index_path = os.path.relpath(PurePath(folder_path, "DiagnosticsReport", "index.html"), start = PurePath(self._dir_name)),
                            )

                        #TODO: ugly workaround, FIXME
                        rupture_class = "Azimuth"
                        azim_len = len("UnVwdHVyZUdlbmVyYXRpb25UYXNrOjE4NXN4Zjhp/InversionSolution-RmlsZTo2-rnd0-t1380_RmlsZTo1MDcuMDdaMkFp.zip")
                        if len(info['solution_relative_path']) > azim_len:
                            rupture_class = "Coulomb"
                        info['meta']['rupture_class'] = rupture_class

                        lines.append(info)
        return lines


    def get_template(self, info, mfd_dirs):
        """
        {'key': 'RmlsZTo0NTkuMDlnaEda', 'meta': {'rupture_set_file_id': 'RmlsZTo0NTkuMDlnaEda',
        'generation_task_id': 'UnVwdHVyZUdlbmVyYXRpb25UYXNrOjE4MUNqSFFa',
        'short_name': 'CFM_0_9_SANSTVZ_D90-0.1', 'rupture_class': 'Azimuth', 'max_inversion_time': '1380', 'completion_energy': '0.2', 'round_number': '0'},
        'solution_relative_path': 'UnVwdHVyZUdlbmVyYXRpb25UYXNrOjE4MUNqSFFa/InversionSolution-RmlsZTo2-rnd0-t1380_RmlsZTo0NTkuMDlnaEda.zip',
        'index_path': 'RmlsZTo0NTkuMDlnaEda/DiagnosticsReport/index.html'}

        """
        m = info['meta']
        report_info  = f"{m['short_name']} {m['rupture_class']} energy({m['completion_energy']}) round({m['round_number']})"

        if m['rupture_set_file_id'] in mfd_dirs:
            extra_link = f'&nbsp;<a href="{self._date_path}-{self.set_number}/{m["rupture_set_file_id"]}/named_fault_mfds/mfd_index.html" >Named MFDS</a>'
        else:
            extra_link = ''

        return  f'''<li>{report_info}&nbsp;
    <a href="{self._date_path}-{self.set_number}/{info['index_path']}" >Diagnostics report</a>&nbsp;
    <a href="{self._date_path}-{self.set_number}/{info['solution_relative_path']}" >Download solution file</a>
    {extra_link}</li>'''




if __name__ == "__main__":

    #rupture_class = "Azimuth" #"Coulomb"

    # report_builder = IndexBuilder(
    #     # path = '/home/chrisbc/DEV/GNS/opensha-new/DATA/2021-05-26-01',
    #     path = './tmp',

    #     date_path = "2021-05-26")

    # for line in sorted(report_builder.build()):
    #     print(line)

    # downloads = DownloadBuilder(
    #     path = '/home/chrisbc/DEV/GNS/opensha-new/DATA/2021-05-26-01',
    #     date_path = "2021-05-26")

    # for line in sorted(downloads.build()):
    #     print(line)


    mfd_dirs = [
    "RmlsZTo1MjIuMDN2ZktR",
    "RmlsZTo1MTAuMDlDVUsy",
    "RmlsZTo0OTguMEtiUnJE",
    "RmlsZTo0ODYuMDI4N2dr",
    "RmlsZTo0NzQuMG1CdVhq",
    "RmlsZTo0NjguMEczcFVT",
    "RmlsZTo1MTkuMG9XR0dF",
    "RmlsZTo1MDcuMDdaMkFp",
    "RmlsZTo0OTUuMFVLcm5B",
    "RmlsZTo0ODMuMFN3cTRN",
    "RmlsZTo0NzEuMFpqckZx",
    "RmlsZTo0NTkuMDlnaEda"]



    #ReportMetaBuilder
    meta_builder = ReportMetaBuilder(
        path = '/home/chrisbc/DEV/GNS/opensha-new/DATA/2021-06-01-01',
        date_path = "2021-06-01")

    def sort_fn(info):
        key = info['meta']['short_name']
        key += info['meta']['rupture_class']
        key += info['meta']['completion_energy']
        return key


    for line in sorted(meta_builder.build(), key=sort_fn):
        line['meta'].pop('solution_file') #to verbose
        print(meta_builder.get_template(line, mfd_dirs))


    # for line in sorted(report_builder.build()):
    #     print(line)