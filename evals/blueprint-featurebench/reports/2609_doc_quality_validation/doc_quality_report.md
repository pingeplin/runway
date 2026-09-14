# Doc quality — deterministic spec metrics (stage 12)

Oracle = `def`/`class` symbols the dataset mask removed. Recall = share the spec names in code context; effective recall excludes symbols the spec fences off. Fenced = oracle symbols under an out-of-scope heading or in a do-not-touch sentence (heuristic; stage 13 has the LLM listing). Grounding = share of named files/identifiers that exist in the masked workspace or are oracle symbols.

| label | task | lines | oracle syms | symbol recall | effective recall | file recall | fenced∩oracle | grounding | B pass_rate |
|---|---|---|---|---|---|---|---|---|---|
| v4 | `test_basic_rgb` | 753 | 9 | 0.78 | 0.78 | 1.00 | 0 | 0.99 | 0.94 |
| v4 | `test_containers` | 938 | 16 | 0.75 | 0.75 | 1.00 | 0 | 0.97 | 1.00 |
| v4 | `test_lombscargle_multiband` | 637 | 18 | 0.50 | 0.50 | 0.73 | 0 | 0.97 | 0.96 |
| v4 | `test_table` | 258 | 37 | 0.65 | 0.38 | 0.50 | 10 ['_iterable_helper', '_make_masked_array', '_parse_binary', '_resize_strategy', '_write_binary', 'binparse', 'bitarray_to_bool', 'bool_to_bitarray', 'concatenate', 'data'] | 0.99 | 0.35 |
| v4 | `test_vo` | 587 | 33 | 0.33 | 0.33 | 0.18 | 0 | 0.99 | 0.95 |
| ouroboros-a | `test_basic_rgb` | 575 | 9 | 0.78 | 0.67 | 1.00 | 1 ['_process_values'] | 0.98 | 1.00 |
| ouroboros-a | `test_containers` | 777 | 16 | 0.75 | 0.69 | 1.00 | 1 ['pdf_std'] | 0.98 | 0.52 |
| ouroboros-a | `test_lombscargle_multiband` | 748 | 18 | 0.67 | 0.50 | 0.53 | 3 ['get_err_str', 'get_unit', 'strip_units'] | 0.98 | 0.03 |
| ouroboros-a | `test_table` | 473 | 37 | 0.68 | 0.38 | 0.50 | 11 ['_all_matching_dtype', '_binoutput_fixed', '_binoutput_var', '_binparse_fixed', '_make_masked_array', '_parse_binary', '_resize_strategy', 'bitarray_to_bool', 'bool_to_bitarray', 'data', 'numpy_to_votable_dtype'] | 0.98 | 0.30 |
| ouroboros-a | `test_vo` | 667 | 33 | 0.24 | 0.24 | 0.09 | 0 | 0.99 | 0.00 |
| ouroboros-b | `test_basic_rgb` | 719 | 9 | 0.78 | 0.78 | 1.00 | 0 | 1.00 | 0.94 |
| ouroboros-b | `test_containers` | 767 | 16 | 0.75 | 0.75 | 1.00 | 0 | 0.97 | 0.67 |
| ouroboros-b | `test_lombscargle_multiband` | 783 | 18 | 0.61 | 0.56 | 0.67 | 1 ['get_err_str'] | 0.99 | 0.03 |
| ouroboros-b | `test_table` | 848 | 37 | 0.84 | 0.78 | 0.50 | 2 ['get_first_table', 'to_table'] | 0.98 | 0.88 |
| ouroboros-b | `test_vo` | 662 | 33 | 0.85 | 0.85 | 0.82 | 0 | 0.99 | 1.00 |

## Per-label means

| label | n | symbol recall | effective recall | file recall | fenced∩oracle (sum) | grounding | B pass_rate |
|---|---|---|---|---|---|---|---|
| v4 | 5 | 0.60 | 0.55 | 0.68 | 10 | 0.98 | 0.84 |
| ouroboros-a | 5 | 0.62 | 0.49 | 0.62 | 16 | 0.98 | 0.37 |
| ouroboros-b | 5 | 0.77 | 0.74 | 0.80 | 3 | 0.99 | 0.70 |

## Direction against B pass_rate (5 tasks × 3 labels)

| metric | expected sign | pooled Spearman ρ | within-task agreement with expected sign (label pairs) |
|---|---|---|---|
| `symbol_recall` | + | 0.50 (n=15) | 0.62 (8 pairs) |
| `effective_recall` | + | 0.50 (n=15) | 0.70 (10 pairs) |
| `file_recall` | + | 0.50 (n=15) | 1.00 (5 pairs) |
| `fenced∩oracle` | − | -0.49 (n=15) | 0.78 (9 pairs) |
| `grounding_precision` | + | -0.30 (n=15) | 0.31 (13 pairs) |
| `spec_lines` | none | -0.05 (n=15) | 0.38 (13 pairs) |

Pooled ρ mixes task difficulty with spec quality (cells share tasks, so they are not independent); agreement compares labels inside one task only, as the share of pairs ordered the way the expected sign predicts (0.50 = coin flip; a metric with no expected sign is read as +). A metric that points the wrong way on either view is **diagnostic only** and must not be a target.

