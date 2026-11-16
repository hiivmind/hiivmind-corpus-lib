# /// script
# requires-python = ">=3.10"
# dependencies = ["lancedb>=0.20.0", "pyarrow>=15.0.0"]
# ///
"""Make a Lance directory with a `_meta` table, as `embed.py` writes it: `make_lance.py <dir> <generated_at>`."""

import sys

import lancedb
import pyarrow as pa

db = lancedb.connect(sys.argv[1])
db.create_table("_meta", data=pa.table({"key": ["generated_at"], "value": [sys.argv[2]]}), mode="overwrite")
