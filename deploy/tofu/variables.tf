variable "hcloud_token" {
  description = "Hetzner Cloud API token (read/write, project-scoped)."
  type        = string
  sensitive   = true
}

variable "hetznerdns_token" {
  description = "Hetzner DNS API token (console.hetzner.com/dns -> API tokens)."
  type        = string
  sensitive   = true
}

variable "dns_zone" {
  description = "Your DNS zone in Hetzner DNS, e.g. example.com."
  type        = string
}

variable "subdomain" {
  description = "Record name within the zone, e.g. postcodejager (=> postcodejager.example.com)."
  type        = string
  default     = "postcodejager"
}

variable "ssh_public_key" {
  description = "Public SSH key placed on the server (the matching private key deploys)."
  type        = string
}

variable "server_type" {
  description = "Hetzner server type. CAX11 = cheapest ARM, plenty for this app."
  type        = string
  default     = "cax11"
}

variable "location" {
  description = "Hetzner location (fsn1/nbg1/hel1 in the EU)."
  type        = string
  default     = "fsn1"
}
