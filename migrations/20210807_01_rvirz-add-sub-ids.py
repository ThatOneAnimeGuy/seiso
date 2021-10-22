"""
add sub ids
"""

from yoyo import step

__depends__ = {'20210714_01_kvALS-add-artist-last-post-imported-at', '20210715_01_rxObX-add-post-extra-content'}

steps = [
    step("""
        ALTER TABLE post_file ADD COLUMN sub_id varchar(255) NULL;
        ALTER TABLE extra_post_content ADD COLUMN sub_id varchar(255) NULL;
        ALTER TABLE post_embed ADD COLUMN sub_id varchar(255) NULL;
        CREATE INDEX ON post_file (sub_id);
        CREATE INDEX ON extra_post_content (sub_id);
        CREATE INDEX ON post_embed (sub_id);
    """)
]
