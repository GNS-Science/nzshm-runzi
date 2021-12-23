# build_rupture_set_index

"""
Simple script to create valid URLs
only to be used until we have automated rupture reporting

"""

import os

import urllib.request
import shutil
import fnmatch
from pathlib import PurePath, Path
from datetime import datetime as dt
import pytz

import base64
import json
import collections

from runzi.automation.scaling.toshi_api import ToshiApi
from runzi.automation.scaling.local_config import WORK_PATH


class GeneralTaskBuilder:
    """
    find the metadata.json and make this available for the HTML
    """

    def __init__(self, path, date_path):
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
        m = info["meta"]
        report_info = f"{m['short_name']} {m['rupture_class']} energy({m['completion_energy']}) round({m['round_number']})"

        if m["rupture_set_file_id"] in mfd_dirs:
            extra_link = f'&nbsp;<a href="{self._date_path}-{self.set_number}/{m["rupture_set_file_id"]}/named_fault_mfds/mfd_index.html" >Named MFDS</a>'
        else:
            extra_link = ""

        return f"""<li>{report_info}&nbsp;
    <a href="{self._date_path}-{self.set_number}/{info['index_path']}" >Diagnostics report</a>&nbsp;
    <a href="{self._date_path}-{self.set_number}/{info['solution_relative_path']}" >Download solution file</a>
    {extra_link}</li>"""


def gt_template(node, general_task_id, tui):
    title = node.get("title")
    description = node.get("description")

    NZ_timezone = pytz.timezone("NZ")
    created = dt.strptime(node.get("created"), "%Y-%m-%dT%H:%M:%S.%f%z").astimezone(
        NZ_timezone
    )

    return f"""
    <h2>{title}</h2>
    <p>{created.strftime("%Y-%m-%d %H:%M:%S %z")}</p>
    <a href="{tui}GeneralTask/{general_task_id}">{general_task_id}</a>
    <p>{description}</p>
    """


def get_file_meta(file_node, tui, display_keys=[]):
    display_keys = [k[:-1] if k[-2:] == "ts" else k for k in display_keys]
    display_info = ""
    for kv_pair in file_node["meta"]:
        if kv_pair["k"] in display_keys:
            if kv_pair["k"] == "rupture_set_file_id":
                info = f"<a href ='{tui}FileDetail/{kv_pair['v']}'>{kv_pair['v']}</a>"
            else:
                info = kv_pair["v"]
            display_info += f"{kv_pair['k']}:{info}, "

    display_info = display_info[:-2]
    return display_info


def rgt_template(rgt, upload_folder, tui, display_keys=None):
    """'id': 'UnVwdHVyZUdlbmVyYXRpb25UYXNrOjE4ODNXcnFN', 'created': '2021-06-10T10:23:23.457361+00:00', 'state': 'DONE', 'result': 'SUCCESS',"""
    rid = rgt["id"]
    result = rgt["result"]
    fname = None
    display_keys = display_keys or []
    display_info = ""
    # return f'<li><a href="{TUI}RuptureGenerationTask/{rid}">Rupture set {rid}</a>result: {result}</li>'
    for file_node in rgt["files"]["edges"]:
        fn = file_node["node"]
        if fn["role"] == "WRITE" and "zip" in fn["file"]["file_name"]:
            fname = fn["file"]["file_name"]
            fid = fn["file"]["id"]
            display_info = get_file_meta(fn["file"], tui, display_keys)
            break

    if fname:
        return f"""<li>
            <a href="{tui}Find/{rid}">{rid}</a> result: {result} &nbsp;
            <a href="{tui}FileDetail/{fid}">File detail</a> &nbsp;
            <a href="{upload_folder}/{fid}/DiagnosticsReport/index.html">Diagnostics report</a>
            <br />
            <div class="display_info">{display_info}</div>
            <br />
        </li>
        """
    else:
        return f"""<li>
            <a href="{tui}RuptureGenerationTask/{rid}">{rid}</a> result: {result}
        </li>
        """


def solution_diags_div(fid, upload_folder):
    return f"""<a href="{upload_folder}/{fid}/solution_report/index.html">Diagnostics</a> &nbsp;"""


