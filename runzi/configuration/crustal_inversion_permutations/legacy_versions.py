import itertools
import json

def all_permutations_generator(args, rupture_set_info):

    for (_round, completion_energy, max_inversion_time,
            mfd_equality_weight, mfd_inequality_weight, slip_rate_weighting_type,
            slip_rate_weight, slip_uncertainty_scaling_factor,
            slip_rate_normalized_weight, slip_rate_unnormalized_weight,
            mfd_mag_gt_5_sans, mfd_mag_gt_5_tvz,
            mfd_b_value_sans, mfd_b_value_tvz, mfd_transition_mag,
            seismogenic_min_mag,
            selection_interval_secs, threads_per_selector, averaging_threads, averaging_interval_secs,
            non_negativity_function, perturbation_function,
            deformation_model,
            scaling_relationship, scaling_recalc_mag,
            paleo_rate_constraint_weight, paleo_rate_constraint,
            paleo_probability_model, paleo_parent_rate_smoothness_constraint_weight,
            scaling_c_val_dip_slip, scaling_c_val_strike_slip,
            initial_solution_id
            )\
        in itertools.product(
            args['rounds'], args['completion_energies'], args['max_inversion_times'],
            args['mfd_equality_weights'], args['mfd_inequality_weights'], args['slip_rate_weighting_types'],
            args['slip_rate_weights'], args['slip_uncertainty_scaling_factors'],
            args['slip_rate_normalized_weights'],  args['slip_rate_unnormalized_weights'],
            args['mfd_mag_gt_5_sans'], args['mfd_mag_gt_5_tvz'],
            args['mfd_b_values_sans'], args['mfd_b_values_tvz'], args['mfd_transition_mags'],
            args['seismogenic_min_mags'],
            args['selection_interval_secs'], args['threads_per_selector'], args['averaging_threads'], args['averaging_interval_secs'],
            args['non_negativity_function'], args['perturbation_function'],
            args['deformation_models'],
            args['scaling_relationships'], args['scaling_recalc_mags'],
            args['paleo_rate_constraint_weights'], args['paleo_rate_constraints'],
            args['paleo_probability_models'], args['paleo_parent_rate_smoothness_constraint_weights'],
            args['scaling_c_val_dip_slips'], args['scaling_c_val_strike_slips'],
            args.get('initial_solution_ids', [None,])
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
                seismogenic_min_mag=seismogenic_min_mag,
                mfd_mag_gt_5_sans=mfd_mag_gt_5_sans,
                mfd_mag_gt_5_tvz=mfd_mag_gt_5_tvz,
                mfd_b_value_sans=mfd_b_value_sans,
                mfd_b_value_tvz=mfd_b_value_tvz,
                mfd_transition_mag=mfd_transition_mag,

                #New config arguments for Simulated Annealing ...
                selection_interval_secs=selection_interval_secs,
                threads_per_selector=threads_per_selector,
                averaging_threads=averaging_threads,
                averaging_interval_secs=averaging_interval_secs,
                non_negativity_function=non_negativity_function,
                perturbation_function=perturbation_function,

                scaling_relationship=scaling_relationship,
                scaling_recalc_mag=scaling_recalc_mag,

                #New Paleo Args...
                paleo_rate_constraint_weight=paleo_rate_constraint_weight,
                paleo_rate_constraint=paleo_rate_constraint,
                paleo_probability_model=paleo_probability_model,
                paleo_parent_rate_smoothness_constraint_weight=paleo_parent_rate_smoothness_constraint_weight,

                scaling_c_val_dip_slip=scaling_c_val_dip_slip,
                scaling_c_val_strike_slip=scaling_c_val_strike_slip,
                initial_solution_id=initial_solution_id
                )

            return task_arguments


