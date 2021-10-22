"""
add table for processed sub ids
"""

from yoyo import step

__depends__ = {'20210807_01_rvirz-add-sub-ids'}

steps = [
    step("""
        CREATE TABLE processed_sub_id (
            id serial NOT NULL PRIMARY KEY,
            post_id int NOT NULL REFERENCES post(id),
            sub_id varchar(255) NOT NULL,
            UNIQUE (post_id, sub_id)
        )
    """)
]
