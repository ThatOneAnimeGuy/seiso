CREATE TABLE account (
    id serial PRIMARY KEY,
    username varchar NOT NULL,
    email varchar(320) NULL,
    password_hash varchar NOT NULL,
    created_at timestamp NOT NULL DEFAULT (now() at time zone 'utc'),
    UNIQUE (username),
    UNIQUE (email)
);

CREATE TABLE artist (
    id serial PRIMARY KEY,
    service varchar(20) NOT NULL,
    service_id varchar(255) NOT NULL,
    display_name varchar(100) NOT NULL,
    username varchar(100),
    created_at timestamp NOT NULL DEFAULT (now() at time zone 'utc'),
    last_indexed timestamp,
    UNIQUE (service, service_id)
);
CREATE INDEX ON artist (last_indexed);


CREATE TABLE artist_banner (
    id serial PRIMARY KEY,
    artist_id integer NOT NULL REFERENCES artist(id),
    path varchar,
    retries_remaining integer NOT NULL DEFAULT 5,
    updated_at timestamp NOT NULL DEFAULT (now() at time zone 'utc'),
    UNIQUE (artist_id)
);
CREATE INDEX ON artist_banner (artist_id);


CREATE TABLE artist_icon (
    id serial PRIMARY KEY,
    artist_id integer NOT NULL REFERENCES artist(id),
    path varchar,
    retries_remaining integer NOT NULL DEFAULT 5,
    updated_at timestamp NOT NULL DEFAULT (now() at time zone 'utc'),
    UNIQUE (artist_id)
);


CREATE TABLE post (
    id serial PRIMARY KEY,
    service_id varchar(255) NOT NULL,
    artist_id integer NOT NULL REFERENCES artist(id),
    title varchar NOT NULL DEFAULT '',
    content varchar NOT NULL DEFAULT '',
    is_manual_upload boolean NOT NULL DEFAULT false,
    added_at timestamp NOT NULL DEFAULT (now() at time zone 'utc'),
    published_at timestamp,
    updated_at timestamp,
    is_import_finished boolean NOT NULL DEFAULT false,
    thumbnail_path varchar,
    imported_by int NULL REFERENCES account(id),
    UNIQUE (service_id, artist_id)
);
CREATE INDEX ON post USING btree (added_at);
CREATE INDEX ON post USING btree (published_at);
CREATE INDEX ON post USING GIN (to_tsvector('english', content || ' ' || title));


CREATE TABLE post_file (
    id serial PRIMARY KEY,
    post_id integer NOT NULL REFERENCES post(id),
    name varchar(255),
    path varchar,
    preview_path varchar,
    mime_type varchar(127) NOT NULL DEFAULT '',
    is_inline boolean NOT NULL DEFAULT false,
    inline_content varchar,
    is_upload_finished boolean NOT NULL DEFAULT false,
    sha256_hash char(64) NOT NULL,
    UNIQUE (post_id, sha256_hash)
);
CREATE INDEX ON post_file (sha256_hash);


CREATE TABLE post_embed (
    id serial PRIMARY KEY,
    post_id integer NOT NULL REFERENCES post(id),
    subject varchar,
    description varchar,
    url varchar
);
CREATE INDEX ON post_embed (post_id);


CREATE TABLE do_not_post_request (
    id serial PRIMARY KEY,
    service varchar(20) NOT NULL,
    service_id varchar(255) NOT NULL,
    UNIQUE (service, service_id)
);


CREATE TABLE reimport_flag (
    id serial PRIMARY KEY,
    post_id integer NOT NULL REFERENCES post(id),
    UNIQUE (post_id)
);


CREATE TABLE account_post_favorite (
    id serial PRIMARY KEY,
    account_id int NOT NULL REFERENCES account(id),
    post_id int NOT NULL REFERENCES post(id),
    UNIQUE (account_id, post_id)
);
CREATE INDEX ON account_post_favorite (post_id);


CREATE TABLE account_artist_favorite (
    id serial PRIMARY KEY,
    account_id int NOT NULL REFERENCES account(id),
    artist_id integer NOT NULL REFERENCES artist(id),
    UNIQUE (account_id, artist_id)
);
CREATE INDEX ON account_artist_favorite (artist_id);


CREATE TABLE ongoing_import (
    id serial PRIMARY KEY,
    service varchar(20) NOT NULL,
    encrypted_session_key varchar NOT NULL,
    import_id varchar(8) NOT NULL,
    session_key_sha256_hash char(64) NOT NULL,
    started_at timestamp NOT NULL DEFAULT (now() at time zone 'utc'),
    account_id int NULL REFERENCES account(id),
    UNIQUE (session_key_sha256_hash)
);
CREATE INDEX ON ongoing_import (started_at);


CREATE TABLE post_import_lock (
    id serial PRIMARY KEY,
    service varchar(20) NOT NULL,
    artist_service_id varchar(255) NOT NULL,
    post_service_id varchar(255) NOT NULL,
    taken_at timestamp NOT NULL DEFAULT (now() at time zone 'utc'),
    UNIQUE (service, artist_service_id, post_service_id)
);