def branch_permutations_generator(args, rupture_set_info):
    for (_round, completion_energy, max_inversion_time,
            mfd_equality_weight, mfd_inequality_weight, slip_rate_weighting_type,
            slip_rate_weight, slip_uncertainty_scaling_factor,
            slip_rate_normalized_weight, slip_rate_unnormalized_weight,
            mfd_mag_gt_5_sans, mfd_mag_gt_5_tvz,
            mfd_b_value_sans, mfd_b_value_tvz, mfd_transition_mag,
            seismogenic_min_mag,
            selection_interval_secs, threads_per_selector, averaging_threads, averaging_interval_secs,
            non_negativity_function, perturbation_function,
            deformation_model,
            scaling_relationship, scaling_recalc_mag,
            paleo_rate_constraint_weight, paleo_rate_constraint,
            paleo_probability_model, paleo_parent_rate_smoothness_constraint_weight,
            scaling_c_val_dip_slip, scaling_c_val_strike_slip,
            initial_solution_id
            )\
            in itertools.product(
                args['rounds'], args['completion_energies'], args['max_inversion_times'],
                args['mfd_equality_weights'], args['mfd_inequality_weights'], args['slip_rate_weighting_types'],
                args['slip_rate_weights'], args['slip_uncertainty_scaling_factors'],
                args['slip_rate_normalized_weights'],  args['slip_rate_unnormalized_weights'],
                #args['mfd_mag_gt_5_sans'], args['mfd_mag_gt_5_tvz'],
                [b_and_n['N_sans']], [b_and_n['N_tvz']],
                #args['mfd_b_values_sans'], args['mfd_b_values_tvz'],
                [b_and_n['b_sans']], [b_and_n['b_tvz']],
                args['mfd_transition_mags'],
                args['seismogenic_min_mags'],
                args['selection_interval_secs'], args['threads_per_selector'], args['averaging_threads'], args['averaging_interval_secs'],
                args['non_negativity_function'], args['perturbation_function'],
                args['deformation_models'],
                args['scaling_relationships'], args['scaling_recalc_mags'],
                args['paleo_rate_constraint_weights'], args['paleo_rate_constraints'],
                args['paleo_probability_models'], args['paleo_parent_rate_smoothness_constraint_weights'],
                #args['scaling_c_val_dip_slips'], args['scaling_c_val_strike_slips'],
                [scaling_c['dip']], [scaling_c['strike']],
                args.get('initial_solution_ids', [None,])
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
                    seismogenic_min_mag=seismogenic_min_mag,
                    mfd_mag_gt_5_sans=mfd_mag_gt_5_sans,
                    mfd_mag_gt_5_tvz=mfd_mag_gt_5_tvz,
                    mfd_b_value_sans=mfd_b_value_sans,
                    mfd_b_value_tvz=mfd_b_value_tvz,
                    mfd_transition_mag=mfd_transition_mag,

                    #New config arguments for Simulated Annealing ...
                    selection_interval_secs=selection_interval_secs,
                    threads_per_selector=threads_per_selector,
                    averaging_threads=averaging_threads,
                    averaging_interval_secs=averaging_interval_secs,
                    non_negativity_function=non_negativity_function,
                    perturbation_function=perturbation_function,

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
                    scaling_c = str(scaling_c)
                    )

                yield task_arguments

