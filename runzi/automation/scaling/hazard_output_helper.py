from distutils.util import execute
import os
import requests
from pathlib import Path, PurePath

#TODO convert return to yield?

class HazardOutputHelper():

    def __init__(self,toshi_api):
        self.api = toshi_api

    def download_hdf(self, hazard_soln_ids, dest_folder, overwrite=False):
        
        downloads = dict()
 
        for hazard_soln_id in hazard_soln_ids:

            file_info = self.get_archive_info(hazard_soln_id,'hdf5')

            folder = Path(dest_folder, 'downloads', hazard_soln_id)
            folder.mkdir(parents=True, exist_ok=True)
            file_path = PurePath(folder, file_info['file_name'])

            downloads[file_info['id']] = dict(id=file_info['id'],
                                                filepath = str(file_path),
                                                info = file_info,
                                                hazard_id = hazard_soln_id)

            if not overwrite and os.path.isfile(file_path):
                print(f"Skip DL for existing file: {file_path}")
                continue

            r1 = requests.get(file_info['file_url'])
            with open(str(file_path), 'wb') as f:
                f.write(r1.content)
                print("downloaded input file:", file_path, f)
                os.path.getsize(file_path) == file_info['file_size']

        return downloads



    def download_csv(self, hazard_soln_ids, dest_folder, overwrite=False):
    
        downloads = dict()
 
        for hazard_soln_id in hazard_soln_ids:

            file_info = self.get_archive_info(hazard_soln_id,'csv')

            folder = Path(dest_folder, 'downloads', hazard_soln_id)
            folder.mkdir(parents=True, exist_ok=True)
            file_path = PurePath(folder, file_info['file_name'])

            downloads[file_info['id']] = dict(id=file_info['id'],
                                                filepath = str(file_path),
                                                info = file_info,
                                                hazard_id = hazard_soln_id)

            if not overwrite and os.path.isfile(file_path):
                print(f"Skip DL for existing file: {file_path}")
                continue

            r1 = requests.get(file_info['file_url'])
            with open(str(file_path), 'wb') as f:
                f.write(r1.content)
                print("downloaded input file:", file_path, f)
                os.path.getsize(file_path) == file_info['file_size']

        return downloads

    
    def get_archive_info(self, hazard_soln_id, archive_type):
        """
        archive_type: str {'csv','hdf5'}
        """
       
        qry = '''
        query oqhazsoln ($id:ID!) {  
            node (id: $id) {
		    ... on OpenquakeHazardSolution {
                    ###archive_type###_archive {
                    id
                    file_name
                    file_size
                    file_url
                    }
                }
            }
        }'''
        qry = qry.replace('###archive_type###',archive_type)
        input_variables = dict(id=hazard_soln_id)
        executed = self.api.run_query(qry, input_variables)
              
        archive_info =  executed['node'][f'{archive_type}_archive']

        return archive_info


    def get_hazard_ids_from_gt(self,gt_id):

        qry = '''
        query oqhaztask ($id:ID!) {
            node (id: $id) {
         	... on OpenquakeHazardTask {
                hazard_solution {
                id
                }
              }
            }
        }'''
        
        api_result = self.api.get_general_task_subtasks(gt_id)
        edges = api_result['children']['edges']

        hazard_solns = {}
        for edge in edges:
            subtask_id = edge['node']['child']['id']
            
            args = {}
            for kv in edge['node']['child']['arguments']:
                args.update(dict([tuple(kv.values()),]))

            input_variables = dict(id=subtask_id)
            executed = self.api.run_query(qry, input_variables)
            if executed['node']['hazard_solution']:
                hazard_solns[(executed['node']['hazard_solution']['id'])] = args
        
        return hazard_solns
        

       

    
        