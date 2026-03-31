provider "aws" {
  region  = "us-east-1"
  profile = "terraform"
}

#terraform {
#  backend "s3" {
#    bucket         = "gauravdevstatelock123"
#    key            = "modules/security_group/terraform.tfstate"
#    region         = "us-east-1"
#    profile        = "terraform"
#    dynamodb_table = "terraform-lock-table"
#    encrypt        = true
#  }
#}

data "aws_vpc" "existing" {
  filter {
    name   = "tag:Name"
    values = ["dev-vpc"]
  }
}

resource "aws_security_group" "dev_sg" {
  name        = "dev_sg"
  description = "dev_sg"
  vpc_id      = data.aws_vpc.existing.id

  ingress {
    description = "Allow SSH from individual public IP"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "Allow HTTP from anywhere"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }


  ingress {
    description = "Allow HTTPS from anywhere"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "dev-sg1"
  }
}

