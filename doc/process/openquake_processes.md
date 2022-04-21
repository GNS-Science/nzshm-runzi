# Openquake processes

## Toshi Schema Definitions (graphl schema types)

 **Configuration Template Archive** is a File  (zip archive) containing openquake configuration files (except for sources)

   -  see `run_save_oq_configuration_template.py` below

 **OpenquakeHazardTask (OHT)** is a AutomationTask that has sub-components that are specific to OQ hazard

   -  see `run_oq_hazard.py` below

 **OpenQuakeHazardSolution** is an Object capturing the results of a succesful OHT

 **OpenquakeHazardConfig** is an Object containing all the configuration elements for a given OHT

 **InversionSolutionNrml** is a File object with attributes specific to an  Openquake NRML XML source model.

   -  see `run_oq_convert_solutionhazard.py` below


**Save an arbritrary file**

```
python3 runzi/automation/run_save_file_archive.py ~/Downloads/Floor_ADDTOT346ave-base.xml -t BG_Kiran_Floor_ADDTOT346ave-base
```