def branch_permutations_generator_21(args, rupture_set_info):

    for b_and_n in args['b_and_n']:
        for scaling_c in args['scaling_c']:
            for wts in args['constraint_wts']:
                for (_round, completion_energy, max_inversion_time,
                        mfd_equality_weight, mfd_inequality_weight, slip_rate_weighting_type,
                        slip_rate_weight, slip_uncertainty_scaling_factor,
                        slip_rate_normalized_weight, slip_rate_unnormalized_weight,
                        mfd_mag_gt_5_sans, mfd_mag_gt_5_tvz,
                        mfd_b_value_sans, mfd_b_value_tvz, mfd_transition_mag,
                        seismogenic_min_mag,
                        selection_interval_secs, threads_per_selector, averaging_threads, averaging_interval_secs,
                        non_negativity_function, perturbation_function,
                        deformation_model,
                        scaling_relationship, scaling_recalc_mag,
                        paleo_rate_constraint_weight, paleo_rate_constraint,
                        paleo_probability_model, paleo_parent_rate_smoothness_constraint_weight,
                        scaling_c_val_dip_slip, scaling_c_val_strike_slip,
                        initial_solution_id
                        )\
                    in itertools.product(
                        args['rounds'], args['completion_energies'], args['max_inversion_times'],
                        [wts['mfd_eq']], [wts['mfd_ineq']], args['slip_rate_weighting_types'],
                        args['slip_rate_weights'], args['slip_uncertainty_scaling_factors'],
                        [wts['sr_norm']],  [wts['sr_unnorm']],
                        [b_and_n['N_sans']], [b_and_n['N_tvz']],
                        [b_and_n['b_sans']], [b_and_n['b_tvz']],
                        args['mfd_transition_mags'],
                        args['seismogenic_min_mags'],
                        args['selection_interval_secs'], args['threads_per_selector'], args['averaging_threads'], args['averaging_interval_secs'],
                        args['non_negativity_function'], args['perturbation_function'],
                        args['deformation_models'],
                        args['scaling_relationships'], args['scaling_recalc_mags'],
                        [wts['paleo_rate']], args['paleo_rate_constraints'],
                        args['paleo_probability_models'], [wts['paleo_smoothing']],
                        #args['scaling_c_val_dip_slips'], args['scaling_c_val_strike_slips'],
                        [scaling_c['dip']], [scaling_c['strike']],
                        args.get('initial_solution_ids', [None,])
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
                                seismogenic_min_mag=seismogenic_min_mag,
                                mfd_mag_gt_5_sans=mfd_mag_gt_5_sans,
                                mfd_mag_gt_5_tvz=mfd_mag_gt_5_tvz,
                                mfd_b_value_sans=mfd_b_value_sans,
                                mfd_b_value_tvz=mfd_b_value_tvz,
                                mfd_transition_mag=mfd_transition_mag,

                                #New config arguments for Simulated Annealing ...
                                selection_interval_secs=selection_interval_secs,
                                threads_per_selector=threads_per_selector,
                                averaging_threads=averaging_threads,
                                averaging_interval_secs=averaging_interval_secs,
                                non_negativity_function=non_negativity_function,
                                perturbation_function=perturbation_function,

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
                                constraint_wt = str(wts)
                                )

                            yield task_arguments

def branch_permutations_generator_22(args, rupture_set_info):

    for b_and_n in args['b_and_n']:
        for scaling_c in args['scaling_c']:
            for wts in args['constraint_wts']:
                for (_round, completion_energy, max_inversion_time,
                        mfd_equality_weight, mfd_inequality_weight, slip_rate_weighting_type,
                        slip_rate_weight, slip_uncertainty_scaling_factor,
                        slip_rate_normalized_weight, slip_rate_unnormalized_weight,
                        mfd_mag_gt_5_sans, mfd_mag_gt_5_tvz,
                        mfd_b_value_sans, mfd_b_value_tvz, mfd_transition_mag,
                        seismogenic_min_mag,
                        selection_interval_secs, threads_per_selector, averaging_threads, averaging_interval_secs,
                        non_negativity_function, perturbation_function,
                        deformation_model,
                        scaling_relationship, scaling_recalc_mag,
                        paleo_rate_constraint_weight, paleo_rate_constraint,
                        paleo_probability_model, paleo_parent_rate_smoothness_constraint_weight,
                        scaling_c_val_dip_slip, scaling_c_val_strike_slip,
                        initial_solution_id,
                        cooling_schedule
                        )\
                    in itertools.product(
                        args['rounds'], args['completion_energies'], args['max_inversion_times'],
                        [wts['mfd_eq']], [wts['mfd_ineq']], args['slip_rate_weighting_types'],
                        args['slip_rate_weights'], args['slip_uncertainty_scaling_factors'],
                        [wts['sr_norm']],  [wts['sr_unnorm']],
                        [b_and_n['N_sans']], [b_and_n['N_tvz']],
                        [b_and_n['b_sans']], [b_and_n['b_tvz']],
                        args['mfd_transition_mags'],
                        args['seismogenic_min_mags'],
                        args['selection_interval_secs'], args['threads_per_selector'], args['averaging_threads'], args['averaging_interval_secs'],
                        args['non_negativity_function'], args['perturbation_function'],
                        args['deformation_models'],
                        args['scaling_relationships'], args['scaling_recalc_mags'],
                        [wts['paleo_rate']], args['paleo_rate_constraints'],
                        args['paleo_probability_models'], [wts['paleo_smoothing']],
                        #args['scaling_c_val_dip_slips'], args['scaling_c_val_strike_slips'],
                        [scaling_c['dip']], [scaling_c['strike']],
                        args.get('initial_solution_ids', [None,]),
                        args['cooling_schedules']
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
                                seismogenic_min_mag=seismogenic_min_mag,
                                mfd_mag_gt_5_sans=mfd_mag_gt_5_sans,
                                mfd_mag_gt_5_tvz=mfd_mag_gt_5_tvz,
                                mfd_b_value_sans=mfd_b_value_sans,
                                mfd_b_value_tvz=mfd_b_value_tvz,
                                mfd_transition_mag=mfd_transition_mag,

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
                                constraint_wts = str(wts)
                                )

                            yield task_arguments

