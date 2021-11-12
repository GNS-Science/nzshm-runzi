#!python3
"""
helpers for upstream file retrieval

"""
import re
import os
import requests
from pathlib import Path, PurePath

def get_output_file_ids(general_task_api, upstream_task_id, file_extension='zip'):

    api_result = general_task_api.get_subtask_files(upstream_task_id)
    for subtask in api_result['children']['edges']:

        #get rupture set fault model
        fault_model = ""
        for filenode in subtask['node']['child']['files']['edges']:
            print("FN:", filenode)
            if filenode['node']['role'] == 'READ' and filenode['node']['file']['file_name'][-3:] == file_extension:
                for kv in filenode['node']['file'].get('meta', []):
                    if kv.get('k') == 'fault_model':
                        fault_model = kv.get('v')
                        break

        for filenode in subtask['node']['child']['files']['edges']:
            #skip task inputs
            if filenode['node']['role'] == 'READ':
                continue
            if filenode['node']['file']['file_name'][-3:] == file_extension:
                # inversion_meta = dict() ## this relies on order of
                # for kv in filenode['node']['file']['meta']:
                #     inversion_meta[kv['k']] = kv['v']
                res = dict(id = filenode['node']['file']['id'],
                        file_name = filenode['node']['file']['file_name'],
                        file_size = filenode['node']['file']['file_size']
                        )

                if fault_model:
                    res['fault_model'] = fault_model
                yield res
                #TESTING
                #return

def get_output_file_id(file_api, single_file_id):

    api_result = file_api.get_file_detail(single_file_id)
    fault_model = ""
    print("FN:", api_result)
    if api_result['file_name'][-3:] == "zip":
        res = dict(id = api_result['id'],
                file_name = api_result['file_name'],
                file_size = api_result['file_size'],
                fault_model = re.search(r"\((.*?)\)", api_result['meta'][3]['v']).group(0)[1:-1]
                )
        for kv in api_result['meta']:
            if kv.get('k') == 'fault_model':
                fault_model = kv.get('v')

        if fault_model:
            res['fault_model'] = fault_model
        yield res #yep yield one

    return


def get_download_info(file_api, file_infos):
    """
    [{'id': 'RmlsZToyOS4wRUVjV0E=',
    'file_name': 'RupSet_Cl_FM(CFM_0_3_SANSTVZ)_noInP(T)_slRtP(0.05)_slInL(F)_cfFr(0.75)_cfRN(2)_cfRTh(0.5)_cfRP(0.01)_fvJm(T)_jmPTh(0.001)_cmRkTh(360)_mxJmD(15)_plCn(T)_adMnD(6)_adScFr(0)_bi(F)_stGrSp(2)_coFr(0.5).zip',
    'file_size': 2498443,
    'short_name': None}]
    """
    file_info = {}
    for itm in file_infos:
        api_result = file_api.get_file_download_url(itm['id'])
        # print(api_result)
        yield dict(dict(file_url=api_result['file_url']), **itm) #merge the discts


def download_files(file_api, file_generator, dest_folder, id_suffix=False, overwrite=False, skip_existing=False):
    """
    file_generator = get_output_file_ids(general_api, upstream_task_id) # for files by upstream task ID)

    or

    file_generator = get_output_file_id(file_api, file_id) #for file by file ID
    """
    downloads = dict()

    for info in get_download_info(file_api, file_generator):

        folder = Path(dest_folder, 'downloads', info['id'])
        folder.mkdir(parents=True, exist_ok=True)

        #we can skip if file exists and has correct file_size
        file_path = PurePath(folder, info['file_name'])

        if id_suffix:
            file_path = str(file_path).replace('.zip', f"_{info['id']}.zip")

        #shortname = info['short_name'] or info['id']
        if skip_existing and os.path.isfile(file_path):
            print(f"Don't reprocess existing file: {file_path}")
            continue

        downloads[info['id']] = dict(id=info['id'], filepath = str(file_path), info = info)

        if not overwrite and os.path.isfile(file_path):
            print(f"Skip DL for existing file: {file_path}")
            continue

        # here we pull the file
        # print(info['file_url'])
        # r0 = requests.head(info['file_url'])
        r1 = requests.get(info['file_url'])
        with open(str(file_path), 'wb') as f:
            f.write(r1.content)
            print("downloaded input file:", file_path, f)
            os.path.getsize(file_path) == info['file_size']

    return downloads
