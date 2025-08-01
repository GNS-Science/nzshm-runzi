from runzi.automation.scaling.local_config import API_KEY, API_URL
import asyncio
from typing import Optional, Any, Dict
from runzi.automation.scaling.toshi_api_codegen.graphql_client import Client, KeyValueListPairInput, TaskSubType, ModelType
import datetime as dt
from dateutil.tz import tzutc

async def _get_file_info(file_id: str) -> dict[str, Any]:

    client = Client(
        url= API_URL,
        headers={"X-API-KEY": API_KEY}
    )
    response = await client.get_file_detail(file_id)
    fault_model = ""
    max_jump_distance = ""

    # if response.node. api_result['file_name'][-3:] == "zip":
    #     res = dict(id=api_result['id'], file_name=api_result['file_name'], file_size=api_result['file_size'])

    #     if api_result.get('meta'):
    #         for kv in api_result['meta']:
    #             if kv.get('k') == 'fault_model':
    #                 fault_model = kv.get('v')

    #         for kv in api_result['meta']:
    #             if kv.get('k') == 'max_jump_distance':
    #                 max_jump_distance = kv.get('v')

    #     if fault_model:
    #         res['fault_model'] = fault_model
    #     if max_jump_distance:
    #         res['max_jump_distance'] = max_jump_distance
    #     return res

    return response

def get_file_info(file_id: str) -> dict[str, Any]:
    return asyncio.run(_get_file_info(file_id))


if __name__ == "__main__":

    response = get_file_info("RmlsZToxMDAwNjk=")