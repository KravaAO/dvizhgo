# Production: `dvizhgo.knowstack.space`

## Architecture

`dvizhgo.knowstack.space` is served only through the existing KnowStack Nginx
container. DvizhGO, PostgreSQL and Redis do **not** expose host ports. Nginx
uses Docker DNS in the existing `msschool_default` network to reach the
`dvizhgo-web:5000` alias. This avoids the occupied KommoAI port `18081` and
does not use `18080`, `5000`, `5432` or `6379` on the server.

```
Internet :443 -> KnowStack Nginx -> dvizhgo-web:5000 -> PostgreSQL / Redis
```

## Before deployment

1. Create DNS records for `dvizhgo.knowstack.space` pointing to the server's
   public IPv4 address (and IPv6 only if the server accepts it).
2. Confirm that ports `80` and `443` remain owned by KnowStack Nginx.
3. Issue a Let's Encrypt certificate with the same process used for
   `kommoai.tutordesk.site`. Nginx must be able to read:
   `/etc/letsencrypt/live/dvizhgo.knowstack.space/fullchain.pem` and
   `privkey.pem`.
4. Copy `.env.production.example` to `.env.production` on the server and set
   unique values for `POSTGRES_PASSWORD`, `SECRET_KEY`, `ADMIN_PASSWORD` and
   `AVATAR_LAB_PATH`. Do not commit this file.

## Deploy

1. Copy `deploy/nginx/dvizhgo.knowstack.space.conf` into
   `C:\Users\artem\Documents\knowstack\nginx\nginx.conf` after the existing
   KommoAI blocks.
2. Validate and reload Nginx before starting the new stack:

   ```powershell
   docker compose -f C:\Users\artem\Documents\knowstack\docker-compose.yml -f C:\Users\artem\Documents\knowstack\docker-compose.prod.yml exec nginx nginx -t
   docker compose -f C:\Users\artem\Documents\knowstack\docker-compose.yml -f C:\Users\artem\Documents\knowstack\docker-compose.prod.yml exec nginx nginx -s reload
   ```

3. From the DvizhGO repository, start production with a stable project name:

   ```powershell
   docker compose -p dvizhgo --env-file .env.production -f docker-compose.yml -f docker-compose.production.yml up -d --build
   ```

4. Verify internal connectivity from the KnowStack Nginx container:

   ```powershell
   docker compose -f C:\Users\artem\Documents\knowstack\docker-compose.yml -f C:\Users\artem\Documents\knowstack\docker-compose.prod.yml exec nginx wget -qO- http://dvizhgo-web:5000/health
   ```

## Acceptance checklist

- [ ] `https://dvizhgo.knowstack.space/health` returns `200`.
- [ ] HTTP redirects to HTTPS.
- [ ] The home page and `/how-it-works` load; the MP4 can be sought on its
  timeline.
- [ ] A host can create a room; multiple browsers can join and receive live
  Socket.IO updates.
- [ ] A quiz, ДВИЖ-ДУЕЛЬ and Flash Question work over the public domain.
- [ ] `docker compose -p dvizhgo ... ps` shows healthy `web`, `db` and `redis`.

## Rollback

Remove only the `dvizhgo.knowstack.space` Nginx server blocks, validate/reload
Nginx, then run:

```powershell
docker compose -p dvizhgo --env-file .env.production -f docker-compose.yml -f docker-compose.production.yml down
```

Do not append `-v`: the PostgreSQL volume is production data.
