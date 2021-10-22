"""

"""

from yoyo import step

__depends__ = {'20210611_01_u5vBu-add-banned-posts-table'}

steps = [
    step("""
        ALTER TABLE post_file ADD COLUMN bucket_name varchar(20) NULL;
        ALTER TABLE artist_banner ADD COLUMN bucket_name varchar(20) NULL;
        ALTER TABLE artist_icon ADD COLUMN bucket_name varchar(20) NULL;
        ALTER TABLE post ADD COLUMN bucket_name varchar(20) NULL;
        UPDATE post_file SET bucket_name = 'nagato';
        UPDATE artist_banner SET bucket_name = 'nagato';
        UPDATE artist_icon SET bucket_name = 'nagato';
        UPDATE post SET bucket_name = 'nagato';
    """)
]
