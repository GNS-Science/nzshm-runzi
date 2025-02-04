import csv
import tempfile
from pathlib import Path
from zipfile import ZipFile

import pytest


def get_mags(properties_file_path):
    magnitudes = []
    with open(properties_file_path, 'r') as properties_file:
        reader = csv.reader(properties_file)
        header = next(reader)
        for row in reader:
            magnitudes.append(float(row[1]))

    return magnitudes


def get_rates(rates_file_path):
    rates = []
    with open(rates_file_path, 'r') as rates_file:
        reader = csv.reader(rates_file)
        header = next(reader)
        for row in reader:
            rates.append(float(row[1]))
        
    return rates

def test_scale_inversion_polygon():
    inv_soln_archive_path = Path(Path(__file__).parent, 'fixtures/NZSHM22_InversionSolution-QXV0b21hdGlvblRhc2s6MTA3MDA2.zip')
    scaled_soln_archive_path = Path(Path(__file__).parent, 'fixtures/NZSHM22_ScaledInversionSolution-QXV0b21hdGlvblRhc2s6MTEzMTA0.zip')

    with tempfile.TemporaryDirectory() as tmpdir:
        with ZipFile(inv_soln_archive_path) as inv_soln_archive:
            with ZipFile(scaled_soln_archive_path) as scaled_soln_archive:

                properties_path = inv_soln_archive.extract('ruptures/properties.csv', path=Path(tmpdir, 'inv_soln', 'properties.csv'))
                inv_rates_path = inv_soln_archive.extract('solution/rates.csv', path=Path(tmpdir, 'inv_soln', 'rates.csv'))
                scaled_rates_path = scaled_soln_archive.extract('solution/rates.csv', path=Path(tmpdir, 'scaled_soln', 'rates.csv'))

        magnitudes = get_mags(properties_path)
        rates_orig = get_rates(inv_rates_path)
        rates_scaled = get_rates(scaled_rates_path)

        assert len(rates_orig) == len(rates_scaled)

        for i in range(len(rates_orig)):
            if magnitudes[i] > 8.0:
                assert pytest.approx(rates_orig[i]*1.41) == rates_scaled[i]
            else:
                assert pytest.approx(rates_orig[i]*1.41*0.8) == rates_scaled[i]

def test_scale_inversion():
    inv_soln_archive_path = Path(Path(__file__).parent, 'fixtures/NZSHM22_AveragedInversionSolution-QXV0b21hdGlvblRhc2s6MTA3MzE3.zip')
    scaled_soln_archive_path = Path(Path(__file__).parent, 'fixtures/NZSHM22_ScaledInversionSolution-QXV0b21hdGlvblRhc2s6MTA3NjY4.zip')

    with tempfile.TemporaryDirectory() as tmpdir:
        with ZipFile(inv_soln_archive_path) as inv_soln_archive:
            with ZipFile(scaled_soln_archive_path) as scaled_soln_archive:

                properties_path = inv_soln_archive.extract('ruptures/properties.csv', path=Path(tmpdir, 'inv_soln', 'properties.csv'))
                inv_rates_path = inv_soln_archive.extract('solution/rates.csv', path=Path(tmpdir, 'inv_soln', 'rates.csv'))
                scaled_rates_path = scaled_soln_archive.extract('solution/rates.csv', path=Path(tmpdir, 'scaled_soln', 'rates.csv'))

        magnitudes = get_mags(properties_path)
        rates_orig = get_rates(inv_rates_path)
        rates_scaled = get_rates(scaled_rates_path)

        assert len(rates_orig) == len(rates_scaled)

        for i in range(len(rates_orig)):
            assert pytest.approx(rates_orig[i]*0.42) == rates_scaled[i]
