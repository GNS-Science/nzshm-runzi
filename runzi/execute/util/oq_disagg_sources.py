import logging
from pathlib import Path
from runzi.automation.scaling.local_config import WORK_PATH
from oq_build_sources import SourceModelLoader, build_disagg_sources_xml

log = logging.getLogger(__name__)

loglevel = logging.INFO
# logging.getLogger('py4j.java_gateway').setLevel(loglevel)
# logging.getLogger('nshm_toshi_client.toshi_client_base').setLevel(loglevel)
# logging.getLogger('nshm_toshi_client.toshi_file').setLevel(loglevel)
# logging.getLogger('urllib3').setLevel(loglevel)
# logging.getLogger('botocore').setLevel(loglevel)
# logging.getLogger('git.cmd').setLevel(loglevel)
logging.getLogger('gql.transport').setLevel(logging.WARN)


dissag_config = dict(
  vs30 = 400,
  # _source_ids = [
  #     'SW52ZXJzaW9uU29sdXRpb25Ocm1sOjExMDk5Mg',
  #     'RmlsZToxMTEyMjQ','SW52ZXJzaW9uU29sdXRpb25Ocm1sOjExMTA2Mw==',
  #     'RmlsZToxMTEyMTM=','SW52ZXJzaW9uU29sdXRpb25Ocm1sOjExMTEzNQ==',
  #     'RmlsZToxMTE5MTM=',
  #     'RmlsZToxMTEyMzk='],
  source_ids = ["SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwODA3NQ==", 'RmlsZToxMDY1MjU=', 'SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwODI3MA==', 'RmlsZToxMDY1NDg=', 'SW52ZXJzaW9uU29sdXRpb25Ocm1sOjEwODMzNw==', 'RmlsZToxMDY1NDc='],
  imt = 'PGA',
  level = '0.954',
  location = '-36.870~174.770',
  gsims = {
      'Active Shallow Crust':'Stafford2022_Central',
      'Subduction Interface':'Atkiinson2022Crust_Upper',
      'Subduction Intraslab':'AbrahamsonEtAl2014'
  }
)


if __name__ == "__main__":

    logging.basicConfig(level=logging.INFO)
    sources_folder = Path(WORK_PATH, 'sources')
    source_file_mapping = SourceModelLoader().unpack_sources_in_list(dissag_config['source_ids'], sources_folder)

    flattened_files = []
    for key, val in source_file_mapping.items():
    	flattened_files += val['sources']

    source_xml = build_disagg_sources_xml(flattened_files)
    with open("source_model.xml", 'w') as f:
        f.write(source_xml)

    print('Done!')