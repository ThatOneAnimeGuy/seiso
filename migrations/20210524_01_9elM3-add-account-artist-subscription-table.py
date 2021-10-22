"""
Add account_artist_subscription table
"""

from yoyo import step

__depends__ = {'initial'}

steps = [
    step("""
        CREATE TABLE account_artist_subscription (
            id serial NOT NULL PRIMARY KEY,
            account_id int NOT NULL REFERENCES account(id),
            artist_id int NOT NULL REFERENCES artist(id),
            last_imported_at timestamp NOT NULL DEFAULT (now() at time zone 'utc'),
            was_present_in_most_recent_import boolean NOT NULL DEFAULT true,
            UNIQUE (account_id, artist_id)
        );
        CREATE INDEX ON account_artist_subscription (account_id);
        CREATE INDEX ON account_artist_subscription (artist_id);
    """),
    step("""
        INSERT INTO account_artist_subscription (account_id, artist_id) SELECT imported_by, artist_id FROM post WHERE imported_by IS NOT NULL GROUP BY imported_by, artist_id;
        ALTER TABLE post DROP COLUMN imported_by;
    """)
]
