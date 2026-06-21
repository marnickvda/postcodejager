# Deploy Postcodejager (Hetzner + OpenTofu + Ansible + GitHub Actions)

OpenTofu provisions a Hetzner server, firewall, and DNS (zone + record) once.
Ansible configures it (Caddy with automatic HTTPS, a systemd service running the
app). GitHub Actions re-runs the Ansible playbook on **every push to `main`** to
pull the latest code and restart.

Because the backend is **stateless** (all user data lives in the visitor's
browser), there's no database to back up and no login to add. The server is just
compute plus the public PC4 map data.

## What you provide

| Item | Where |
|---|---|
| **Hetzner Cloud API token** (read/write) | console.hetzner.com → project → Security → API Tokens. The same token manages DNS (provider v1.56+); no separate DNS token needed. |
| **A registered domain** (e.g. at TransIP) | e.g. `postcodejager.nl`. You point its nameservers at Hetzner in step 3. |
| **An SSH keypair** | generated below |
| **Strava API app** | strava.com/settings/api (you already have client id/secret) |
| **A GitHub repo** with this code pushed | public repo = simplest (server clones over HTTPS) |

## 1. SSH key

```bash
ssh-keygen -t ed25519 -f ~/.ssh/postcodejager -N ""
# public key  -> OpenTofu var ssh_public_key
# private key -> GitHub secret SSH_PRIVATE_KEY
```

## 2. Provision (one-time, local)

```bash
cd deploy/tofu
cp terraform.tfvars.example terraform.tfvars   # fill in hcloud_token, dns_zone, subdomain, ssh_public_key
tofu init
tofu apply
```

`tofu apply` creates the server, the Hetzner DNS zone, and the A-record, and
prints:

- **`nameservers`**: the Hetzner nameservers to set at your registrar (step 3)
- **`fqdn`** (e.g. `postcodejager.nl`) and **`server_ipv4`**

Already created the zone by hand in the Hetzner Console? Import it first so tofu
manages it instead of erroring (`tofu import hcloud_zone.main <zone-name-or-id>`),
or delete the manual zone and let tofu create it.

## 3. Delegate the domain to Hetzner (at TransIP)

In the TransIP control panel, open your domain's **Nameservers** section, switch
from the TransIP nameservers to your own, and enter the values from
`tofu output nameservers` (the Hetzner nameservers). Save. Propagation can take
up to ~24h, usually much less.

## 4. Strava app settings

Set the **Authorization Callback Domain** to the bare host, e.g.
`postcodejager.nl` (no `https://`, no path). The deploy sets
`STRAVA_REDIRECT_URI=https://<fqdn>/auth/callback` automatically.

## 5. GitHub secrets

Repo → Settings → Secrets and variables → Actions → New repository secret:

| Secret | Value |
|---|---|
| `SSH_PRIVATE_KEY` | contents of `~/.ssh/postcodejager` (the private key) |
| `SERVER_HOST` | the `fqdn` from step 2 |
| `STRAVA_CLIENT_ID` | your Strava client id |
| `STRAVA_CLIENT_SECRET` | your Strava client secret |

## 6. Deploy

Deploys run on a **version tag** (not on every push). To release:

```bash
git tag v0.1.0
git push origin v0.1.0
```

Or trigger the **Deploy** workflow manually from the Actions tab. GitHub Actions
runs the Ansible playbook against the server: clone the tagged code, install,
fetch PC4 data on first run, (re)start the service, configure Caddy. The first
run also issues the HTTPS certificate, so finish step 3 and let DNS resolve first.

Open `https://<fqdn>` and connect Strava.

## Notes

- **Cost:** about EUR 4/mo (CAX11). Change `server_type`/`location` in `terraform.tfvars`.
- **No state to lose:** redeploys are safe; user data is in the browser. The only
  server data is `data/pc4.geojson`, re-fetchable any time.
- **Private repo?** The server clones over HTTPS; for a private repo add a deploy
  key or a PAT, or switch the deploy to rsync the checked-out code.
- **Routing:** uses the public BRouter server by default, no extra infra.
```
