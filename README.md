# nzshm-runzi


[![pypi](https://img.shields.io/pypi/v/nzshm-runzi.svg)](https://pypi.org/project/nzshm-runzi/)
[![python](https://img.shields.io/pypi/pyversions/nzshm-runzi.svg)](https://pypi.org/project/nzshm-runzi/)
[![Build Status](https://github.com/GNS-Science/nzshm-runzi/actions/workflows/dev.yml/badge.svg)](https://github.com/GNS-Science/nzshm-runzi/actions/workflows/dev.yml)
[![codecov](https://codecov.io/gh/GNS-Science/nzshm-runzi/branch/main/graphs/badge.svg)](https://codecov.io/github/GNS-Science/nzshm-runzi)

* Documentation: <https://GNS-Science.github.io/nzshm-runzi>
* GitHub: <https://github.com/GNS-Science/nzshm-runzi>
* PyPI: <https://pypi.org/project/nzshm-runzi/>
* Free software: GPL-3.0-only

Python application for running, scheduling, collecting inputs &amp; outputs of NZSHM jobs on workstations, AWS cloud, and HPC cluster

runzi is used by the ESNZ NSHM programme to run OpenSHA style inversions, hazard calculations, and other computational tasks.

- Provides a CLI for launching jobs locally or using AWS EC2 services (HPC is currently unsupported after the move from PBS to Slurm).
- Coordinates with [toshi API](https://github.com/GNS-Science/nshm-toshi-api) and [toshi-hazard-store](https://github.com/GNS-Science/toshi-hazard-store) to lookup and store results and metadata.

## Run
```console
$ runzi [OPTIONS] COMMAND [ARGS]...
```

```console
$ runzi --help
```



