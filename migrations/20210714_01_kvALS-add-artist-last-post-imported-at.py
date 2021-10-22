"""
add artist last post imported at
"""

from yoyo import step

__depends__ = {'20210712_02_9n9bA-make-display-name-unique'}

steps = [
    step(
        """
            ALTER TABLE artist ADD COLUMN last_post_imported_at timestamp NULL;
            UPDATE artist SET last_post_imported_at = last_indexed;
            CREATE INDEX ON artist (last_post_imported_at);
        """
    )
]
