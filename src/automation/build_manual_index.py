#build_rupture_set_index

"""
Simple script to create valid URLs
only to be used until we have automated rupture reporting

"""

import os
# import os.path
import shutil
import fnmatch
from pathlib import PurePath, Path
from datetime import datetime as dt
import pytz

import base64
import json
import collections

from scaling.toshi_api import ToshiApi

class GeneralTaskBuilder():
    """
    find the metadata.json and make this available for the HTML
    """
    def __init__(self, path, date_path ):
        self._dir_name = path
        self._date_path = date_path


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

API_URL  = os.getenv('NZSHM22_TOSHI_API_URL', "http://127.0.0.1:5000/graphql")
API_KEY = os.getenv('NZSHM22_TOSHI_API_KEY', "")
S3_URL = os.getenv('NZSHM22_TOSHI_S3_URL',"http://localhost:4569")

def gt_template(node):
    title = node.get('title')
    description = node.get('description')

    NZ_timezone = pytz.timezone('NZ')
    created = dt.strptime(node.get('created'), "%Y-%m-%dT%H:%M:%S.%f%z").astimezone(NZ_timezone)

    return f"""
    <h2>{title}</h2>
    <p>{created.strftime("%Y-%m-%d %H:%M:%S %z")}</p>
    <a href="{TUI}GeneralTask/{GID}">{GID}</a>
    <p>{description}</p>
    """

def get_file_meta(file_node, display_keys = []):
    display_info = ""
    for kv_pair in file_node['meta']:
        if kv_pair['k'] in display_keys:
            if kv_pair['k'] == 'rupture_set_file_id':
                info = f"<a href ='{TUI}FileDetail/{kv_pair['v']}'>{kv_pair['v']}</a>"
            else:
                info = kv_pair['v']
            display_info += f"{kv_pair['k']}:{info}, "

    display_info = display_info[:-2]
    return display_info


def rgt_template(rgt, display_keys=None):
    """'id': 'UnVwdHVyZUdlbmVyYXRpb25UYXNrOjE4ODNXcnFN', 'created': '2021-06-10T10:23:23.457361+00:00', 'state': 'DONE', 'result': 'SUCCESS',"""
    rid = rgt['id']
    result = rgt['result']
    fname = None
    display_keys = display_keys or []
    display_info = ""
    # return f'<li><a href="{TUI}RuptureGenerationTask/{rid}">Rupture set {rid}</a>result: {result}</li>'
    for file_node in rgt['files']['edges']:
        fn = file_node['node']
        if fn['role'] == 'WRITE' and 'zip' in fn['file']['file_name']:
            fname = fn['file']['file_name']
            fid = fn['file']['id']
            display_info = get_file_meta(fn['file'], display_keys)
            break

    if fname:
        return f'''<li>
            <a href="{TUI}RuptureGenerationTask/{rid}">{rid}</a> result: {result} &nbsp;
            <a href="{TUI}FileDetail/{fid}">File detail</a> &nbsp;
            <a href="{UPLOAD_FOLDER}/{fid}/DiagnosticsReport/index.html">Diagnostics report</a>
            <br />
            <div class="display_info">{display_info}</div>
            <br />
        </li>
        '''
    else:
       return f'''<li>
            <a href="{TUI}RuptureGenerationTask/{rid}">{rid}</a> result: {result}
        </li>
        '''


def inv_template(rgt, display_keys=None):

    rid = rgt['id']
    result = rgt['result']
    fname = None
    fault_model = ""
    display_info = ""
    display_keys = display_keys or []
    # return f'<li><a href="{TUI}RuptureGenerationTask/{rid}">Rupture set {rid}</a>result: {result}</li>'
    if not rgt.get('files'):
        return ''

    for file_node in rgt['files']['edges']:
        fn = file_node['node']
        #get solution details
        if fn['role'] == 'WRITE' and 'zip' in fn['file']['file_name']:
            fname = fn['file']['file_name']
            fid = fn['file']['id']
            display_info = get_file_meta(fn['file'], display_keys)

        #extract mmode from the rupture set
        if fn['role'] == 'READ' and 'zip' in fn['file']['file_name']:
            for kv_pair in fn['file']['meta']:
                if kv_pair['k'] == 'fault_model':
                    fault_model = kv_pair['v']
                    break

    if fname:
        named_faults_link = ''
        #only link named_faults if they're there
        if Path(f'{WORK_FOLDER}/{UPLOAD_FOLDER}/{fid}/named_fault_mfds/mfd_index.html').exists():
            named_faults_link = f'<a href="{UPLOAD_FOLDER}/{fid}/named_fault_mfds/mfd_index.html">Named fault MFDs</a>'
        return f'''<li>
            <a href="{TUI}RuptureGenerationTask/{rid}">{rid}</a> result: {result} &nbsp;
            <a href="{TUI}InversionSolution/{fid}">Inversion Solution detail</a> &nbsp;
            <a href="{UPLOAD_FOLDER}/{fid}/mag_rates/MAG_rates_log_fixed_yscale.png">Mag Rate overall</a>
            {named_faults_link}
            <br />
            <div class="display_info">{display_info}</div>
            <br />

        </li>
        '''
    else:
       return f'''<li>
            <a href="{TUI}RuptureGenerationTask/{rid}">{rid}</a> result: {result}
        </li>
        '''

if __name__ == "__main__":

    #rupture_class = "Azimuth" #"Coulomb"

    headers={"x-api-key":API_KEY}
    general_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)

    GID = "R2VuZXJhbFRhc2s6MTg2NkdyZDRY="
    GID = "R2VuZXJhbFRhc2s6MTk0NTJNS2dN"
    GID = "R2VuZXJhbFRhc2s6MjAwNU1veHM5"
    GID = "R2VuZXJhbFRhc2s6NzA4Q3RieTg=" #TEST API example
    GID = "R2VuZXJhbFRhc2s6NzIybjVvc0I=" #TEST RUPT SET
    GID = "R2VuZXJhbFRhc2s6NzI2ejQ4SlQ=" #TEST INVERSION

    UPLOAD_FOLDER = "DATA25"

    TUI = "http://simple-toshi-ui.s3-website-ap-southeast-2.amazonaws.com/"
    WORK_FOLDER = "/home/chrisbc/DEV/GNS/opensha-new/AWS_S3_DATA"

    gentask = general_api.get_general_task_subtask_files(GID)
    # print(gentask)
    node = gentask

    info_keys = ['mfd_equality_weight',
         'mfd_inequality_weight',
         'slip_rate_normalized_weight',
         'slip_rate_unnormalized_weight' ] # 'round', 'max_inversion_time', 'mfd_transition_mag',
    #info_keys = ['fault_model', 'min_fill_ratio',] #'growth_size_epsilon'] # for ruptget on subduction
    #info_keys = ['round',]
    info_keys = ['mfd_equality_weight', 'mfd_inequality_weight','slip_rate_unnormalized_weight' ] # 'round', 'max_inversion_time'
    #info_keys = ['min_fill_ratio', 'growth_size_epsilon'] # for ruptget on subduction
    info_keys = ['round', 'mfd_mag_gt_5',] #] 'mfd_b_value']
    #info_keys = []

    #Write Section info
    print(gt_template(node))
    print("<ul>")

    for child_node in node['children']['edges']:
        rgt = child_node['node']['child']

        #print(rgt_template(rgt, info_keys))  #rupt sets
        print(inv_template(rgt, info_keys)) #inversions

    print("</ul>")
    print("<hr />")
