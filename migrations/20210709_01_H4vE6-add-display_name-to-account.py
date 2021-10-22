"""
add display_name to account
"""

from yoyo import step

__depends__ = {'20210628_02_L55e1-add-comments-to-post-file'}

steps = [
    step("ALTER TABLE account ADD COLUMN display_name varchar(20) NULL;")
]
