# Doc quality — LLM-judged spec metrics (stage 13)

Judge: report-only, tools disabled, prompts under `prompts/judge_*.md`, up to 2 repeat(s) per cell. Values are means over repeats; ± is max−min across repeats (judge self-agreement).

| label | task | fenced (hard∩oracle) | scenarios | behavioral share | DoD / agent instr | B pass_rate |
|---|---|---|---|---|---|---|
| b41 | `test_basic_rgb` | 2.00 ['__call__', 'apply_mappings'] | — | — | — | — |
| b41 | `test_containers` | 1.00 ['distribution'] | — | — | — | — |
| b41 | `test_lombscargle_multiband` | 2.00 ['get_err_str', 'ndim'] | — | — | — | — |
| b41 | `test_table` | 8.00 ['__init__', '_make_masked_array', '_parse_binary', '_resize_strategy', '_write_binary', 'bitarray_to_bool', 'bool_to_bitarray', 'concatenate'] | — | — | — | — |
| b41 | `test_vo` | 0.00 | — | — | — | — |
| bnew | `test_basic_rgb` | 2.00 ['__call__', 'apply_mappings'] | — | — | — | — |
| bnew | `test_containers` | 0.00 | — | — | — | — |
| bnew | `test_lombscargle_multiband` | 0.00 | — | — | — | — |
| bnew | `test_table` | 6.00 ['_binoutput_fixed', '_binparse_fixed', '_make_masked_array', 'bitarray_to_bool', 'bool_to_bitarray', 'concatenate'] | — | — | — | — |
| bnew | `test_vo` | 1.00 ['get_ref'] | — | — | — | — |

## Per-label means

| label | n | hard fenced∩oracle | behavioral share | B pass_rate |
|---|---|---|---|---|
| b41 | 5 | 2.60 | — | — |
| bnew | 5 | 1.80 | — | — |
