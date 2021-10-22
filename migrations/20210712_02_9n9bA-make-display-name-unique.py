"""
make display name unique
"""

from yoyo import step

__depends__ = {'20210712_01_VrUMi-limit-account-name-length'}

steps = [
    step("ALTER TABLE account ADD UNIQUE (display_name);")
]
