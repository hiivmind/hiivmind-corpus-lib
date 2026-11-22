from hiivmind_corpus_lib.pdf import decode_math, is_math_font


def test_decode_math_oml_greek():                              # ports test_decode_math_text_oml_greek
    assert decode_math("\u02db", "MT2MIT") == "α"
    assert decode_math("\u02c7", "MT2MIT") == "β"
    assert decode_math("\ufffd", "MT2MIT") == "π"

def test_decode_math_oms_operators():                          # ports test_decode_math_text_oms_operators
    assert decode_math("C", "MT2SYT") == "+"
    assert decode_math("D", "MT2SYT") == "="
    assert decode_math("j", "MT2SYT") == "|"

def test_decode_math_preserves_ascii():                        # ports test_decode_math_text_preserves_ascii
    assert decode_math("x", "MT2MIT") == "x"
    assert decode_math("Y", "MT2MIT") == "Y"

def test_decode_math_unknown_font_is_unchanged():              # ports test_decode_math_text_unknown_font
    assert decode_math("hello", "NimbusRomNo9L-Regu") == "hello"

def test_is_math_font():                                       # ports test_is_math_font
    assert is_math_font("MT2MIT") is True
    assert is_math_font("MT2SYT") is True
    assert is_math_font("MT2BMIT") is True
    assert is_math_font("NimbusRomNo9L-Regu") is False
    assert is_math_font("AlbanyAMT,Bold") is False

def test_decode_math_bold_beta():                              # ports test_decode_math_text_bold_beta
    assert decode_math("\u02c7", "MT2BMIT") == "β"

def test_decode_math_prime():                                  # ports test_decode_math_text_prime
    assert decode_math("0", "MT2SYS") == "′"

def test_decode_math_matches_a_font_by_prefix():               # plugin behaviour (font.startswith), untested there
    assert decode_math("D", "MT2SYT-Subset") == "="
    assert decode_math("p", "MT2EXA") == ")"
