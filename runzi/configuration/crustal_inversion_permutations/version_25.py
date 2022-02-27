import itertools
import json

def branch_permutations_generator_25(args, rupture_set_info):

    for b_and_n in args['b_and_n']:
        for scaling_c in args['scaling_c']:
            for wts in args['constraint_wts']:
                for mag_ranges in args['mag_ranges']:
                    for (_round, completion_energy, max_inversion_time,
                            mfd_equality_weight, mfd_inequality_weight, slip_rate_weighting_type,
                            slip_rate_weight, slip_uncertainty_scaling_factor,
                            slip_rate_normalized_weight, slip_rate_unnormalized_weight,
                            mfd_mag_gt_5_sans, mfd_mag_gt_5_tvz,
                            mfd_b_value_sans, mfd_b_value_tvz, mfd_transition_mag,
                            max_mag_type,
                            min_mag_sans,min_mag_tvz,
                            max_mag_sans,max_mag_tvz,
                            selection_interval_secs, threads_per_selector, averaging_threads, averaging_interval_secs,
                            non_negativity_function, perturbation_function,
                            deformation_model,
                            scaling_relationship, scaling_recalc_mag,
                            paleo_rate_constraint_weight, paleo_rate_constraint,
                            paleo_probability_model, paleo_parent_rate_smoothness_constraint_weight,
                            scaling_c_val_dip_slip, scaling_c_val_strike_slip,
                            initial_solution_id,
                            cooling_schedule,
                            tvz_slip_rate_factor,
                            )\
                        in itertools.product(
                            args['rounds'], args['completion_energies'], args['max_inversion_times'],
                            [wts['mfd_eq']], [wts['mfd_ineq']], args['slip_rate_weighting_types'],
                            args['slip_rate_weights'], args['slip_uncertainty_scaling_factors'],
                            [wts['sr_norm']],  [wts['sr_unnorm']],
                            [b_and_n['N_sans']], [b_and_n['N_tvz']],
                            [b_and_n['b_sans']], [b_and_n['b_tvz']],
                            args['mfd_transition_mags'],
                            args['max_mag_types'],
                            [mag_ranges['min_mag_sans']], [mag_ranges['min_mag_tvz']],
                            [mag_ranges['max_mag_sans']], [mag_ranges['max_mag_tvz']],
                            args['selection_interval_secs'], args['threads_per_selector'], args['averaging_threads'], args['averaging_interval_secs'],
                            args['non_negativity_function'], args['perturbation_function'],
                            args['deformation_models'],
                            args['scaling_relationships'], args['scaling_recalc_mags'],
                            [wts['paleo_rate']], args['paleo_rate_constraints'],
                            args['paleo_probability_models'], [wts['paleo_smoothing']],
                            #args['scaling_c_val_dip_slips'], args['scaling_c_val_strike_slips'],
                            [scaling_c['dip']], [scaling_c['strike']],
                            args.get('initial_solution_ids', [None,]),
                            args['cooling_schedules'],
                            args['tvz_slip_rate_factors']
                            ):

                                task_arguments = dict(
                                    round = _round,
                                    config_type = 'crustal',
                                    deformation_model=deformation_model,
                                    rupture_set_file_id=rupture_set_info['id'],
                                    rupture_set=rupture_set_info['filepath'],
                                    completion_energy=completion_energy,
                                    max_inversion_time=max_inversion_time,
                                    mfd_equality_weight=mfd_equality_weight,
                                    mfd_inequality_weight=mfd_inequality_weight,
                                    slip_rate_weighting_type=slip_rate_weighting_type,
                                    slip_rate_weight=slip_rate_weight,
                                    slip_uncertainty_scaling_factor=slip_uncertainty_scaling_factor,
                                    slip_rate_normalized_weight=slip_rate_normalized_weight,
                                    slip_rate_unnormalized_weight=slip_rate_unnormalized_weight,
                                    max_mag_type=max_mag_type,
                                    min_mag_sans=min_mag_sans,
                                    min_mag_tvz=min_mag_tvz,
                                    max_mag_sans=max_mag_sans,
                                    max_mag_tvz=max_mag_tvz,
                                    mfd_mag_gt_5_sans=mfd_mag_gt_5_sans,
                                    mfd_mag_gt_5_tvz=mfd_mag_gt_5_tvz,
                                    mfd_b_value_sans=mfd_b_value_sans,
                                    mfd_b_value_tvz=mfd_b_value_tvz,
                                    mfd_transition_mag=mfd_transition_mag,
                                    tvz_slip_rate_factor=tvz_slip_rate_factor,

                                    #New config arguments for Simulated Annealing ...
                                    selection_interval_secs=selection_interval_secs,
                                    threads_per_selector=threads_per_selector,
                                    averaging_threads=averaging_threads,
                                    averaging_interval_secs=averaging_interval_secs,
                                    non_negativity_function=non_negativity_function,
                                    perturbation_function=perturbation_function,
                                    cooling_schedule=cooling_schedule,

                                    scaling_relationship=scaling_relationship,
                                    scaling_recalc_mag=scaling_recalc_mag,

                                    #New Paleo Args...
                                    paleo_rate_constraint_weight=paleo_rate_constraint_weight,
                                    paleo_rate_constraint=paleo_rate_constraint,
                                    paleo_probability_model=paleo_probability_model,
                                    paleo_parent_rate_smoothness_constraint_weight=paleo_parent_rate_smoothness_constraint_weight,

                                    scaling_c_val_dip_slip=scaling_c_val_dip_slip,
                                    scaling_c_val_strike_slip=scaling_c_val_strike_slip,
                                    initial_solution_id=initial_solution_id,

                                    # Composite args (branch sets)
                                    # are required for ToshiUI filtering
                                    b_and_n = str(b_and_n),
                                    scaling_c = str(scaling_c),
                                    constraint_wts = str(wts),
                                    mag_ranges = str(mag_ranges)
                                    )

                                yield task_arguments

