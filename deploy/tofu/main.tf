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

# DNS A-record in your existing Hetzner DNS zone, managed via the same Hetzner
# Cloud token (DNS is part of the Cloud API since provider v1.56). The zone must
# already exist in Hetzner DNS; "@" as name targets the apex.
resource "hcloud_zone_rrset" "app" {
  zone    = var.dns_zone
  name    = var.subdomain
  type    = "A"
  ttl     = 300
  records = [{ value = hcloud_server.app.ipv4_address }]
}
