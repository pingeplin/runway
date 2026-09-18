# Doc quality — deterministic spec metrics (stage 12)

Oracle = `def`/`class` symbols the dataset mask removed. Recall = share the spec names in code context; effective recall excludes symbols the spec fences off. Fenced = oracle symbols under an out-of-scope heading or in a do-not-touch sentence (heuristic; stage 13 has the LLM listing). Grounding = share of named files/identifiers that exist in the masked workspace or are oracle symbols. Smells = hedges, vague terms, escape and open-ended clauses, absolutes per 100 prose words (word lists; diagnostic only).

| label | task | lines | oracle syms | symbol recall | effective recall | file recall | fenced∩oracle | grounding | smells/100w |
|---|---|---|---|---|---|---|---|---|---|
| b41 | `test_basic_rgb` | 753 | 9 | 0.78 | 0.78 | 1.00 | 0 | — | 0.37 |
| b41 | `test_containers` | 938 | 16 | 0.75 | 0.75 | 1.00 | 0 | — | 0.43 |
| b41 | `test_lombscargle_multiband` | 637 | 18 | 0.50 | 0.50 | 0.73 | 0 | — | 0.29 |
| b41 | `test_table` | 258 | 37 | 0.65 | 0.38 | 0.50 | 10 ['_iterable_helper', '_make_masked_array', '_parse_binary', '_resize_strategy', '_write_binary', 'binparse', 'bitarray_to_bool', 'bool_to_bitarray', 'concatenate', 'data'] | — | 0.42 |
| b41 | `test_vo` | 587 | 33 | 0.33 | 0.33 | 0.18 | 0 | — | 0.13 |
| bnew | `test_basic_rgb` | 518 | 9 | 0.78 | 0.22 | 1.00 | 5 ['__call__', '_prepare', '_process_values', 'apply_mappings', 'get_limits'] | — | 0.13 |
| bnew | `test_containers` | 514 | 16 | 0.75 | 0.50 | 1.00 | 4 ['__array_function__', 'broadcast_arrays', 'concatenate', 'empty_like'] | — | 0.24 |
| bnew | `test_lombscargle_multiband` | 497 | 18 | 0.39 | 0.00 | 0.47 | 7 ['__array__', '_check_leapsec', 'broadcast_arrays', 'get_unit', 'has_units', 'quantity_day_frac', 'strip_units'] | — | 0.08 |
| bnew | `test_table` | 509 | 37 | 0.57 | 0.11 | 0.50 | 17 ['__init__', '_as_quantity', '_binoutput_fixed', '_binoutput_var', '_binparse_fixed', '_binparse_var', '_iterable_helper', '_make_masked_array', '_parse_length', '_quantities2arrays', '_write_length', 'add_column', 'bitarray_to_bool', 'bool_to_bitarray', 'concatenate', 'data', 'to_table'] | — | 0.22 |
| bnew | `test_vo` | 676 | 33 | 0.33 | 0.18 | 0.18 | 5 ['get_first_table', 'get_ref', 'iter_values', 'reference_frames', 'to_table'] | — | 0.22 |

## Per-label means

| label | n | symbol recall | effective recall | file recall | fenced∩oracle (sum) | grounding | smells/100w |
|---|---|---|---|---|---|---|---|
| b41 | 5 | 0.60 | 0.55 | 0.68 | 10 | — | 0.33 |
| bnew | 5 | 0.56 | 0.20 | 0.63 | 38 | — | 0.18 |

## Misses and ungrounded names

- **b41 / `test_basic_rgb`** — missed: ['_convert_images_to_float', '_convert_images_to_uint']; ungrounded: none
- **b41 / `test_containers`** — missed: ['_get_distribution_cls', '_result_as_distribution', 'get_n_samples', 'is_distribution']; ungrounded: none
- **b41 / `test_lombscargle_multiband`** — missed: ['__str__', '_check_required_columns', '_init_from_ndarray', 'as_scalar_or_list_str', 'bitceil', 'extirpolate', 'format_string', 'str_kwargs', 'trig_sum']; ungrounded: none
- **b41 / `test_table`** — missed: ['_add_fieldref', '_add_paramref', '_all_matching_dtype', '_get_binary_data_stream', '_invalid_unit_error_message', '_is_null', '_splitter_lax', 'careful_read', 'check_anyuri', 'entries', 'iter_values', 'numpy_to_votable_dtype', 'yes_no']; ungrounded: none
- **b41 / `test_vo`** — missed: ['__set__', '_base_repr_', '_convert_to_fd_or_read_function', '_decompose_to_known_units', '_did_you_mean_units', '_format_message', '_init_from_ndarray', '_invalid_unit_error_message', '_parse_minmax', '_splitter_lax', '_suppressed_warning', '_validate_unit', 'check_anyuri', 'check_id', 'check_token', 'did_you_mean', 'fix_id', 'is_primary', 'is_secondary', 'normalize_capitalization', 'strip_accents', 'validate_schema']; ungrounded: none
- **bnew / `test_basic_rgb`** — missed: ['_convert_images_to_float', '_convert_images_to_uint']; ungrounded: none
- **bnew / `test_containers`** — missed: ['_get_distribution_cls', '_result_as_distribution', 'get_n_samples', 'is_distribution']; ungrounded: none
- **bnew / `test_lombscargle_multiband`** — missed: ['__str__', '_check_required_columns', '_init_from_ndarray', 'as_scalar_or_list_str', 'bitceil', 'extirpolate', 'format_string', 'get_err_str', 'ndim', 'str_kwargs', 'trig_sum']; ungrounded: none
- **bnew / `test_table`** — missed: ['_add_fieldref', '_add_paramref', '_all_matching_dtype', '_get_binary_data_stream', '_invalid_unit_error_message', '_is_null', '_parse_binary', '_resize_strategy', '_splitter_lax', '_write_binary', 'careful_read', 'check_anyuri', 'entries', 'iter_values', 'numpy_to_votable_dtype', 'yes_no']; ungrounded: none
- **bnew / `test_vo`** — missed: ['__set__', '_base_repr_', '_convert_to_fd_or_read_function', '_decompose_to_known_units', '_did_you_mean_units', '_format_message', '_init_from_ndarray', '_invalid_unit_error_message', '_parse_minmax', '_splitter_lax', '_suppressed_warning', '_validate_unit', 'check_anyuri', 'check_id', 'check_token', 'did_you_mean', 'fix_id', 'is_primary', 'is_secondary', 'normalize_capitalization', 'strip_accents', 'validate_schema']; ungrounded: none
