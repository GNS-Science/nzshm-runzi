
# Opensha Processes

## 1. Rupture sets

Rupture sets are built using the `run_{TYPE}_rupture_sets.py scripts`. There are three scripts, one each for Azimuthal, Coulomb and Subduction.

### 1.1 Producing rupture sets

 - [x] activate the venv (automation)
 - [x] update the rupture specifications and the the job descriptions in `automation\run_{TYPE}_rupture_sets.py`
 - [x] make sure the Toshi env vars are set
 - [x] run the script (note that coulomb must be run on cluster due to memory demands)
       `(automation) $ python run_subduction_rupture_sets.py`
       note the GENERAL_TASK_ID: R2VuZXJhbFRhc2s6NjE1aHdiNFM=
 - [x] update the log


### 1.1 Producing rupture set diagnostic reports

 - [x] activate the venv (automation)
 - [x] update the upstream_task_id in `automation\run_ruptset_diagnostics.py`
 - [x] run the reports (locally usually)
 - [x] copy the data folders (FileData:ID) to publication DATAXX folder
 - [x] run `python build_named_fault_mfd_index.py`
 - [x] update the GID & folder and info_keys in  `automation\build_manual_index.py` and run it
 - [x] copy/paste into index.html & check

### 1.2 Copy up to S3

Locations used by the manual index....
```
./s5cmd -numworkers 64 cp --acl public-read DATA{NN}/ s3://nzshm22-rupset-diags-poc/DATA{NN}/
./s5cmd --stat -numworkers 128 cp --acl public-read index.html s3://nzshm22-rupset-diags-poc/
```

Locations (to be) used by the TOSHI-UI....

```
./s5cmd -numworkers 64 cp -u -n --acl public-read s3://nzshm22-rupset-diags-poc/DATA{NN}/* s3://nzshm22-static-reports/opensha/DATA/
```

## s5cmd to transfer S3 data efficiently

examples

```
./s5cmd -numworkers 64 cp --acl public-read DATA9/ s3://nzshm22-rupset-diags-poc/DATA9/
./s5cmd --stat -numworkers 128 cp --acl public-read index.html s3://nzshm22-rupset-diags-poc/
```
