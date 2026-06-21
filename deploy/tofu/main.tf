terraform {
  required_version = ">= 1.6"
  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.48"
    }
    hetznerdns = {
      source  = "timohirt/hetznerdns"
      version = "~> 2.2"
    }
  }
}

provider "hcloud" {
  token = var.hcloud_token
}

provider "hetznerdns" {
  apitoken = var.hetznerdns_token
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

# DNS A-record (subdomain -> server) in your existing Hetzner DNS zone.
data "hetznerdns_zone" "zone" {
  name = var.dns_zone
}

resource "hetznerdns_record" "app" {
  zone_id = data.hetznerdns_zone.zone.id
  name    = var.subdomain
  type    = "A"
  value   = hcloud_server.app.ipv4_address
  ttl     = 300
}
