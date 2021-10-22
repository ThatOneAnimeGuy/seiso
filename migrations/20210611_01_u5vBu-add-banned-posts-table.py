"""
add banned posts table
"""

from yoyo import step

__depends__ = {'20210601_01_FKecL-add-file-size-to-post-file'}

steps = [
    step("""
        CREATE TABLE banned_post (
            id serial PRIMARY KEY,
            service varchar(20) NOT NULL,
            artist_service_id varchar(255) NOT NULL,
            post_service_id varchar(255) NOT NULL,
            UNIQUE (service, artist_service_id, post_service_id)
        );
    """)
]
