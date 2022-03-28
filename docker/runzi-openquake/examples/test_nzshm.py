import gzip
import unittest
import numpy
from openquake.baselib import parallel, general, config
from openquake.baselib.python3compat import decode
from openquake.hazardlib import InvalidFile, contexts
from openquake.hazardlib.source.rupture import get_ruptures
from openquake.hazardlib.sourcewriter import write_source_model
from openquake.commonlib import readinput    
from openquake.calculators.tests import (
    CalculatorTestCase, NOT_DARWIN, strip_calc_id)

# hacked from https://github.com/gem/oq-engine/blob/7e8dc6fdd0d50da41cfed76ec901838e5c929b32/openquake/calculators/tests/classical_test.py

class ClassicalTestCase(CalculatorTestCase):

    def assert_curves_ok(self, expected, test_dir, delta=None, **kw):
        kind = kw.pop('kind', '')
        self.run_calc(test_dir, 'job.ini', **kw)
        ds = self.calc.datastore
        got = (export(('hcurves/' + kind, 'csv'), ds) +
               export(('hmaps/' + kind, 'csv'), ds) +
               export(('uhs/' + kind, 'csv'), ds))
        self.assertEqual(len(expected), len(got), str(got))
        for fname, actual in zip(expected, got):
            self.assertEqualFiles('expected/%s' % fname, actual,
                                  delta=delta)
        return got


    def test_case_65(self):
        # reading/writing a multiFaultSource

        #oq = readinput.get_oqparam('job.ini', pkg=case_65)

        inifile = "/WORKING/examples/16_SRWG_TEST/oq_inputs/many-sites_3-periods_vs30-475.ini"
        oq = readinput.get_oqparam(inifile)
        csm = readinput.get_composite_source_model(oq)
        tmpname = general.gettemp()
        out = write_source_model(tmpname, csm.src_groups)
        self.assertEqual(out[0], tmpname)
        self.assertEqual(out[1], tmpname[:-4] + '_sections.xml')

        # running the calculation
        self.run_calc(case_65.__file__, 'job.ini')

        [f] = export(('hcurves/mean', 'csv'), self.calc.datastore)
        self.assertEqualFiles('expected/hcurve-mean.csv', f, delta=1E-5)

        # make sure we are not breaking event_based
        self.run_calc(case_65.__file__, 'job_eb.ini')
        [f] = export(('ruptures', 'csv'), self.calc.datastore)
        self.assertEqualFiles('expected/ruptures.csv', f, delta=1E-5)

        rups = extract(self.calc.datastore, 'ruptures')
        csv = general.gettemp(rups.array)
        self.assertEqualFiles('expected/full_ruptures.csv', csv, delta=1E-5)

        files = export(('gmf_data', 'csv'), self.calc.datastore)
        self.assertEqualFiles('expected/gmf_data.csv', files[0], delta=1E-4)