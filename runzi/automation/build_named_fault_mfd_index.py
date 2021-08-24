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
from copy import copy
# Set up your local config, from environment variables, with some sone defaults
from scaling.local_config import WORK_PATH

TUI = "http://simple-toshi-ui.s3-website-ap-southeast-2.amazonaws.com/"

class NamedFaultIndexBuilder():
    """
    find the metadata.json and make this available for the HTML
    """
    _patterns = ['metadata.json',]
    set_number = '02'

    def __init__(self, path ):
        self._dir_name = path

    def build(self):
        file_meta = dict()
        filekey = None

        lines = []
        for root, dirs, files in os.walk(self._dir_name):
            for pattern in self._patterns:
                for filename in fnmatch.filter(files, pattern):
                    folder_path = PurePath(root)
                    if len(folder_path.parts) - len(PurePath(self._dir_name).parts) == 1:
                        print(root, filename)
                        key = PurePath(root).parts[-1]
                        #print(key)
                        value = json.load(open(PurePath(folder_path, filename), 'r'))
                        print(value['task_arguments'])
                        '''
                        e.g {'rupture_set_file_id': 'RmlsZTo0ODMuMFN3cTRN', 'generation_task_id': 'UnVwdHVyZUdlbmVyYXRpb25UYXNrOjE4M0FoblN5',
                        'solution_file': '/home/chrisbc/DEV/GNS/opensha-new/nshm-nz-opensha/src/python/automation/tmp/UnVwdHVyZUdlbmVyYXRpb25UYXNrOjE4M0FoblN5/InversionSolution-RmlsZTo2-rnd0-t1380_RmlsZTo0ODMuMFN3cTRN.zip',
                        'short_name': 'CFM_0_9_SANSTVZ_D90-0.1', 'rupture_class': 'Azimuth', 'max_inversion_time': '1380', 'completion_energy': '0.05', 'round_number': '0'}
                        '''
                        try:
                            solution_name = PurePath( value['task_arguments']['file_path']).name
                        except (KeyError):
                            break

                        #print(solution_name)
                        solution_filepath = Path(folder_path, '..', value['task_arguments']['file_id'], solution_name).resolve()
                        #print(solution_filepath)

                        info = dict(
                            key = key,
                            meta = value['task_arguments'],
                            solution_relative_path = os.path.relpath(solution_filepath, start = PurePath(self._dir_name)),
                            index_path = os.path.relpath(PurePath(folder_path, "named_fault_mfds"), start = PurePath(self._dir_name)),
                            )

                        #TODO: ugly workaround, FIXME in NEXT beavan
                        rupture_class = "Azimuth"
                        azim_len = len("UnVwdHVyZUdlbmVyYXRpb25UYXNrOjE4NXN4Zjhp/InversionSolution-RmlsZTo2-rnd0-t1380_RmlsZTo1MDcuMDdaMkFp.zip")
                        if len(info['solution_relative_path']) > azim_len:
                            rupture_class = "Coulomb"
                        info['meta']['rupture_class'] = rupture_class
                        lines.append(info)
        return lines


    def link_li_template(self, title, path):
        return  f'''
            <li id="{title}"><a href="{path}" >{title}</a> - <a href="#{title}-inline_img" >see below</a> </li>
            '''

    def nav_li_template(self, title, path):
        return  f'''<li id="{title}"><a href="{path}" ><h3>{title}</h3></a></li>'''



    def plot_div_template(self, title, path):
        return  f'''
            <div id="{title}-inline_img" align="center"><a href="{path}" ><img src="{path}" alt="{title} "width="500" /></a><p><a href="#top">top</a></p></div>
            '''


    def build_image_index(self, image_folder):
        file_meta = dict()
        filekey = None
        patterns = ["*.png",]

        lines = []
        for root, dirs, files in os.walk(image_folder):
            for pattern in patterns:
                    for filename in sorted(fnmatch.filter(files, pattern)):
                        folder_path = PurePath(root)
                        rel_path = PurePath(folder_path.parts[-1], filename)
                        title = filename.replace(".png", "").replace("_", " ")
                        yield (title, str(rel_path))


    def sub_index_template(self, solution_info, mfd_folder='nucleation_cumulative'):

        m = solution_info['meta']

        report_info  = "" #f"{m['short_name']} {m['rupture_class']} energy({m['completion_energy']}) round({m['round_number']})"
        list_insertion = "".join([self.link_li_template(title, path) for (title, path) in self.build_image_index(Path(self._dir_name, solution_info['index_path'], mfd_folder))])
        img_insertion = "".join([self.plot_div_template(title, path) for (title, path) in self.build_image_index(Path(self._dir_name, solution_info['index_path'], mfd_folder))])

        if len(list_insertion) == 0:
            return

        return f"""
            <html>
            <head></head>
                <div>
                <h1 id="top" >NZSHM22 Named Fault MFD plots: <strong>{mfd_folder}</strong> </h1>
                <!--<p>{report_info}</p>-->
                <p>ID: {m['file_id']} </p>
                <ul>
                {list_insertion}
                </ul>

                </div>
                <h2>All the images</h2>
                <div align="left">
                <ul>
                {img_insertion}
                </ul>

                </div>
            </html>"""


    def main_index_template(self, solution_info, links):

        m = solution_info['meta']
        report_info  = "" #f"{m['short_name']} {m['rupture_class']} energy({m['completion_energy']}) round({m['round_number']})"
        list_insertion = "".join([self.nav_li_template(link, link +'-index.html') for link in links])

        if len(list_insertion) == 0:
            return

        return  f"""
            <html>
            <head></head>

                <div>
                <h1 id="top" >NZSHM22 Named Fault MFD plots</strong> </h1>

                <!--<p>{report_info}</p>-->

                <p>ID: {m['file_id']}  <a href="{TUI}FileDetail/{m['file_id']}">file detail</a></p>

                <ul>
                {list_insertion}
                </ul>

                </div>
            </html>"""


    def build_mfd_indexes(self, solution_info):

        links = ['nucleation_cumulative', 'nucleation_incremental', 'participation_cumulative', 'participation_incremental']

        #build sub-indices
        for mfd_folder in copy(links):
            idx = self.sub_index_template(solution_info, mfd_folder)
            if not idx:
                links.remove(mfd_folder)
                continue

            with open(Path(self._dir_name, solution_info['index_path'], mfd_folder + '-index.html'), 'w') as index_html:
                index_html.write(idx)
                index_html.close()

        if len(links):
            #main index
            with open(Path(self._dir_name, solution_info['index_path'], 'mfd_index.html'), 'w') as index_html:
                idx = self.main_index_template(solution_info, links)
                index_html.write(idx)
                index_html.close()

        return links

def main():

    meta_builder = NamedFaultIndexBuilder(path = WORK_PATH )

    solution_infos = meta_builder.build()
    for info in solution_infos:
        if len(meta_builder.build_mfd_indexes(info)) > 0:
            #list of folders for main index
            print(info["meta"]["file_id"])
        # else:
        #     print("skip " + info["meta"]["rupture_set_file_id"])


if __name__ == "__main__":
    main()
