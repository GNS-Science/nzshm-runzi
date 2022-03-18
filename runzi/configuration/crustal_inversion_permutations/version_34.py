import itertools
import copy
import json

def branch_permutations_generator_34(args, rupture_set_info):
    """
    Generate Uncertainty Constraint argument forms
    """

    bn_list = copy.deepcopy(args['b_and_n'])
    # bit of a no-no to change a list in a for loop, but since we're only altering the contents of the list items, we should be OK
    for i,a in enumerate(bn_list):
        bn_list[i]['string'] = str(a) #preserve origional string for TUI
        if not(a['enable_tvz_mfd']):
            bn_list[i]['N_sans'] = bn_list[i].pop('N')
            bn_list[i]['b_sans'] = bn_list[i].pop('b')
            bn_list[i]['N_tvz'] = 1.0
            bn_list[i]['b_tvz'] = 1.0
            


    for b_and_n in bn_list:
        for scaling_c in args['scaling_c']:
            for wts in args['constraint_wts']:
                for mag_ranges in args['mag_ranges']:
                    for slip_rate_factors in args['slip_rate_factors']:
                        for (_round, completion_energy, max_inversion_time,

                                #mfd_equality_weight, mfd_inequality_weight, slip_rate_weighting_type,
                                #slip_rate_weight, slip_uncertainty_scaling_factor,
                                #slip_rate_normalized_weight, slip_rate_unnormalized_weight,
                                reweight,
                                mfd_uncertainty_power, mfd_uncertainty_scalar,
                                slip_uncertainty_scaling_factor, slip_use_scaling,
                                enable_tvz_mfd,
                                mfd_mag_gt_5_sans, mfd_mag_gt_5_tvz,
                                mfd_b_value_sans, mfd_b_value_tvz, mfd_transition_mag,
                                max_mag_type,
                                min_mag_sans,min_mag_tvz,
                                max_mag_sans,max_mag_tvz,
                                selection_interval_secs, threads_per_selector, averaging_threads, averaging_interval_secs,
                                non_negativity_function, perturbation_function,
                                deformation_model,
                                scaling_relationship, scaling_recalc_mag,
                                paleo_rate_constraint,
                                paleo_probability_model, paleo_parent_rate_smoothness_constraint_weight,
                                scaling_c_val_dip_slip, scaling_c_val_strike_slip,
                                initial_solution_id,
                                cooling_schedule,
                                sans_slip_rate_factor,tvz_slip_rate_factor,
                                )\
                            in itertools.product(
                                args['rounds'], args['completion_energies'], args['max_inversion_times'],
                                [wts["reweight"]],
                                [wts["mfd_pow"]],[wts["mfd_unc_scalar"]],
                                [wts["sr_scaling"]], [wts["sr_use_scaling"]],
                                [b_and_n['enable_tvz_mfd']],
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
                                args['paleo_rate_constraints'],
                                args['paleo_probability_models'], [wts['paleo_smoothing']],
                                #args['scaling_c_val_dip_slips'], args['scaling_c_val_strike_slips'],
                                [scaling_c['dip']], [scaling_c['strike']],
                                args.get('initial_solution_ids', [None,]),
                                args['cooling_schedules'],
                                [slip_rate_factors['slip_factor_sans']],[slip_rate_factors['slip_factor_tvz']]
                                ):
                                    task_arguments = dict(
                                        round = _round,
                                        config_type = 'crustal',
                                        deformation_model=deformation_model,
                                        rupture_set_file_id=rupture_set_info['id'],
                                        rupture_set=rupture_set_info['filepath'],
                                        completion_energy=completion_energy,
                                        max_inversion_time=max_inversion_time,
                                        #mfd_equality_weight=mfd_equality_weight,
                                        #mfd_inequality_weight=mfd_inequality_weight,

                                        #mfd_uncertainty_weight=mfd_uncertainty_weight,
                                        mfd_uncertainty_power=mfd_uncertainty_power,
                                        mfd_uncertainty_scalar=mfd_uncertainty_scalar,

                                        max_jump_distances=rupture_set_info['info']['max_jump_distance'],

                                        #slip_rate_weighting_type=slip_rate_weighting_type,
                                        #slip_rate_weight=slip_rate_weight,

                                        #slip_uncertainty_weight=slip_uncertainty_weight,
                                        slip_uncertainty_scaling_factor=slip_uncertainty_scaling_factor,
                                        slip_use_scaling=slip_use_scaling,

                                        enable_tvz_mfd=enable_tvz_mfd,

                                        #slip_rate_normalized_weight=slip_rate_normalized_weight,
                                        #slip_rate_unnormalized_weight=slip_rate_unnormalized_weight,

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
                                        sans_slip_rate_factor=sans_slip_rate_factor,
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
                                        #paleo_rate_constraint_weight=paleo_rate_constraint_weight,
                                        paleo_rate_constraint=paleo_rate_constraint,
                                        paleo_probability_model=paleo_probability_model,
                                        paleo_parent_rate_smoothness_constraint_weight=paleo_parent_rate_smoothness_constraint_weight,

                                        #new reweight
                                        reweight=reweight,

                                        scaling_c_val_dip_slip=scaling_c_val_dip_slip,
                                        scaling_c_val_strike_slip=scaling_c_val_strike_slip,
                                        initial_solution_id=initial_solution_id,

                                        # Composite args (branch sets)
                                        # are required for ToshiUI filtering
                                        b_and_n = str(b_and_n['string']),
                                        scaling_c = str(scaling_c),
                                        constraint_wts = str(wts),
                                        mag_ranges = str(mag_ranges),
                                        slip_rate_factors = str(slip_rate_factors)
                                        )

                                    yield task_arguments