def inv_template(rgt, upload_folder, tui, display_keys=None):
    rid = rgt["id"]
    result = rgt["result"]
    fname = None
    fault_model = ""
    display_info = ""
    display_keys = display_keys or []
    if not rgt.get("files"):
        return ""

    for file_node in rgt["files"]["edges"]:
        fn = file_node["node"]
        # get solution details
        if fn["role"] == "WRITE" and "zip" in fn["file"]["file_name"]:
            fname = fn["file"]["file_name"]
            fid = fn["file"]["id"]
            display_info = get_file_meta(fn["file"], tui, display_keys)

        # extract mmode from the rupture set
        if fn["role"] == "READ" and "zip" in fn["file"]["file_name"]:
            for kv_pair in fn["file"]["meta"]:
                if kv_pair["k"] == "fault_model":
                    fault_model = kv_pair["v"]
                    break

    if fname:
        named_faults_link = f'<a href="{upload_folder}/{fid}/named_fault_mfds/mfd_index.html">Named fault MFDs</a>'
        solution_diags = solution_diags_div(fid, upload_folder) or ""

        return f"""<li>
            <a href="{tui}Find/{rid}">{rid}</a> result: {result}&nbsp;
            <a href="{tui}InversionSolution/{fid}">Inversion Solution detail</a>&nbsp;
            {solution_diags}
            {named_faults_link}

            <br />
            <div class="display_info">{display_info}</div>
            <br />

        </li>
        """
    else:
        return f"""<li>
            <a href="{tui}RuptureGenerationTask/{rid}">{rid}</a> result: {result}
        </li>
        """


def build_manual_index(
    general_task_id,
    subtask_type,
    multiple_entries=False,
    index_url="http://nzshm22-static-reports.s3-website-ap-southeast-2.amazonaws.com/opensha/index.html"
):

    API_URL = os.getenv("NZSHM22_TOSHI_API_URL", "http://127.0.0.1:5000/graphql")
    API_KEY = os.getenv("NZSHM22_TOSHI_API_KEY", "")
    S3_URL = os.getenv("NZSHM22_TOSHI_S3_URL", "http://localhost:4569")
    UPLOAD_FOLDER = "./DATA"
    TUI = "http://simple-toshi-ui.s3-website-ap-southeast-2.amazonaws.com/"

    headers = {"x-api-key": API_KEY}
    general_api = ToshiApi(
        API_URL, S3_URL, None, with_schema_validation=True, headers=headers
    )

    try:
        node = general_api.get_general_task_subtask_files(general_task_id)
    except Exception as e:
        print(f"Error while getting the General Task: {e}")
        return

    info_keys = node["swept_arguments"]
    # print(info_keys)

    def node_template(node, info_keys):
        node_list = []
        for child_node in node["children"]["edges"]:
            rgt = child_node["node"]["child"]
            if subtask_type == "RUPTSET":
                node_list.append(
                    rgt_template(rgt, UPLOAD_FOLDER, TUI, info_keys)
                )  # rupt sets
            elif subtask_type == "INVERSION":
                node_list.append(
                    inv_template(rgt, UPLOAD_FOLDER, TUI, info_keys)
                )  # inversions
        return "".join(node_list)

    new_entries = f"""
<hr />
    {gt_template(node, general_task_id, TUI)}
<ul>
    {node_template(node, info_keys)}
</ul>
<hr />
    """

    if multiple_entries == False:
        index_request = urllib.request.Request(index_url)
        index_html = urllib.request.urlopen(index_request)
        parsed_index_html = index_html.read().decode("utf-8")
        elements = parsed_index_html.split("<hr />", 1)
        new_index_html = elements[0] + new_entries + elements[1]
    else:
        with open(f"{WORK_PATH}/index.html", "r") as index:
            parsed_index_html = index.read()
            elements = parsed_index_html.split("<hr />", 1)
            new_index_html = elements[0] + new_entries + elements[1]

    with open(f"{WORK_PATH}/index.html", "w") as f:
        f.write(new_index_html)
    print(f"Finished! New index is at {WORK_PATH}/index.html")
