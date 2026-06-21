output "server_ipv4" {
  description = "Public IPv4 of the server."
  value       = hcloud_server.app.ipv4_address
}

output "fqdn" {
  description = "Full hostname the app is reachable at."
  value       = "${var.subdomain}.${var.dns_zone}"
}
