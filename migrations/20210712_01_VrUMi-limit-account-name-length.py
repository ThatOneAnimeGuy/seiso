"""
limit username length
"""

from yoyo import step

__depends__ = {'20210709_01_H4vE6-add-display_name-to-account'}

steps = [
    step("ALTER TABLE account ALTER COLUMN username TYPE varchar(30);")
]
