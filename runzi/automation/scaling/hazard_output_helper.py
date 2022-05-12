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
            file_info = self.get_hdf_info(hazard_soln_id)

            folder = Path(dest_folder, 'downloads', hazard_soln_id)
            folder.mkdir(parents=True, exist_ok=True)
            file_path = PurePath(folder, file_info['file_name'])

            downloads[file_info['id']] = dict(id=file_info['id'],
                                                filepath = str(file_path),
                                                info = file_info,
                                                hazard_id = hazard_soln_id)

            if not overwrite and os.path.isfile(file_path):
                print(f"Skip DL for existing file: {file_path}")
                return downloads

            r1 = requests.get(file_info['file_url'])
            with open(str(file_path), 'wb') as f:
                f.write(r1.content)
                print("downloaded input file:", file_path, f)
                os.path.getsize(file_path) == file_info['file_size']

        return downloads


    def download_csv(self, hazard_soln_id, dest_folder, skip_existing=False):

        #TODO this does nothing

        downloads = dict()
        

        return downloads


    def get_hdf_info(self,hazard_soln_id):
       
        qry = '''
        query oqhazsoln ($id:ID!) {  
            node (id: $id) {
		    ... on OpenquakeHazardSolution {
                    hdf5_archive {
                    id
                    file_name
                    file_size
                    file_url
                    }
                }
            }
        }'''
        input_variables = dict(id=hazard_soln_id)
        executed = self.api.run_query(qry, input_variables)
              
        hdf_info =  executed['node']['hdf5_archive']

        return hdf_info


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

        hazard_soln_ids = []
        for edge in edges:
            subtask_id = edge['node']['child']['id']
            input_variables = dict(id=subtask_id)
            executed = self.api.run_query(qry, input_variables)
            if executed['node']['hazard_solution']:
                hazard_soln_ids.append(executed['node']['hazard_solution']['id'])
        
        return hazard_soln_ids        
        

       

    
        