"""
Add account_role table
"""

from yoyo import step

__depends__ = {'20210524_01_9elM3-add-account-artist-subscription-table'}

steps = [
    step("""
        INSERT INTO account (id, username, password_hash) VALUES (1, 'admin', '$2y$12$NcBlnm9W1sJ14R99c/jTTuGEBz6YFCxOVrtxKyhr3cdb654vRfX1u') ON CONFLICT DO NOTHING;
        CREATE TABLE account_role (
            id serial NOT NULL PRIMARY KEY,
            account_id int NOT NULL REFERENCES account(id),
            role varchar(20) NOT NULL,
            UNIQUE (account_id, role)
        );
        INSERT INTO account_role (account_id, role) VALUES (1, 'admin');
    """)
]