def branch_permutations_generator_23(args, rupture_set_info):

    for b_and_n in args['b_and_n']:
        for scaling_c in args['scaling_c']:
            for wts in args['constraint_wts']:
                for (_round, completion_energy, max_inversion_time,
                        mfd_equality_weight, mfd_inequality_weight, slip_rate_weighting_type,
                        slip_rate_weight, slip_uncertainty_scaling_factor,
                        slip_rate_normalized_weight, slip_rate_unnormalized_weight,
                        mfd_mag_gt_5_sans, mfd_mag_gt_5_tvz,
                        mfd_b_value_sans, mfd_b_value_tvz, mfd_transition_mag,
                        seismogenic_min_mag,
                        selection_interval_secs, threads_per_selector, averaging_threads, averaging_interval_secs,
                        non_negativity_function, perturbation_function,
                        deformation_model,
                        scaling_relationship, scaling_recalc_mag,
                        paleo_rate_constraint_weight, paleo_rate_constraint,
                        paleo_probability_model, paleo_parent_rate_smoothness_constraint_weight,
                        scaling_c_val_dip_slip, scaling_c_val_strike_slip,
                        initial_solution_id,
                        cooling_schedule
                        )\
                    in itertools.product(
                        args['rounds'], args['completion_energies'], args['max_inversion_times'],
                        [wts['mfd_eq']], [wts['mfd_ineq']], args['slip_rate_weighting_types'],
                        args['slip_rate_weights'], args['slip_uncertainty_scaling_factors'],
                        [wts['sr_norm']],  [wts['sr_unnorm']],
                        [b_and_n['N_sans']], [b_and_n['N_tvz']],
                        [b_and_n['b_sans']], [b_and_n['b_tvz']],
                        args['mfd_transition_mags'],
                        args['seismogenic_min_mags'],
                        args['selection_interval_secs'], args['threads_per_selector'], args['averaging_threads'], args['averaging_interval_secs'],
                        args['non_negativity_function'], args['perturbation_function'],
                        args['deformation_models'],
                        args['scaling_relationships'], args['scaling_recalc_mags'],
                        [wts['paleo_rate']], args['paleo_rate_constraints'],
                        args['paleo_probability_models'], [wts['paleo_smoothing']],
                        #args['scaling_c_val_dip_slips'], args['scaling_c_val_strike_slips'],
                        [scaling_c['dip']], [scaling_c['strike']],
                        args.get('initial_solution_ids', [None,]),
                        args['cooling_schedules']
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
                                seismogenic_min_mag_tvz=seismogenic_min_mag['TVZ'],
                                seismogenic_min_mag_sans=seismogenic_min_mag['sansTVZ'],
                                mfd_mag_gt_5_sans=mfd_mag_gt_5_sans,
                                mfd_mag_gt_5_tvz=mfd_mag_gt_5_tvz,
                                mfd_b_value_sans=mfd_b_value_sans,
                                mfd_b_value_tvz=mfd_b_value_tvz,
                                mfd_transition_mag=mfd_transition_mag,

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
                                constraint_wts = str(wts)
                                )

                            yield task_arguments

def branch_permutations_generator_24(args, rupture_set_info):

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
                            cooling_schedule
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
                            args['cooling_schedules']
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
