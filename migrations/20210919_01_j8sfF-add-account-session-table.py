"""
add account_session table
"""

from yoyo import step

__depends__ = {'20210808_01_sS1X2-add-table-for-processed-sub-ids'}

steps = [
    step("""
        CREATE TABLE account_session (
            id serial primary key,
            account_id int not null references account(id),
            service varchar(20) not null,
            encrypted_key text not null,
            session_key_sha256_hash char(64) not null,
            retries_remaining int not null default 2,
            created_at timestamp not null default (now() at time zone 'utc'),
            last_imported_at timestamp not null default (now() at time zone 'utc')
        );
        CREATE UNIQUE INDEX ON account_session (service, session_key_sha256_hash);
        CREATE UNIQUE INDEX ON account_session (account_id, service);
        CREATE INDEX ON account_session (account_id);
    """)
]
