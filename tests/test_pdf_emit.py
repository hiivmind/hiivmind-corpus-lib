from hiivmind_corpus_lib.pdf import (callout, chapter_markdown, code_block, dehyphenate, frontmatter,
                                     heading, safe_file_name, table, wikilink)


def test_heading():                                            # ports test_emit_heading
    assert heading("Macro Variables", 1) == "# Macro Variables"
    assert heading("Using Macros", 3) == "### Using Macros"

def test_code_block_with_and_without_language():               # ports test_emit_code_block, test_emit_code_block_no_language
    assert code_block("%let x=1;", "sas") == "```sas\n%let x=1;\n```"
    assert code_block("some output") == "```\nsome output\n```"

def test_table():                                              # ports test_emit_table
    result = table(["Name", "Type"], [["SYSDATE", "Read-only"], ["SYSERR", "Read and Write"]])
    assert "| Name | Type |" in result
    assert "| SYSDATE | Read-only |" in result
    assert "| --- | --- |" in result

def test_callout():                                            # ports test_emit_callout
    assert callout("Only printable characters should be used.", "note") == "> **Note:** Only printable characters should be used."

def test_frontmatter_lists_and_scalars():                      # ports test_emit_frontmatter
    assert frontmatter({"title": "Test", "tags": ["a", "b"]}) == "---\ntitle: Test\ntags:\n  - a\n  - b\n---\n"

def test_frontmatter_round_trips_through_yaml():               # through yamlio, the package's one YAML writer
    import yaml
    metadata = {"title": 'He said "A: B"', "flag": "yes", "pages": "1-2", "tags": ["a", "b"],
                "chapters": [{"file": "01_a", "pages": "1-2"}]}
    text = frontmatter(metadata)
    assert text.startswith("---\n") and text.endswith("\n---\n")
    loaded = yaml.safe_load(text.removeprefix("---\n").removesuffix("---\n"))
    assert loaded == metadata
    assert loaded["flag"] == "yes" and isinstance(loaded["flag"], str)      # the string 'yes' stays a string

def test_chapter_markdown_is_frontmatter_blank_line_body():    # plugin write_chapter_markdown, as text
    assert chapter_markdown({"title": "T"}, "# T\n\nBody") == "---\ntitle: T\n---\n\n# T\n\nBody"

def test_wikilink():                                           # ports test_make_wikilink
    assert wikilink("16_Scopes", "Scopes of Macro Variables") == "[[16_Scopes|Scopes of Macro Variables]]"

def test_safe_file_name():                                     # ports test_sanitize_filename
    assert safe_file_name("Chapter 3: Macro Variables!") == "Chapter_3_Macro_Variables"
    assert len(safe_file_name("A" * 100, max_length=50)) <= 50

def test_dehyphenate_joins_split_words():                      # ports test_dehyphenate_joins_split_words
    assert dehyphenate("inde- pendent") == "independent"
    assert dehyphenate("multi- variate analysis") == "multivariate analysis"

def test_dehyphenate_preserves_intentional_hyphens():          # ports test_dehyphenate_preserves_intentional_hyphens
    assert dehyphenate("end- Start") == "end- Start"
    assert dehyphenate("least-squares") == "least-squares"

def test_dehyphenate_preserves_short_fragments():              # ports test_dehyphenate_preserves_short_fragments
    assert dehyphenate("x- axis") == "x- axis"

def test_dehyphenate_empty_and_no_hyphens():                   # ports test_dehyphenate_empty_and_no_hyphens
    assert dehyphenate("") == ""
    assert dehyphenate("no hyphens here") == "no hyphens here"
