terraform {
  required_version = ">= 1.6"
  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.56" # DNS resources (hcloud_zone_rrset) need >= 1.56
    }
  }
}

provider "hcloud" {
  token = var.hcloud_token
}

resource "hcloud_ssh_key" "deploy" {
  name       = "postcodejager"
  public_key = var.ssh_public_key
}

resource "hcloud_firewall" "app" {
  name = "postcodejager"

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "22"
    source_ips = ["0.0.0.0/0", "::/0"]
  }
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "80"
    source_ips = ["0.0.0.0/0", "::/0"]
  }
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "443"
    source_ips = ["0.0.0.0/0", "::/0"]
  }
}

resource "hcloud_server" "app" {
  name         = "postcodejager"
  server_type  = var.server_type
  image        = "ubuntu-24.04"
  location     = var.location
  ssh_keys     = [hcloud_ssh_key.deploy.id]
  firewall_ids = [hcloud_firewall.app.id]

  public_net {
    ipv4_enabled = true
    ipv6_enabled = true
  }

  labels = {
    app = "postcodejager"
  }
}

# Hetzner DNS zone (managed via the same Hetzner Cloud token; DNS is part of the
# Cloud API since provider v1.56). Delegate your domain to Hetzner by setting the
# `nameservers` output at your registrar (TransIP).
resource "hcloud_zone" "main" {
  name = var.dns_zone
  mode = "primary"
}

# A-record pointing the host at the server. "@" as name targets the apex.
resource "hcloud_zone_rrset" "app" {
  zone    = hcloud_zone.main.name
  name    = var.subdomain
  type    = "A"
  ttl     = 300
  records = [{ value = hcloud_server.app.ipv4_address }]
}

# www -> same server (only for apex deploys; Caddy redirects www to the apex).
resource "hcloud_zone_rrset" "www" {
  count   = var.subdomain == "@" ? 1 : 0
  zone    = hcloud_zone.main.name
  name    = "www"
  type    = "A"
  ttl     = 300
  records = [{ value = hcloud_server.app.ipv4_address }]
}