if __name__ == '__main__':

    #1840-2020 options
    b_and_n = [
        {"tag": "1840-2020 med","enable_tvz_mfd":True, "b_sans": 0.9, "N_sans": 4.2, "b_tvz": 1.2, "N_tvz": 0.7},
        {"tag": "1840-2020 low","enable_tvz_mfd":False, "b": 0.8, "N": 2.6}
    ]
    scaling_c = [#dict(tag='low', dip=4.1, strike=4.1),
            #dict(tag='med', dip=4.2, strike=4.2),
            dict(tag='high', dip=4.3, strike=4.3)]

    # #these are used for BOTH, NORMALIZED and UNNORMALIZED
    # constraint_wts = [
    #     #{"tag": "mfd weak", "mfd_eq": "1e4", "mfd_ineq": "1e4", "sr_norm": "1e3", "sr_unnorm": "1e5", "paleo_rate": "1e3", "paleo_smoothing": "1e4" },
    #     {"tag": "mfd even", "mfd_eq": "1e4", "mfd_ineq": "1e4", "sr_norm": "1e2", "sr_unnorm": "1e4", "paleo_rate": "1e2", "paleo_smoothing": "1e4" }
    # ]

    constraint_wts = [
        {"tag": "UCT M(0.25,0.4)_S(0,0)_Psmth(3)",     "reweight": True, "mfd_pow": 0.25, "mfd_unc_scalar": 0.4, "sr_scaling": 0, "sr_use_scaling": 0,"paleo_smoothing": 1e3},
        {"tag": "UCT M(0.5,0.6)_S(3,0,0)_Psmth(3,3)",  "reweight": True, "mfd_pow": 0.5, "mfd_unc_scalar": 0.6, "sr_scaling":1, "sr_use_scaling": 1,"paleo_smoothing": 1e3 }
    ]

    mag_ranges = [
        #{"min_mag_sans":7.0, "min_mag_tvz":6.5, "max_mag_sans":9.0, "max_mag_tvz":8.0},
        {"min_mag_sans":7.5, "min_mag_tvz":7.1, "max_mag_sans":9.1, "max_mag_tvz":8.5}
    ]

    slip_rate_factors =  [
        {"tag": "Sans 0.9 TVZ 0.7", "slip_factor_sans":0.9, "slip_factor_tvz":0.7}       
    ]

    args = dict(
        rounds = [str(x) for x in range(1)],
        completion_energies = ['0.0'],
        max_inversion_times = ['3', '4'],

        deformation_models = ['FAULT_MODEL',], # GEOD_NO_PRIOR_UNISTD_2010_RmlsZTo4NTkuMDM2Z2Rw, 'GEOD_NO_PRIOR_UNISTD_D90_RmlsZTozMDMuMEJCOVVY',

        initial_solution_ids = ["", "SOME"],

        tvz_slip_rate_factors = [1, 0.9, 0.8],

        scaling_c = scaling_c,

        b_and_n = b_and_n,

        constraint_wts = constraint_wts,

        mfd_transition_mags = [7.85],

        mag_ranges = mag_ranges,

        slip_rate_factors = slip_rate_factors,

        #max_mag_types = ["NONE", "FILTER_RUPSET", "MANIPULATE_MFD"],
        max_mag_types = ["FILTER_RUPSET"],

        #slip_rate_weighting_types = ['BOTH'], #NORMALIZED_BY_SLIP_RATE', UNCERTAINTY_ADJUSTED', BOTH

        #these are used for UNCERTAINTY_ADJUSTED
        #slip_rate_weights = [None],# 1e5, 1e4, 1e3, 1e2]
        #slip_uncertainty_scaling_factors = [None],#2,]

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
    #print( json.dumps(args))

    # assert 0
    args_list = []
    for key, value in args.items():
        args_list.append(dict(k=key, v=value))

    #print(args_list)
    print(args['b_and_n'])
    print('\n')
    print('-----------')
    print('\n')

    rupture_set_info = dict(id=0, filepath='')
    count = 0
    for p in branch_permutations_generator_34(args, rupture_set_info):
        #print(p)
        for k,v in p.items():
            print(k,v)
        print('=================')
        count +=1

    print()
    print(f"perms: {count}")