## Misses and ungrounded names

- **v4 / `test_basic_rgb`** — missed: ['_convert_images_to_float', '_convert_images_to_uint']; ungrounded: ['com/spacetelescope/stsci.numdisplay/blob/master/lib/stsci/numdisplay/zscale.py', 'xNxM']
- **v4 / `test_containers`** — missed: ['_get_distribution_cls', '_result_as_distribution', 'get_n_samples', 'is_distribution']; ungrounded: ['_median', '_subok_false', 'arr_t', 'as_strided', 'deg2', 'raw_samples', 'test_setitem_']
- **v4 / `test_lombscargle_multiband`** — missed: ['__str__', '_check_required_columns', '_init_from_ndarray', 'as_scalar_or_list_str', 'bitceil', 'extirpolate', 'format_string', 'str_kwargs', 'trig_sum']; ungrounded: ['Barrier', 'masked_b', 'plain_a', 'plain_c']
- **v4 / `test_table`** — missed: ['_add_fieldref', '_add_paramref', '_all_matching_dtype', '_get_binary_data_stream', '_invalid_unit_error_message', '_is_null', '_splitter_lax', 'careful_read', 'check_anyuri', 'entries', 'iter_values', 'numpy_to_votable_dtype', 'yes_no']; ungrounded: ['U0001F600b', 'test_converters']
- **v4 / `test_vo`** — missed: ['__set__', '_base_repr_', '_convert_to_fd_or_read_function', '_decompose_to_known_units', '_did_you_mean_units', '_format_message', '_init_from_ndarray', '_invalid_unit_error_message', '_parse_minmax', '_splitter_lax', '_suppressed_warning', '_validate_unit', 'check_anyuri', 'check_id', 'check_token', 'did_you_mean', 'fix_id', 'is_primary', 'is_secondary', 'normalize_capitalization', 'strip_accents', 'validate_schema']; ungrounded: ['GENERIC_GALACTIC', 'paramref_instance']
- **ouroboros-a / `test_basic_rgb`** — missed: ['_convert_images_to_float', '_convert_images_to_uint']; ungrounded: ['S11', 'S21', 'minpix']
- **ouroboros-a / `test_containers`** — missed: ['_get_distribution_cls', '_result_as_distribution', 'get_n_samples', 'is_distribution']; ungrounded: ['SomeQuantitySubclass', 'arr_distribution', 'd1000', 'samples_cls']
- **ouroboros-a / `test_lombscargle_multiband`** — missed: ['__str__', 'as_scalar_or_list_str', 'bitceil', 'extirpolate', 'ndim', 'trig_sum']; ungrounded: ['_validate_', 'getcontext', 'jyr']
- **ouroboros-a / `test_table`** — missed: ['_add_fieldref', '_add_paramref', '_as_quantity', '_get_binary_data_stream', '_invalid_unit_error_message', '_is_null', '_splitter_lax', '_write_binary', 'careful_read', 'check_anyuri', 'iter_values', 'yes_no']; ungrounded: ['U0001D11E', '_init_from_', 'number_of_columns', 'number_of_columns_before_adding']
- **ouroboros-a / `test_vo`** — missed: ['__set__', '_base_repr_', '_convert_to_fd_or_read_function', '_decompose_to_known_units', '_did_you_mean_units', '_format_message', '_init_from_ndarray', '_invalid_unit_error_message', '_parse_minmax', '_splitter_lax', '_suppressed_warning', '_validate_unit', 'check_anyuri', 'check_astroyear', 'check_id', 'check_string', 'check_token', 'did_you_mean', 'fix_id', 'is_primary', 'is_secondary', 'normalize_capitalization', 'reference_frames', 'strip_accents', 'validate_schema']; ungrounded: ['flux3', 'n_tables']
- **ouroboros-b / `test_basic_rgb`** — missed: ['_convert_images_to_float', '_convert_images_to_uint']; ungrounded: none
- **ouroboros-b / `test_containers`** — missed: ['_get_distribution_cls', '_result_as_distribution', 'get_n_samples', 'is_distribution']; ungrounded: ['Ordinary', 'broadcast_', 'logical_shape', 'other_dtype', 'other_logical_shape', 'plain_ndarray']
- **ouroboros-b / `test_lombscargle_multiband`** — missed: ['__str__', 'as_scalar_or_list_str', 'bitceil', 'extirpolate', 'format_string', 'ndim', 'trig_sum']; ungrounded: ['_to_twoval']
- **ouroboros-b / `test_table`** — missed: ['_get_binary_data_stream', '_invalid_unit_error_message', '_is_null', 'careful_read', 'check_anyuri', 'yes_no']; ungrounded: ['U0001F600', 'café', 'foo_1', 'int_nulls', 'some_plain_ndarray']
- **ouroboros-b / `test_vo`** — missed: ['__set__', '_decompose_to_known_units', '_invalid_unit_error_message', '_suppressed_warning', '_validate_unit']; ungrounded: ['Flux2', 'Flux3']