if __name__ == '__main__':

    #1840-2020 options
    b_and_n = [
        {"tag": "1840-2020 med", "b_sans": 0.9, "N_sans": 4.2, "b_tvz": 1.2, "N_tvz": 0.7},
        {"tag": "1840-2020 low", "b_sans": 0.8, "N_sans": 2.6, "b_tvz": 0.98, "N_tvz": 0.4},
    ]
    scaling_c = [#dict(tag='low', dip=4.1, strike=4.1),
            dict(tag='med', dip=4.2, strike=4.2),
            dict(tag='high', dip=4.3, strike=4.3)]

    #these are used for BOTH, NORMALIZED and UNNORMALIZED
    constraint_wts = [
        #{"tag": "mfd weak", "mfd_eq": "1e4", "mfd_ineq": "1e4", "sr_norm": "1e3", "sr_unnorm": "1e5", "paleo_rate": "1e3", "paleo_smoothing": "1e4" },
        {"tag": "mfd even", "mfd_eq": "1e4", "mfd_ineq": "1e4", "sr_norm": "1e2", "sr_unnorm": "1e4", "paleo_rate": "1e2", "paleo_smoothing": "1e4" }
    ]

    mag_ranges = [
        {"min_mag_sans":7.0, "min_mag_tvz":6.5, "max_mag_sans":9.0, "max_mag_tvz":8.0},
        {"min_mag_sans":7.5, "min_mag_tvz":7.1, "max_mag_sans":9.1, "max_mag_tvz":8.5}
    ]

    args = dict(
        rounds = [str(x) for x in range(1)],
        completion_energies = ['0.0'],
        max_inversion_times = ['3', '4', '5'],

        deformation_models = ['FAULT_MODEL',], # GEOD_NO_PRIOR_UNISTD_2010_RmlsZTo4NTkuMDM2Z2Rw, 'GEOD_NO_PRIOR_UNISTD_D90_RmlsZTozMDMuMEJCOVVY',

        initial_solution_ids = ["", "SOME"],

        tvz_slip_rate_factors = [1, 0.9, 0.8],

        scaling_c = scaling_c,

        b_and_n = b_and_n,

        constraint_wts = constraint_wts,

        mfd_transition_mags = [7.85],

        mag_ranges = mag_ranges,

        #max_mag_types = ["NONE", "FILTER_RUPSET", "MANIPULATE_MFD"],
        max_mag_types = ["FILTER_RUPSET"],

        slip_rate_weighting_types = ['BOTH'], #NORMALIZED_BY_SLIP_RATE', UNCERTAINTY_ADJUSTED', BOTH

        #these are used for UNCERTAINTY_ADJUSTED
        slip_rate_weights = [None],# 1e5, 1e4, 1e3, 1e2]
        slip_uncertainty_scaling_factors = [None],#2,]

        #New modular inversion configurations
        selection_interval_secs = ['1'],
        threads_per_selector = ['4'],
        averaging_threads = ['4'],
        averaging_interval_secs = ['30'],

        non_negativity_function = ['TRY_ZERO_RATES_OFTEN'], # TRY_ZERO_RATES_OFTEN,  LIMIT_ZERO_RATES, PREVENT_ZERO_RATES
        perturbation_function = ['EXPONENTIAL_SCALE'], # UNIFORM_NO_TEMP_DEPENDENCE, EXPONENTIAL_SCALE;

        cooling_schedules =["CLASSICAL_SA",], # "FAST_SA"

        #Scaling Relationships
        scaling_relationships=['SIMPLE_CRUSTAL'], #'SMPL_NZ_INT_LW', 'SMPL_NZ_INT_UP'],
        scaling_recalc_mags=['True'],

        #Paleo
        paleo_rate_constraints = ["GEOLOGIC_SLIP_1_0"],
        paleo_probability_models = ["UCERF3_PLUS_PT5"],
        )
    print( json.dumps(args))

    # assert 0
    args_list = []
    for key, value in args.items():
        args_list.append(dict(k=key, v=value))

    print(args_list)

    rupture_set_info = dict(id=0, filepath='')
    count = 0
    for p in branch_permutations_generator_25(args, rupture_set_info):
        print(p)
        #assert 0
        count +=1

    print()
    print(f"perms: {count}")
