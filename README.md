# smtp_message — Email ↔ Telegram bridge

Open-source Telegram bot that keeps people reachable when Telegram access is unstable (VPN issues, blocks, travel).  
It bridges **group chat ↔ email**: tag a user, send mail; they reply by email, the answer lands back in the thread.

**Idea:** stay in touch without replacing Telegram — email is a fallback channel.

## Try the live bot

Public demo: **[@email_itbot](https://t.me/email_itbot)**

1. Open the bot → `/start`
2. Link email: `/email you@example.com` → confirm with `/confirm <code>` from the letter
3. Add **@email_itbot** to your group (admin recommended, or disable privacy so it sees `[mail_it]` / `[мыльни]`)
4. In the group: mention a user with a verified email and add `[mail_it]` or `[мыльни]`
5. When they answer by email, the bot posts `[Name replied]: "..."` in the group. Anyone else can **reply to that message** to continue on email; if the same person replies to their own bridged message, the bot ignores it.
6. **Group language** (admins): `@email_itbot ru` or `@email_itbot en`. Default is English; this affects bot replies and outbound emails in that group.

Self-hosting (own token / mailbox / Mongo) is described below.

---

## Features

- One shared bot mailbox (IMAP + SMTP); users only **link** their personal email
- Email confirmation via one-time code (`/email` → `/confirm`)
- Group triggers: `[mail_it]` or `[мыльни]` + mention → send email
- Reply threading both ways (TG reply ↔ email `In-Reply-To`)
- Default UI language: English; in DMs uses Telegram `language_code`; group admins switch with `@bot ru` / `@bot en`
- If someone in the group replies to a bridged message (`[Name replied]: "..."`), that reply is emailed to the offline user — **except** when that user replies to their own bridged message (ignored, no self-mail)
- Quote stripping on inbound mail; media described as text (no file forwarding)
- Message deep-link in outbound emails (when Telegram allows)
- Field-level encryption at rest (email, names, message bodies)
- Auto-delete of delivery threads after 72 hours (Mongo TTL)
- Privacy-first: no ads, no commercial use of user data
- Docker image build via GitHub Actions

## Stack

- Python 3.12, aiogram 3
- MongoDB (users, pending confirmations, threads)
- IMAP/SMTP
- Docker / docker-compose
- `cryptography` (Fernet + HMAC)

## Quick start (local)

```bash
cp .env.example .env
# fill BOT_TOKEN, MAIL_*, MONGO_URI, DATA_ENCRYPTION_KEY

pip install -r requirements.txt
python -m app.main
```

## Docker

CI pushes the image to a **private registry** (URL and credentials are GitHub Secrets, not in the repo).

On a server:

```bash
cp .env.example .env   # fill secrets + BOT_IMAGE; never commit .env
# If Mongo runs on the host, use host.docker.internal in MONGO_URI

docker login <your-private-registry>
docker compose pull
docker compose up -d
```

Local build (optional):

```bash
docker build -t smtp_message:local .
docker run --env-file .env --add-host=host.docker.internal:host-gateway smtp_message:local
```

## Bot commands

| Command | Description |
|---------|-------------|
| `/start` | Help (RU/EN) |
| `/email you@example.com` | Start email linking (sends code) |
| `/confirm 123456` | Confirm code from email |
| `/resend_code` | Resend code (max 5) |
| `/delemail` | Unlink email |
| `/whoami` | Show binding / verified flag |
| `/privacy` | Privacy policy |
| `/stop` | Delete profile from the bot |

**In a group:** `@user hello [mail_it]` or `[мыльни]` — bot emails the linked address (verified only).

## Privacy

- Stored binding: Telegram ID ↔ email (+ short-lived delivery threads)
- Sensitive fields encrypted with `DATA_ENCRYPTION_KEY`
- Threads expire after `MESSAGE_RETENTION_HOURS` (default 72)
- Not used for commercial profiling
- Contact: [@netpregrad](https://t.me/netpregrad)

See also `/privacy` in the bot.

## Configuration

See `.env.example`. Important vars:

- `BOT_TOKEN` — Telegram bot token
- `BOT_IMAGE` — full image ref for compose (`registry/name:tag`)
- `MAIL_ADDRESS` / `MAIL_PASSWORD` / `SMTP_*` / `IMAP_*` — bot mailbox
- `MONGO_URI` / `MONGO_DB`
- `DATA_ENCRYPTION_KEY` — required encryption secret
- `MESSAGE_RETENTION_HOURS` — thread TTL (default `72`)

## CI

On push to `main`/`master` (or tags `v*`), GitHub Actions builds and pushes the image.  
Repository secrets (not public):

- `DCR_REGISTRY` — registry host
- `DCR_IMAGE` — image name without tag (`host/name`)
- `DCR_USERNAME`
- `DCR_PASSWORD`

## Roadmap (optional / self-hosted)

- Real attachments
- AI daily summaries
- Multi-tenant / corporate packaging

## License

MIT (or set your preferred license before publishing).

---

Built as a practical fallback bridge: **Telegram first, email when needed.**
