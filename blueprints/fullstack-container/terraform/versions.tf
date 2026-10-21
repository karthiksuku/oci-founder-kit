terraform {
  required_version = ">= 1.6"
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "~> 9.10"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "oci" {
  region              = var.region
  config_file_profile = var.config_file_profile
}

# IAM changes (dynamic group, policy) must be made in the tenancy's home region.
provider "oci" {
  alias               = "home"
  region              = var.home_region
  config_file_profile = var.config_file_profile
}
