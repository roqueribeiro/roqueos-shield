resource "aws_db_instance" "banco" {
  identifier          = "banco"
  engine              = "postgres"
  instance_class      = "db.t3.micro"
  allocated_storage   = 20
  username            = "app"
  password            = var.senha_banco
  publicly_accessible = true
}

variable "senha_banco" {
  type      = string
  sensitive = true
}
