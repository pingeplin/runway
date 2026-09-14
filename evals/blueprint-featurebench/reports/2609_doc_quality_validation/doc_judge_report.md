# Doc quality — LLM-judged spec metrics (stage 13)

Judge: report-only, tools disabled, prompts under `prompts/judge_*.md`, up to 2 repeat(s) per cell. Values are means over repeats; ± is max−min across repeats (judge self-agreement).

| label | task | fenced (hard∩oracle) | contradictions | drift | ordering | scenarios | behavioral share | DoD / agent instr | B pass_rate |
|---|---|---|---|---|---|---|---|---|---|
| v4 | `test_basic_rgb` | 2.00 ['__call__', 'apply_mappings'] | 4.50 ±1 | 0.00 | 4.00 | 25.00 | 1.00 | y/y | 0.94 |
| v4 | `test_containers` | 1.00 ['distribution'] | 5.00 ±4 | 1.00 ±2 | 1.50 ±1 | 32.00 | 0.94 | y/n | 1.00 |
| v4 | `test_lombscargle_multiband` | 2.00 ['get_err_str', 'ndim'] | 1.50 ±1 | 1.50 ±1 | 2.00 | 21.00 | 0.93 ±0.047 | y/y | 0.96 |
| v4 | `test_table` | 8.00 ['__init__', '_make_masked_array', '_parse_binary', '_resize_strategy', '_write_binary', 'bitarray_to_bool', 'bool_to_bitarray', 'concatenate'] | 6.50 ±1 | 0.50 ±1 | 1.00 | 33.00 | 1.00 | y/y | 0.35 |
| v4 | `test_vo` | 0.00 | 3.50 ±1 | 2.50 ±1 | 0.00 | 18.00 | 1.00 | y/y | 0.95 |
| ouroboros-a | `test_basic_rgb` | 0.00 | 4.00 | 0.50 ±1 | 0.50 ±1 | 24.00 | 1.00 | y/y | 1.00 |
| ouroboros-a | `test_containers` | 0.00 | 1.50 ±1 | 0.00 | 1.00 | 41.00 | 0.99 ±0.024 | y/y | 0.52 |
| ouroboros-a | `test_lombscargle_multiband` | 7.00 ['_check_required_columns', '_init_from_ndarray', 'format_string', 'get_err_str', 'get_unit', 'str_kwargs', 'strip_units'] | 2.00 ±2 | 2.00 ±2 | 1.50 ±1 | 21.00 | 0.93 ±0.143 | y/y | 0.03 |
| ouroboros-a | `test_table` | 13.00 ['_all_matching_dtype', '_binoutput_fixed', '_binparse_fixed', '_make_masked_array', '_parse_binary', '_parse_length', '_quantities2arrays', '_resize_strategy', '_write_length', 'bitarray_to_bool', 'bool_to_bitarray', 'is_empty', 'numpy_to_votable_dtype'] | 4.00 ±2 | 1.00 | 0.50 ±1 | 42.00 | 1.00 | y/y | 0.30 |
| ouroboros-a | `test_vo` | 0.00 | 2.50 ±1 | 0.00 | 0.00 | 18.00 | 1.00 | y/y | 0.00 |
| ouroboros-b | `test_basic_rgb` | 1.00 ±2 ['__call__', 'apply_mappings'] | 1.00 | 0.50 ±1 | 0.50 ±1 | 26.00 | 0.96 | y/y | 0.94 |
| ouroboros-b | `test_containers` | 0.00 | 4.50 ±3 | 3.00 | 4.50 ±3 | 42.00 | 0.98 | y/y | 0.67 |
| ouroboros-b | `test_lombscargle_multiband` | 6.00 ['_check_required_columns', '_init_from_ndarray', 'get_err_str', 'get_unit', 'str_kwargs', 'strip_units'] | 4.00 ±4 | 0.50 ±1 | 0.50 ±1 | 23.00 | 0.85 ±0.044 | y/y | 0.03 |
| ouroboros-b | `test_table` | 4.50 ±1 ['__init__', '_binoutput_fixed', '_binoutput_var', '_binparse_fixed', '_binparse_var'] | 3.50 ±1 | 0.50 ±1 | 2.50 ±1 | 33.00 | 0.97 | y/y | 0.88 |
| ouroboros-b | `test_vo` | 1.00 ['get_ref'] | 2.00 | 1.00 | 2.00 ±2 | 28.00 | 0.96 | y/y | 1.00 |

## Per-label means

| label | n | hard fenced∩oracle | contradictions | drift | ordering | behavioral share | B pass_rate |
|---|---|---|---|---|---|---|---|
| v4 | 5 | 2.60 | 4.20 | 1.10 | 1.70 | 0.97 | 0.84 |
| ouroboros-a | 5 | 4.00 | 2.80 | 0.70 | 0.70 | 0.98 | 0.37 |
| ouroboros-b | 5 | 2.50 | 3.00 | 1.10 | 2.00 | 0.94 | 0.70 |

## Direction against B pass_rate (5 tasks × 3 labels)

| metric | expected sign | pooled Spearman ρ | within-task agreement with expected sign (label pairs) |
|---|---|---|---|
| `hard_oracle_n` | − | -0.35 (n=15) | 0.64 (11 pairs) |
| `contradictions` | − | -0.00 (n=15) | 0.54 (13 pairs) |
| `drift` | − | 0.23 (n=15) | 0.45 (11 pairs) |
| `ordering` | − | 0.27 (n=15) | 0.18 (11 pairs) |
| `behavioral_share` | + | -0.04 (n=15) | 0.22 (9 pairs) |

Pooled ρ mixes task difficulty with spec quality (cells share tasks, so they are not independent); agreement compares labels inside one task only, as the share of pairs ordered the way the expected sign predicts (0.50 = coin flip; a metric with no expected sign is read as +). A metric that points the wrong way on either view is **diagnostic only** and must not be a target.
