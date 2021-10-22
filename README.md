## Setup
```sh
cp config.py.example config.py
cp .env.vpn.example .env.vpn
cp .env.postgres.example .env.postgres
git submodule init
git submodule update
cd local
docker-compose up
```

Default login is `admin` and `password` (account id 1)

Make sure you update config files to have all the proper values
