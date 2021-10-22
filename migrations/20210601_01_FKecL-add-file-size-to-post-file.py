"""
Add file_size to post_file
"""

from yoyo import step

__depends__ = {'20210527_01_WsYmD-add-account-role-table'}

steps = [
    step("""
        ALTER TABLE post_file ADD COLUMN file_size bigint NULL;
    """)
]
