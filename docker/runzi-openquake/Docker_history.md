Docker History

```
   19  time oq engine --run /WORKING/examples/16_SRWG_TEST/oq_inputs/many-sites_3-periods_vs30-475.ini
   20  oq engine --export-outputs 8 /WORKING/examples/output/PROD/34-sites-few-ASK2014-CRU
   21  cp /home/openquake/oqdata/calc_8.hdf5 /WORKING/examples/output/PROD/34-sites-few-ASK-2014-CRU.hdf5
   22  cd /opt/openquake/lib/python3.8/site-packages
   23  ls
   24  cat openquake.engine.egg-link
   25  cd /usr/src/oq-engine/
   26  ls
   27  cd openquake
   28  ls
   29  cd hazardlib/gsim
   30  ls
   31  cp /WORKING/examples/mcverry_2006_MW.py .
   32  whoami
   33  time oq engine --run /WORKING/examples/16_SRWG_TEST/oq_inputs/many-sites_3-periods_vs30-475.ini
   34  whoami
   35  time oq engine --run /WORKING/examples/16_SRWG_TEST/oq_inputs/many-sites_3-periods_vs30-475.ini
   36  cp /home/openquake/oqdata/calc_9.hdf5 /WORKING/examples/output/PROD/34-sites-few-MKV-CRU.hdf5
   37  oq engine --export-outputs 9 /WORKING/examples/output/PROD/34-sites-few-MKV-CRU
   38  time oq engine --run /WORKING/examples/16_SRWG_TEST/oq_inputs/many-sites_3-periods_vs30-475.ini
   39  oq engine --run /WORKING/examples/16_SRWG_TEST/oq_inputs/many-sites_3-periods_vs30-475.ini
   40  time oq engine --run /WORKING/examples/16_SRWG_TEST/oq_inputs/many-sites_3-periods_vs30-475.ini
   41  oq engine --export-outputs 12 /WORKING/examples/output/PROD/34-sites-few-CRU+BG
   42  cp /home/openquake/oqdata/calc_12.hdf5 /WORKING/examples/output/PROD/34-sites-few-CRU+BG.hdf5
   43  pytest /WORKING/examples/test_nzshm.py -vv
   44  time oq engine --run /WORKING/examples/16_SRWG_TEST/oq_inputs/many-sites_3-periods_vs30-475.ini
   45  cp /home/openquake/oqdata/calc_13.hdf5 /WORKING/examples/output/PROD/34-sites-few-CRU+HIK.hdf5
   46  oq engine --export-outputs 13 /WORKING/examples/output/PROD/34-sites-few-CRU+HIK
   47  time oq engine --run /WORKING/examples/16_SRWG_TEST/oq_inputs/many-sites_3-periods_vs30-475.ini
   48  time oq engine --run /WORKING/examples/16_SRWG_TEST/oq_inputs/WLG_many-periods_vs30-475.ini
   49  oq engine --export-outputs 18 /WORKING/examples/output/PROD/WLG-many-HIK+BG
   50  cp /home/openquake/oqdata/calc_18.hdf5 /WORKING/examples/output/PROD/WLG-many-HIK+BG.hdf5
   51  time oq engine --run /WORKING/examples/17_SUMMING_ISSUE/17_summing_issue.ini
   52  ls -lath /home/openquake/oqdata/
   53  oq engine --export-outputs 20 /WORKING/examples/output/17_SUMMING/CRU_AND_SUB
   54  time oq engine --run /WORKING/examples/17_SUMMING_ISSUE/17_summing_issue.ini
   55  oq engine --export-outputs 21 /WORKING/examples/output/17_SUMMING/CRU_ONLY
   56  time oq engine --run /WORKING/examples/17_SUMMING_ISSUE/17_summing_issue.ini > /WORKING/examples/output/17_SUMMING/BOTH.log &
   57  tail /WORKING/examples/output/17_SUMMING/BOTH.log
   58  head /WORKING/examples/output/17_SUMMING/BOTH.log
   59  oq engine --export-outputs 22 /WORKING/examples/output/17_SUMMING/BOTH
   60  time oq engine --run /WORKING/examples/17_SUMMING_ISSUE/17_summing_issue.ini
   61  oq engine --export-outputs 23 /WORKING/examples/output/17_SUMMING/ASK_BOTH
   62  time oq engine --run /WORKING/examples/17_SUMMING_ISSUE/17_summing_issue.ini
   63  oq engine --export-outputs 24 /WORKING/examples/output/17_SUMMING/ASK_CRU
   64  time oq engine --run /WORKING/examples/17_SUMMING_ISSUE/17_summing_issue.ini
   65  oq engine --export-outputs 25 /WORKING/examples/output/17_SUMMING/ASK_SUB
   66  time oq engine --run /WORKING/examples/17_SUMMING_ISSUE/17_summing_issue.ini
   67  oq engine --export-outputs 26 /WORKING/examples/output/17_SUMMING/NZSHM_SUB
   68  time oq engine --run /WORKING/examples/17_SUMMING_ISSUE/17_summing_issue.ini
   69  oq engine --export-outputs 27 /WORKING/examples/output/17_SUMMING/NZSHM_CRU
   70  time oq engine --run /WORKING/examples/17_SUMMING_ISSUE/17_summing_issue.ini
   71  oq engine --export-outputs 28 /WORKING/examples/output/17_SUMMING/NZSHM_BOTH
   72  history
   ```