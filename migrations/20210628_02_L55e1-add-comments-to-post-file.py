"""
add comments to post file
"""

from yoyo import step

__depends__ = {'20210622_01_9GhMW'}

steps = [
    step("ALTER TABLE post_file ADD COLUMN comment text NULL;")
]
