# Deploy Postcodejager (Hetzner + OpenTofu + Ansible + GitHub Actions)

OpenTofu provisions a Hetzner server, firewall and DNS record **once**. Ansible
configures it (Caddy with automatic HTTPS, a systemd service running the app).
GitHub Actions re-runs the Ansible playbook on **every push to `main`** to pull
the latest code and restart.

Because the backend is **stateless** (all user data lives in the visitor's
browser), there's no database to back up and no login to add — the server is
just compute + the public PC4 map data.

## What you provide

| Item | Where |
|---|---|
| **Hetzner Cloud API token** (read/write) | console.hetzner.com → project → Security → API Tokens |
| **Hetzner DNS API token** | dns.hetzner.com → API tokens |
| **A domain/subdomain** in your Hetzner DNS zone | e.g. `postcodejager.jouwdomein.nl` |
| **An SSH keypair** | generated below |
| **Strava API app** | strava.com/settings/api (you already have client id/secret) |
| **A GitHub repo** with this code pushed | public repo = simplest (server clones over HTTPS) |

## 1. SSH key

```bash
ssh-keygen -t ed25519 -f ~/.ssh/postcodejager -N ""
# public key  -> OpenTofu var ssh_public_key
# private key -> GitHub secret SSH_PRIVATE_KEY
```

## 2. Provision the server (one-time, local)

```bash
cd deploy/tofu
cp terraform.tfvars.example terraform.tfvars   # fill in tokens, dns_zone, subdomain, ssh_public_key
tofu init
tofu apply
```

`tofu apply` prints `fqdn` (e.g. `postcodejager.jouwdomein.nl`) and `server_ipv4`.
Re-run only when you want to change/destroy the server (`tofu destroy`).

## 3. Strava app settings

In your Strava API app set **Authorization Callback Domain** to the bare host —
e.g. `postcodejager.jouwdomein.nl` (no `https://`, no path). The deploy sets
`STRAVA_REDIRECT_URI=https://<fqdn>/auth/callback` automatically.

## 4. GitHub secrets

Repo → Settings → Secrets and variables → Actions → New repository secret:

| Secret | Value |
|---|---|
| `SSH_PRIVATE_KEY` | contents of `~/.ssh/postcodejager` (the private key) |
| `SERVER_HOST` | the `fqdn` from step 2 |
| `STRAVA_CLIENT_ID` | your Strava client id |
| `STRAVA_CLIENT_SECRET` | your Strava client secret |

## 5. Deploy

Push to `main` (or run the **Deploy** workflow manually). GitHub Actions runs the
Ansible playbook against the server: clone/pull, install, fetch PC4 data on first
run, (re)start the service, configure Caddy. First run also issues the HTTPS
certificate (DNS from step 2 must resolve first — usually a minute or two).

Open `https://<fqdn>` and connect Strava.

## Notes

- **Cost:** ~€4/mo (CAX11). Change `server_type`/`location` in `terraform.tfvars`.
- **No state to lose:** redeploys are safe; user data is in the browser. The
  only server data is `data/pc4.geojson`, re-fetchable any time.
- **Private repo?** The server clones over HTTPS; for a private repo add a deploy
  key or a PAT, or switch the deploy to rsync the checked-out code.
- **Routing:** uses the public BRouter server by default — no extra infra.
