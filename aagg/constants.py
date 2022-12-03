"""Constants File"""

AGGR_FORM1 = 1  # Form:  b <= #count{ X : f(X) }
AGGR_FORM2 = 2  # Form:  not #count{ Y : f(Y) } < b
AGGR_FORM3 = 3  # Form:  not b - 1 = #count{ Y : f(Y) }, ..., not 0 = #count{ Y : f(Y) }

LOCATION = {    # Custom 'Location' value for aagg-created AST objects, which do not correspond to a real file location
    'begin': {'column': 'inserted-by-aagg', 'line': 'inserted-by-aagg', 'filename': '<string>'},
    'end': {'column': 'inserted-by-aagg', 'line': 'inserted-by-aagg', 'filename': '<string>'}}
