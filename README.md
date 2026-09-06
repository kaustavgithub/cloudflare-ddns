# cloudflare-ddns

A small dynamic-DNS updater that keeps Cloudflare DNS records pointed at your
current public IP. It runs as a container, checks your IP on a fixed interval,
and only issues a Cloudflare API call when the address has actually changed.

The record list lives in a plain text file that is re-read on every cycle, so
adding or removing a hostname takes effect without restarting the container.

## How it works

Each cycle the script:

1. Reads `config/records.conf` and logs the list whenever it changes.
2. Looks up the zone ID for `CF_ZONE`.
3. Fetches the public IP from [ipify](https://www.ipify.org) — `api.ipify.org`
   for `A` records, `api6.ipify.org` for `AAAA`. The lookup is done once per
   record type per cycle, not once per hostname.
4. Compares each record's current content against that IP and issues a `PUT`
   only on a mismatch.
5. Sleeps for `INTERVAL` seconds.

Any exception is logged with a traceback and the loop continues, so a transient
API or network failure doesn't kill the container.

## Setup

```bash
cp .env.example .env
cp config/records_example.conf config/records.conf
# edit both, then:
docker compose up -d --build
```

Both `.env` and `config/records.conf` are gitignored — only the `*_example`
templates are tracked.

### Cloudflare API token

Create a token at **My Profile → API Tokens** with:

| Permission | Scope |
| --- | --- |
| `Zone → Zone → Read` | the zone in `CF_ZONE` |
| `Zone → DNS → Edit` | the zone in `CF_ZONE` |

The global API key is not used and is not supported.

## Configuration

### Environment (`.env`)

| Variable | Default | Description |
| --- | --- | --- |
| `CF_API_TOKEN` | — | Cloudflare API token. Required. |
| `CF_ZONE` | — | Zone (domain) name, e.g. `example.com`. Required. |
| `CF_RECORDS_FILE` | `/config/records.conf` | Path to the record list inside the container. |
| `CF_RECORD_TYPE` | `A` | Default record type for lines that don't override it. |
| `CF_PROXIED` | `false` | Default proxy setting for lines that don't override it. |
| `CF_RECORD` | — | Comma-separated fallback record list, used only if the records file is missing. |
| `INTERVAL` | `300` | Seconds between checks. Pinned to `300` in `docker-compose.yaml`. |
| `LOG_LEVEL` | `INFO` | `DEBUG` also logs raw API responses and resolved IPs. |

### Record list (`config/records.conf`)

One hostname per line. `#` starts a comment. Each line may override the
defaults with `type=` and `proxied=`:

```conf
app1.example.com
app2.example.com            proxied=false
ipv6.example.com  type=AAAA proxied=false
```

Only `A` and `AAAA` are supported; any other `type=` is logged and skipped.
Unknown options are warned about and ignored.

The records file is bind-mounted read-only as a **directory** (`./config:/config:ro`)
rather than a single file, so editors that replace the file's inode still show
the new content inside the container.

## Records must already exist

The updater updates records; it does not create them. A hostname that has no
matching DNS record in Cloudflare is logged as
`DNS record '<name>' not found. Skipping.` and passed over. Create the record
in the Cloudflare dashboard first, with any placeholder IP.

## Operating

```bash
docker compose logs -f              # follow output
docker compose restart              # after changing .env
docker compose up -d --build        # after changing cf-ddns.py
```

Changes to `config/records.conf` alone need no restart — they are picked up on
the next cycle, within `INTERVAL` seconds.
