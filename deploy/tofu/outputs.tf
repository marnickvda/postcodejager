output "server_ipv4" {
  description = "Public IPv4 of the server."
  value       = hcloud_server.app.ipv4_address
}

output "fqdn" {
  description = "Full hostname the app is reachable at."
  value       = var.subdomain == "@" ? var.dns_zone : "${var.subdomain}.${var.dns_zone}"
}

output "nameservers" {
  description = "Set these as your domain's nameservers at your registrar (TransIP)."
  value       = hcloud_zone.main.authoritative_nameservers.assigned
}
