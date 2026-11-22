from hiivmind_corpus_lib.pdf import expand_newline_cells, layout_table, merge_continuation_rows, split_subtables, strip_empty_columns


def test_split_subtables_on_empty_rows():                      # ports test_split_subtables_on_empty_rows
    rows = [["Source", "DF", "SS"], ["Model", "3", "91.7"], [None, None, None], ["R-Square", "Coeff Var"], ["0.94", "9.8"]]
    assert split_subtables(rows) == ((("Source", "DF", "SS"), ("Model", "3", "91.7")), (("R-Square", "Coeff Var"), ("0.94", "9.8")))

def test_split_subtables_no_separators():                      # ports test_split_subtables_no_separators
    assert len(split_subtables([["A", "B"], ["1", "2"]])) == 1

def test_split_subtables_empty_string_rows():                  # ports test_split_subtables_empty_string_rows
    assert len(split_subtables([["A"], ["", ""], ["B"]])) == 2

def test_expand_newline_cells():                               # ports test_expand_newline_cells
    rows = [["Source", "DF\nSquares\nMean Square", "F Value"], ["Model", "3\n91.7\n30.6", "15.29"]]
    assert expand_newline_cells(rows) == (("Source", "DF", "Squares", "Mean Square", "F Value"), ("Model", "3", "91.7", "30.6", "15.29"))

def test_expand_newline_cells_normalizes_columns():            # ports test_expand_newline_cells_normalizes_columns
    result = expand_newline_cells([["A\nB", "C"], ["D", "E"]])
    assert len(result[0]) == len(result[1]) == 3

def test_expand_newline_cells_empty():                         # ports test_expand_newline_cells_empty
    assert expand_newline_cells([]) == ()

def test_merge_continuation_rows_backward():                   # ports test_merge_continuation_rows_backward
    result = merge_continuation_rows([["MANOVA", "Requests multivariate mode of eliminating observations with missing"], ["", "values"]])
    assert len(result) == 1 and result[0][0] == "MANOVA" and "missing values" in result[0][1]

def test_merge_continuation_rows_forward_sparse_header():      # ports test_merge_continuation_rows_forward_sparse_header
    result = merge_continuation_rows([["", "", "Sum of", ""], ["Source", "DF", "", "F Value"], ["Model", "3", "91.7", "15.29"]])
    assert len(result) == 2 and result[0][2] == "Sum of"

def test_merge_continuation_rows_preserves_normal_rows():      # ports test_merge_continuation_rows_preserves_normal_rows
    assert len(merge_continuation_rows([["A", "B"], ["C", "D"]])) == 2

def test_strip_empty_columns():                                # ports test_strip_empty_columns
    headers, rows = strip_empty_columns(["Source", "", "DF", "", "SS"], [["Model", "", "3", "", "91.7"], ["Error", "", "10", "", "6.0"]])
    assert headers == ("Source", "DF", "SS")
    assert rows == (("Model", "3", "91.7"), ("Error", "10", "6.0"))

def test_strip_empty_columns_keeps_nonempty():                 # ports test_strip_empty_columns_keeps_nonempty
    headers, _ = strip_empty_columns(["A", "B"], [["1", "2"]])
    assert headers == ("A", "B")

def test_table_helpers_do_not_mutate_their_input():            # P-3 (the plugin's versions edited rows in place)
    rows = [["", "", "Sum of", ""], ["Source", "DF", "", "F Value"], ["Model", "3", "91.7", "15.29"]]
    before = [list(r) for r in rows]
    merge_continuation_rows(rows)
    expand_newline_cells(rows)
    assert rows == before

def test_layout_table_simple():                                # ports test_emit_layout_table_simple
    result = layout_table([["Source", "DF", "SS"], ["Model", "3", "91.7"], ["Error", "10", "6.0"]])
    assert "| Source | DF | SS |" in result and "| Model | 3 | 91.7 |" in result

def test_layout_table_splits_subtables():                      # ports test_emit_layout_table_splits_subtables
    result = layout_table([["A", "B"], ["1", "2"], [None, None], ["C", "D"], ["3", "4"]])
    assert result.count("| --- |") == 2

def test_layout_table_empty_returns_empty():                   # ports test_emit_layout_table_empty_returns_empty
    assert layout_table([]) == ""
    assert layout_table([[None, None]]) == ""

def test_layout_table_merges_continuations():                  # ports test_emit_layout_table_merges_continuations
    result = layout_table([["Option", "Description"], ["MANOVA", "Requests multivariate mode of eliminating observations with missing"], [None, "values"]])
    assert "missing values" in result
    assert len([l for l in result.strip().split("\n") if l.startswith("|")]) == 3

def test_layout_table_over_eight_columns_is_a_code_block():     # §7.8 fallback rule
    result = layout_table([list("abcdefghi"), list("123456789")])
    assert result == "```\na  b  c  d  e  f  g  h  i\n1  2  3  4  5  6  7  8  9\n```\n"

def test_layout_table_more_than_half_empty_cells_is_a_code_block():    # §7.8 fallback rule: 10 of 18 cells empty
    result = layout_table([["A", "B", "C"], ["1", "", ""], ["2", "", ""], ["3", "", ""], ["4", "", ""], ["5", "", ""]])
    assert result == "```\nA  B  C\n1\n2\n3\n4\n5\n```\n"
