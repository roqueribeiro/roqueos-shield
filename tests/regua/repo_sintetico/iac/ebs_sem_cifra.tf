resource "aws_ebs_volume" "disco" {
  availability_zone = "us-east-1a"
  size              = 40
  encrypted         = false
}
