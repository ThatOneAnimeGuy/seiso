"""

"""

from yoyo import step

__depends__ = {'20210712_02_9n9bA-make-display-name-unique'}

steps = [
    step("""
        CREATE TABLE extra_post_content (
            id serial NOT NULL PRIMARY KEY,
            post_id int NOT NULL REFERENCES post(id),
            title varchar NULL,
            content varchar NOT NULL
        );
        CREATE INDEX ON extra_post_content (post_id)
    """)
]
