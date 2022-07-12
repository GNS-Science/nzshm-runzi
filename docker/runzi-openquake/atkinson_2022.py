# -*- coding: utf-8 -*-
# vim: tabstop=4 shiftwidth=4 softtabstop=4
#
# Copyright (C) 2015-2018 GEM Foundation
#
# OpenQuake is free software: you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# OpenQuake is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with OpenQuake. If not, see <http://www.gnu.org/licenses/>.

"""
Author: s.bora@gns.cri.nz/e.manea@gns.cri.nz

Module exports :class:`Atkinson2022Crust`
               :class:`Atkinson2022SSlab`
               :class:`Atkinson2022SInter`
"""

import math
import os
import numpy as np
from openquake.hazardlib import const
from openquake.hazardlib.gsim.base import GMPE, CoeffsTable
from openquake.hazardlib.imt import PGA, SA

Atk22_COEFFS = os.path.join(os.path.dirname(__file__),
                          "Atkinson22_coeffs_mod_v8b_sanjay_v2.csv")
#print(Atk22_COEFFS)

def _fmag(suffix, C, mag):
    """
    ctx.magnitude factor.
    """
    if suffix == "slab":
        #res = C['c0_' + suffix] + C['c1_' + suffix] * (mag - 6.0) + C['c2_' + suffix] * (mag - 6.0) ** 2
        # Modified as in RevisionsToBackbonev8 from Gail received on 21.06.2022.
        res = C['c0_' + suffix] + C['c1_' + suffix] * (mag) + C['c2_' + suffix] * (mag) ** 2
    else:
        res = C['c0_crust'] + C['c1_crust'] * (mag) + C['c2_crust'] * (mag) ** 2
    return res


def _fz_ha18(C, ctx):
    """
    Implements eq. 2,3,4,5 from page 5
    """
    # pseudo-depth

    #h = 10 ** (-0.1 + 0.2 * ctx.mag)
    # The h term is modified after receiving the modifications from Gail on Slack on 12.06.2022.
    #h = 10 ** (0.3 + 0.11 * ctx.mag)
    # Modified as in RevisionsToBackbonev8 from Gail received on 21.06.2022. However, there is a typo.
    h = 10**(-0.405 + 0.235 * ctx.mag)
    R = np.sqrt(ctx.rrup ** 2 + h ** 2)
    Rref = np.sqrt(1 + h ** 2)
    # The transition_distance
    Rt = 50
    # Geometrical spreading rates
    b1 = -1.3
    b2 = -0.5
    # Geometrical attenuation
    z = R**b1
    ratio = R/Rt
    z[R > Rt] = (Rt**b1 * (ratio[R > Rt])**b2)

    return np.log(z) + (C['b3'] + C['b4'] * ctx.mag) * np.log(R/Rref)

def _fgamma (suffix, C, ctx):
    if suffix == "crust":
        g1 = min(0.008, 0.005 + 0.0016 * np.log(C['f']))
    elif suffix == "inter":
        g1 = min(0.006, 0.0045 + 0.0014 * np.log(C['f']))
    else:
        g1 = min(0.005, 0.004 + 0.0012 * np.log(C['f']))

    a2 = max(0.002 + 0.0025 * np.log(max(C['f'], 35)), 0.0015)
    a3 = 0.009 - 0.001 * np.log(max(C['f'], 35))

    g2 = min(min(0.0065, a2), a3)

    gamma = np.zeros(ctx.rrup.shape)

    #gamma = -g1 * ctx.rrup + g2*(270.0 - np.clip(ctx.rrup, 270, None))
    # Gail mentioned in personal communication (email 13.06.2022) that now the modified F_gamma (see eq. 20-22 in modifications posted on Salck 12.06.2022) does not include gamma_2 term.
    gamma = -g1 * ctx.rrup
    return gamma

def _epistemic_adjustment_lower (C, ctx):
    # These are revised adjustments after Gail's post on slack 11th May 2022 and in her revised report.
    # The lower branch adjustment remains the same.
    #a = np.fmax(np.clip(0.5 - 0.1 * np.log(ctx.rrup), 0.2, None), - 0.25 + 0.1 * np.log(ctx.rrup))
    # The following variable is after Gail's modifications received on Slack 12.06.2022
    # The additional epistemic uncertainty for M>7 events was added in Gail's V8 modifications shared on 27.06.2022
    a = np.fmax(np.clip(0.6 - 0.13 * np.log(ctx.rrup), 0.3, None), - 0.25 + 0.12 * np.log(ctx.rrup))
    return np.clip(a, -np.inf, 0.5) + 0.15*np.clip(ctx.mag-7.0, 0, np.inf)

def _epistemic_adjustment_upper (C, ctx):
    # These are revised adjustments after Gail's post on slack 11th May 2022 and in her revised report.
    # Only the upper brach is modified.
    #a = np.fmax(np.clip(1.0 - 0.27 * np.log(ctx.rrup), 0.2, None), - 0.25 + 0.1 * np.log(ctx.rrup))
    # The following variable is after Modification from Gail recieved on Slack 12.06.2022
    # The additional epistemic uncertainty for M>7 events was added in Gail's V8 modifications shared on 27.06.2022
    a = np.fmax(np.clip(1.0 - 0.3 * np.log(ctx.rrup), 0.3, None), - 0.25 + 0.12 * np.log(ctx.rrup))
    return np.clip(a, -np.inf, 0.8) + 0.15*np.clip(ctx.mag-7.0, 0, np.inf)

