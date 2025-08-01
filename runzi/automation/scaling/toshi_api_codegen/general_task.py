from runzi.automation.scaling.local_config import API_KEY, API_URL
import asyncio
from typing import Optional
from runzi.automation.scaling.toshi_api_codegen.graphql_client import Client, KeyValueListPairInput, TaskSubType, ModelType
import datetime as dt
from dateutil.tz import tzutc


async def _create_task(
    title: str,
    agent_name: str,
    description: str,
    argument_lists: list[KeyValueListPairInput],
    subtask_type: TaskSubType,
    model_type: ModelType,
    meta: Optional[list] = None,
) -> str:

    meta = meta or []

    try:
        client = Client(
            url= API_URL,
            headers={"X-API-KEY": API_KEY}
        )
        response = await client.create_general_task(
            created=dt.datetime.now(tzutc()).isoformat(),
            agent_name=agent_name,
            title=title,
            description=description,
            argument_lists=argument_lists,
            subtask_type=subtask_type,
            subtask_count=0,
            model_type=model_type,
            meta=[],
        )

        return response.create_general_task.general_task.id
    except Exception as e:
        raise e

async def _update_subtask_cout(gt_id: str, subtask_count: int) -> bool:
    try:
        client = Client(
            url= API_URL,
            headers={"X-API-KEY": API_KEY}
        )
        response = await client.update_subtask_count(gt_id, subtask_count)
    except Exception as e:
        raise e
    return response.update_general_task.ok
    

def update_subtask_count(gt_id: str, subtask_count: int) -> bool:
    return asyncio.run(_update_subtask_cout(gt_id, subtask_count))



def create_task(
    title: str,
    agent_name: str,
    description: str,
    argument_lists: list[KeyValueListPairInput],
    subtask_type: TaskSubType,
    model_type: ModelType,
    meta: Optional[list] = None,
) -> str:
    return asyncio.run(_create_task(
        title, agent_name, description, argument_lists, subtask_type, model_type, meta
    ))


if __name__ == "__main__":
    agent_name = "chris_dicaprio"
    title = "testing generated API client"
    description  = "a description of" + title
    argument_lists = [
        KeyValueListPairInput(k="keyA", v=["valueA1, valueA2"]),
        KeyValueListPairInput(k="keyB", v=["valueB1, valueB2"])
    ]
    subtask_type = TaskSubType.INVERSION
    model_type = ModelType.CRUSTAL
    gt_id =  create_task(
        title,
        agent_name,
        description,
        argument_lists,
        subtask_type,
        model_type,
    )
    print(gt_id)

    ok = update_subtask_count(gt_id, 100)
    print(ok)


