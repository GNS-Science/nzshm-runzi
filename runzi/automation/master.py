#!/usr/bin/env python
import sys

import numpy
from mpi4py import MPI

comm = MPI.COMM_SELF.Spawn(sys.executable, args=['worker.py'], maxprocs=5)

print("comm", comm)

N = numpy.array(100, 'i')
comm.Bcast([N, MPI.INT], root=MPI.ROOT)
PI = numpy.array(0.0, 'd')

comm.Reduce(None, [PI, MPI.DOUBLE], op=MPI.SUM, root=MPI.ROOT)

print()
print(PI)

comm.Disconnect()
