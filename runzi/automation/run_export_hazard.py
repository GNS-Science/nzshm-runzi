import csv
import datetime as dt

from scaling.local_config import API_KEY, API_URL, S3_URL
from scaling.toshi_api import ToshiApi  # , CreateGeneralTaskArgs

if __name__ == "__main__":

    t0 = dt.datetime.utcnow()

    headers={"x-api-key":API_KEY}
    toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)

    ids = ["SW52ZXJzaW9uU29sdXRpb246MjI4NjUuMFpXa3da",
            "SW52ZXJzaW9uU29sdXRpb246MjI4NjguMG1hUlNN",
            "SW52ZXJzaW9uU29sdXRpb246MjI4ODAuME1NdlVa",
            "SW52ZXJzaW9uU29sdXRpb246MjI4ODYuMFhCY1J4",
            "SW52ZXJzaW9uU29sdXRpb246MjI4NzUuMFZCWEJq",
            "SW52ZXJzaW9uU29sdXRpb246MjI4OTMuMGJURnk4",
            "SW52ZXJzaW9uU29sdXRpb246MjI4ODcuMGU2b1JM",
            "SW52ZXJzaW9uU29sdXRpb246MjI5MDIuMGR5UGV2"]

    csvfile = open('hazard.csv', 'w', newline='')
    writer = None

    for solution_id in ids:
        solution = toshi_api.inversion_solution.get_solution(solution_id)
        print(f"process solution: {solution_id}")
        for table in solution.get('tables'):
            if table.get('table_type') == "HAZARD_SITES":
                table_id = table.get('table_id')

                hazard = toshi_api.table.get_table(table_id)
                if not writer:
                    writer = csv.writer(csvfile)
                    writer.writerow(hazard.get("column_headers"))

                print(f"writing hazard for table {table_id}")
                writer.writerows( hazard.get('rows'))

    print("Done! in %s secs" % (dt.datetime.utcnow() - t0).total_seconds())