def fs_SS14(C, pga_rock, ctx):
    # The site-term is implemnted from Seyhan and Stewart (2014; EQS).
    Vs_ref = 760.0
    flin = ctx.vs30 / Vs_ref
    flin[ctx.vs30 > C["Vc"]] = C["Vc"] / Vs_ref
    flin_func = C["c"]*np.log(flin)

    v_s = np.copy(ctx.vs30)
    v_s[ctx.vs30 > 760.] = 760.
    f_1 = 0.0
    f_3 = 0.1 * 981.0 #In Gail's model the GMM is in cm/s^2.
    # Nonlinear controlling parameter (equation 8)
    f_2 = C["f4"] * (np.exp(C["f5"] * (v_s - 360.)) - np.exp(C["f5"] * 400.))
    fnl = f_1 + f_2 * np.log((pga_rock + f_3)/f_3)
    return flin_func + fnl

def _get_pga_on_rock(suffix, C, ctx):
    pga_rock =  np.exp(_fmag(suffix, C, ctx.mag) + _fz_ha18(C, ctx) + _fgamma(suffix, C, ctx))
    return pga_rock

def get_stddevs(suffix, C):
    """
    Standard deviations given in COEFFS with suffix
    Between event standard deviations as Be_.
    Within event stdvs as We_.
    Total as sigma_.
    """
    intra_e_sigma = np.sqrt(C['We_' + suffix]**2 + C['phiSS']**2)
    return [C['sigma_' + suffix], C['Be_' + suffix], intra_e_sigma]


class Atkinson2022Crust(GMPE):
    """
    Implements Atkinson (2022) backbone model for New Zealand. For more info please refere to Gail Atkinson's NSHM report and linked revisions.
    """

    DEFINED_FOR_TECTONIC_REGION_TYPE = const.TRT.ACTIVE_SHALLOW_CRUST

    #: Supported intensity measure types are spectral acceleration,
    #: peak ground acceleration
    DEFINED_FOR_INTENSITY_MEASURE_TYPES = {PGA, SA}

    #: Supported intensity measure component is the RotD50
    DEFINED_FOR_INTENSITY_MEASURE_COMPONENT =const.IMC.RotD50

    DEFINED_FOR_STANDARD_DEVIATION_TYPES = {
        const.StdDev.TOTAL, const.StdDev.INTER_EVENT, const.StdDev.INTRA_EVENT}

    REQUIRES_DISTANCES = {'rrup'}

    REQUIRES_RUPTURE_PARAMETERS = {'mag'}

    REQUIRES_SITES_PARAMETERS = {'vs30'}

    # define the epistemic uncertainities : Central/Lower/Upper

    REQUIRES_ATTRIBUTES = {'epistemic'}

    # define constant parameters
    suffix = "crust"
    #kappa = 0.05
    #stress = 100

    def __init__(self, epistemic = 'Central', **kwargs):
        """
        Aditional parameter for epistemic central,
        lower and upper bounds.
        """
        super().__init__(epistemic=epistemic, **kwargs)
        self.epistemic = epistemic

    def compute(self, ctx:np.recarray, imts, mean, sig, tau, phi):
        # compute pga_rock
       C_PGA = self.COEFFS[PGA()]

       pga_rock = _get_pga_on_rock(self.suffix, C_PGA, ctx)

       for m, imt in enumerate(imts):
            C = self.COEFFS[imt]

            # compute mean
            mean[m] = (_fmag(self.suffix, C, ctx.mag)
                           + _fz_ha18(C, ctx)
                           + _fgamma(self.suffix, C, ctx)
                           + fs_SS14(C, pga_rock, ctx))

            mean[m] = mean[m] - np.log(981.0) # Convert the cm/s^2 to g.
            # In her email and slack post Gail mentioned that her upper and lower branches are as 1.28 times of the delta. So as to represent 10th and 90th percentile.
            # Consequently, the weights have also changed to 0.3, 0.4, 0.3.
            if self.epistemic == 'Lower':
                mean[m] = mean[m] - _epistemic_adjustment_lower(C, ctx)*1.28
            elif self.epistemic == 'Upper':
                mean[m] = mean[m] + _epistemic_adjustment_upper(C, ctx)*1.28
            else:
                mean[m] = mean[m]

            sig[m], tau[m], phi[m] = get_stddevs(self.suffix, C)

    # periods given by 1 / 10 ** COEFFS['f']
    COEFFS = CoeffsTable(sa_damping=5, table=open(Atk22_COEFFS).read())


class Atkinson2022SInter(Atkinson2022Crust):
    """
    Atkinson 2022 for Subduction Interface in NZ.
    """
    DEFINED_FOR_TECTONIC_REGION_TYPE = const.TRT.SUBDUCTION_INTERFACE

    # constant table suffix
    suffix = "inter"
    #stress = 100


class Atkinson2022SSlab(Atkinson2022Crust):
    """
    Atkinson (2022) for Subduction IntraSlab in NZ.
    """
    DEFINED_FOR_TECTONIC_REGION_TYPE = const.TRT.SUBDUCTION_INTRASLAB

    # constant table suffix
    suffix = "slab"
    #stress = 300
